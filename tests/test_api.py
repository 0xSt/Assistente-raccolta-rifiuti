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
