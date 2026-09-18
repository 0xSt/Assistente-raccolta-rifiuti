"""Test delle API.

Si usano risorse finte: database in memoria, Qdrant in-process, modello programmabile.
Nessun container, nessuna rete, nessun modello scaricato: i test restano veloci e verificano
il contratto delle rotte, non la qualità del riconoscimento.
"""
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
    yield Risorse(ambiente.db, ambiente.qdrant, ambiente.vettorizzatore, ambiente.recupero,
                  modello, Agente(ambiente.recupero, modello))


@pytest.fixture
def client(risorse):
    with TestClient(crea_app(risorse)) as c:
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


# ------------------------------------------------------------------ domanda scritta

def test_la_domanda_scritta_salta_il_modello_di_visione(client, risorse):
    """Chi sa come si chiama l'oggetto non deve fotografarlo: si parte dalla sua parola,
    e il passaggio lento non viene eseguito."""
    prima = risorse.modello.chiamate_riconoscimento
    corpo = client.post(f"{PREFISSO}/domanda",
                        json={"comune": "Torino", "oggetto": "giornale"}).json()
    assert corpo["comune"] == "Torino"
    assert corpo["riconoscimento"]["oggetto"] == "giornale"
    assert corpo["riconoscimento"]["confidenza"] == 1.0
    assert risorse.modello.chiamate_riconoscimento == prima


def test_un_oggetto_troppo_corto_viene_rifiutato(client):
    risposta = client.post(f"{PREFISSO}/domanda", json={"comune": "Torino", "oggetto": "x"})
    assert risposta.status_code == 422


def test_la_domanda_controlla_il_comune(client):
    risposta = client.post(f"{PREFISSO}/domanda",
                           json={"comune": "Atlantide", "oggetto": "giornale"})
    assert risposta.status_code == 404


# ----------------------------------------------------- il come, non solo il dove

def test_la_risposta_porta_le_procedure_dei_canali_non_ordinari(client, monkeypatch):
    """Per un terzo del dizionario di Napoli "va in X" è vero e insufficiente: la
    destinazione non dice se devi chiamare, spostarti o aspettare un mezzo."""
    from ecoscan import procedure as proc
    from ecoscan.api import app as modulo

    finta = proc.Procedura(comune="Torino", canale="centro_raccolta", sforzo=5,
                           titolo="Lo porti tu", passi=["Documento", "Vai"], nota="Gratuito.")
    monkeypatch.setattr(modulo.Risorse, "procedure", lambda *_: [finta])

    corpo = client.post(f"{PREFISSO}/domanda",
                        json={"comune": "Torino", "oggetto": "giornale"}).json()
    assert corpo["procedure"][0]["titolo"] == "Lo porti tu"
    assert corpo["procedure"][0]["passi"] == ["Documento", "Vai"]
    assert corpo["procedure"][0]["da_casa"] is False


def test_una_risposta_tutta_ordinaria_non_diventa_un_elenco_puntato(client):
    """Quando si butta e basta, la procedura è al massimo una: tutti sanno cos'è un
    cassonetto, e tre passi per dire "mettilo nel sacco" sarebbero rumore."""
    corpo = client.post(f"{PREFISSO}/domanda",
                        json={"comune": "Torino", "oggetto": "giornale"}).json()
    canali = {p["canale"] for p in corpo["procedure"]}
    assert canali <= {"raccolta_ordinaria"}


def test_il_livello_3_dice_almeno_dove_chiedere(client, monkeypatch):
    """"Non lo so" è onesto ma inutile: chi ha l'oggetto in mano deve comunque buttarlo."""
    from ecoscan import procedure as proc
    from ecoscan.api import app as modulo

    ripiego = proc.Procedura(comune="Torino", canale="centro_raccolta", sforzo=5,
                             titolo="Lo porti tu", passi=["Vai al centro di raccolta"])
    monkeypatch.setattr(modulo.procedure_, "di_ripiego", lambda _: ripiego)

    corpo = client.post(f"{PREFISSO}/domanda",
                        json={"comune": "Torino", "oggetto": "oggetto che non esiste"}).json()
    if corpo["livello_evidenza"] == 3:
        assert corpo["ripiego"]["titolo"] == "Lo porti tu"


def test_i_canali_traducono_le_destinazioni(risorse):
    """Il canale è già nei dati: la procedura si trova da lì, non si indovina."""
    canali = risorse.canali("Torino")
    assert canali["carta_e_cartone"] == "raccolta_ordinaria"
    assert set(canali) == {d["nome"] for d in risorse.destinazioni("Torino")}
