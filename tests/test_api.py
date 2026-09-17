"""Test delle API.

Si usano risorse finte: database in memoria, Qdrant in-process, modello programmabile.
Nessun container, nessuna rete, nessun modello scaricato: i test restano veloci e verificano
il contratto delle rotte, non la qualità del riconoscimento.
"""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from ecoscan.agente.agente import Agente
from ecoscan.api.app import PREFISSO, crea_app
from ecoscan.api.risorse import Risorse
from tests.conftest import ModelloFinto


@pytest.fixture
def risorse(ambiente):
    modello = ModelloFinto()
    yield Risorse(ambiente.db, ambiente.qdrant, ambiente.vettorizzatore, modello,
                  Agente(ambiente.qdrant, ambiente.vettorizzatore, modello))


@pytest.fixture
def client(risorse, tmp_path):
    with TestClient(crea_app(risorse, riscontri=tmp_path / "riscontri.jsonl")) as c:
        yield c


def test_comuni(client):
    risposta = client.get(f"{PREFISSO}/comuni")
    assert risposta.status_code == 200
    nomi = {c["nome"] for c in risposta.json()}
    assert "Torino" in nomi
    torino = next(c for c in risposta.json() if c["nome"] == "Torino")
    assert torino["voci"] > 0 and torino["gestore"]


def test_salute_riporta_lo_stato_dei_servizi(client):
    corpo = client.get(f"{PREFISSO}/salute").json()
    assert corpo["database"] is True and corpo["qdrant"] is True
    assert corpo["schede_indicizzate"] > 0 and corpo["modello_visione"]


def test_analizza_restituisce_una_risposta_completa(client):
    risposta = client.post(f"{PREFISSO}/analizza", data={"comune": "Torino"},
                           files={"foto": ("f.jpg", b"contenuto", "image/jpeg")})
    assert risposta.status_code == 200
    corpo = risposta.json()
    assert corpo["comune"] == "Torino" and corpo["livello_evidenza"] in (1, 2, 3)
    assert corpo["riconoscimento"]["oggetto"]
    assert "contesto" in corpo and corpo["contesto"]["comune"] == "Torino"


def test_analizza_rifiuta_una_foto_vuota(client):
    risposta = client.post(f"{PREFISSO}/analizza", data={"comune": "Torino"},
                           files={"foto": ("f.jpg", b"", "image/jpeg")})
    assert risposta.status_code == 400


def test_analizza_rifiuta_un_comune_sconosciuto(client):
    risposta = client.post(f"{PREFISSO}/analizza", data={"comune": "Atlantide"},
                           files={"foto": ("f.jpg", b"x", "image/jpeg")})
    assert risposta.status_code == 404 and "Atlantide" in risposta.json()["detail"]


def test_il_contesto_permette_di_continuare(client):
    prima = client.post(f"{PREFISSO}/analizza", data={"comune": "Torino"},
                        files={"foto": ("f.jpg", b"x", "image/jpeg")}).json()
    dopo = client.post(f"{PREFISSO}/continua",
                       json={"contesto": prima["contesto"], "risposta": "è vuota"})
    assert dopo.status_code == 200 and dopo.json()["comune"] == "Torino"


def test_un_contesto_inventato_viene_rifiutato(client):
    risposta = client.post(f"{PREFISSO}/continua", json={"contesto": {"a": 1}, "risposta": "x"})
    assert risposta.status_code == 400


def test_cerca_senza_modello_di_visione(client):
    risposta = client.post(f"{PREFISSO}/cerca",
                           json={"domanda": "giornali", "comune": "Torino", "k": 5})
    assert risposta.status_code == 200
    candidati = risposta.json()
    assert candidati and all("id" in c for c in candidati)
    assert {c["livello"] for c in candidati} <= {1, 2}


def test_cerca_filtra_per_livello(client):
    corpo = client.post(f"{PREFISSO}/cerca",
                        json={"domanda": "carta", "comune": "Torino", "livello": 2}).json()
    assert all(c["livello"] == 2 for c in corpo)


def test_il_riscontro_viene_registrato(client, tmp_path):
    risposta = client.post(f"{PREFISSO}/riscontro", json={
        "comune": "Torino", "corretta": False, "oggetto": "sandalo",
        "destinazione_attesa": "abiti", "nota": "ha scelto Stivali"})
    assert risposta.status_code == 201
    righe = (tmp_path / "riscontri.jsonl").read_text(encoding="utf-8").splitlines()
    riga = json.loads(righe[0])
    assert riga["corretta"] is False and riga["oggetto"] == "sandalo" and riga["quando"]


def test_il_database_e_aperto_in_sola_lettura(tmp_path):
    """Il backend non scrive mai nei dati: l'ETL è separato."""
    from ecoscan.api.risorse import apri_database_in_lettura

    percorso = tmp_path / "prova.db"
    sqlite3.connect(percorso).executescript("CREATE TABLE t (x); INSERT INTO t VALUES (1);")
    db = apri_database_in_lettura(percorso)
    assert db.execute("SELECT count(*) FROM t").fetchone()[0] == 1
    with pytest.raises(sqlite3.OperationalError):
        db.execute("INSERT INTO t VALUES (2)")
    db.close()


def test_database_mancante_spiega_cosa_fare(tmp_path):
    from ecoscan.api.risorse import apri_database_in_lettura

    with pytest.raises(SystemExit, match="ecoscan-carica"):
        apri_database_in_lettura(tmp_path / "assente.db")


def test_le_destinazioni_hanno_un_etichetta_leggibile(client):
    """A Torino i nomi nei dati sono chiavi: l'interfaccia deve poterle tradurre."""
    corpo = client.get(f"{PREFISSO}/destinazioni", params={"comune": "Torino"}).json()
    per_nome = {d["nome"]: d for d in corpo}
    assert per_nome["carta_e_cartone"]["etichetta"] == "Carta e cartone"
    assert per_nome["carta_e_cartone"]["colore"] == "giallo"
    # senza etichetta nel riferimento si ripiega sul nome, mai su niente
    assert all(d["etichetta"] for d in corpo)


def test_le_destinazioni_rifiutano_un_comune_sconosciuto(client):
    assert client.get(f"{PREFISSO}/destinazioni", params={"comune": "Atlantide"}).status_code == 404


def test_la_risposta_dice_quale_documento_ha_scelto(client):
    """Senza l'id del documento scelto l'interfaccia non può citare la fonte."""
    corpo = client.post(f"{PREFISSO}/analizza", data={"comune": "Torino"},
                        files={"foto": ("f.jpg", b"contenuto", "image/jpeg")}).json()
    if corpo["livello_evidenza"] in (1, 2):
        assert corpo["scelto_id"] in [c["id"] for c in corpo["candidati"]]


def test_correggi_riparte_dall_oggetto_dell_utente(client):
    """La foto non si rilegge: chi ha l'oggetto in mano vale più del modello di visione."""
    prima = client.post(f"{PREFISSO}/analizza", data={"comune": "Torino"},
                        files={"foto": ("f.jpg", b"contenuto", "image/jpeg")}).json()
    dopo = client.post(f"{PREFISSO}/correggi",
                       json={"contesto": prima["contesto"], "oggetto": "giornali e riviste"})
    assert dopo.status_code == 200
    corpo = dopo.json()
    assert corpo["riconoscimento"]["oggetto"] == "giornali e riviste"
    assert corpo["riconoscimento"]["confidenza"] == 1.0
    assert corpo["contesto"]["id_conversazione"] == prima["contesto"]["id_conversazione"]


def test_correggi_rifiuta_un_contesto_inventato(client):
    assert client.post(f"{PREFISSO}/correggi",
                       json={"contesto": {}, "oggetto": "x"}).status_code == 400


def test_correggi_rifiuta_un_oggetto_vuoto(client):
    risposta = client.post(f"{PREFISSO}/correggi",
                           json={"contesto": {"comune": "Torino"}, "oggetto": ""})
    assert risposta.status_code == 422


def eventi_di(risposta) -> list[dict]:
    """Legge un flusso SSE: ogni riga `data: ` è un evento."""
    return [json.loads(r[6:]) for r in risposta.text.splitlines() if r.startswith("data: ")]


def test_analizza_a_flusso_manda_le_fasi_e_poi_la_risposta(client):
    risposta = client.post(f"{PREFISSO}/analizza/flusso", data={"comune": "Torino"},
                           files={"foto": ("f.jpg", b"contenuto", "image/jpeg")})
    assert risposta.status_code == 200
    assert risposta.headers["content-type"].startswith("text/event-stream")

    eventi = eventi_di(risposta)
    fasi = [e["fase"] for e in eventi]
    assert fasi[0] == "riconoscimento" and fasi[-1] == "risposta", "l'ultimo evento chiude"
    assert "recupero" in fasi
    finale = eventi[-1]["risposta"]
    assert finale["comune"] == "Torino" and "livello_evidenza" in finale


def test_il_flusso_dice_subito_cosa_ha_riconosciuto(client):
    """È il motivo della funzione: non far aspettare la fine per scoprire l'errore."""
    eventi = eventi_di(client.post(f"{PREFISSO}/analizza/flusso", data={"comune": "Torino"},
                                   files={"foto": ("f.jpg", b"contenuto", "image/jpeg")}))
    visto = next(e for e in eventi if e["fase"] == "riconosciuto")
    assert visto["riconoscimento"]["oggetto"]
    fasi = [e["fase"] for e in eventi]
    assert fasi.index("riconosciuto") < fasi.index("recupero")


def test_il_flusso_rifiuta_una_foto_vuota(client):
    risposta = client.post(f"{PREFISSO}/analizza/flusso", data={"comune": "Torino"},
                           files={"foto": ("f.jpg", b"", "image/jpeg")})
    assert risposta.status_code == 400


def test_continua_e_correggi_hanno_il_loro_flusso(client):
    prima = client.post(f"{PREFISSO}/analizza", data={"comune": "Torino"},
                        files={"foto": ("f.jpg", b"contenuto", "image/jpeg")}).json()

    continua = eventi_di(client.post(f"{PREFISSO}/continua/flusso",
                                     json={"contesto": prima["contesto"], "risposta": "sporco"}))
    assert continua[-1]["fase"] == "risposta"
    assert "riconoscimento" not in [e["fase"] for e in continua], "la foto non si rilegge"

    correggi = eventi_di(client.post(f"{PREFISSO}/correggi/flusso",
                                     json={"contesto": prima["contesto"], "oggetto": "giornali"}))
    assert correggi[-1]["risposta"]["riconoscimento"]["oggetto"] == "giornali"


def test_un_guasto_dell_agente_diventa_un_evento_di_errore(risorse, tmp_path, monkeypatch):
    """Il client deve sapere che è finita male, non restare in attesa di una risposta."""
    def rotto(*argomenti, **opzioni):
        raise RuntimeError("Ollama spento")

    monkeypatch.setattr(risorse.agente, "analizza", rotto)
    with TestClient(crea_app(risorse, riscontri=tmp_path / "riscontri.jsonl")) as client:
        eventi = eventi_di(client.post(f"{PREFISSO}/analizza/flusso", data={"comune": "Torino"},
                                       files={"foto": ("f.jpg", b"x", "image/jpeg")}))
    assert eventi[-1]["fase"] == "errore" and "Ollama" in eventi[-1]["dettaglio"]
