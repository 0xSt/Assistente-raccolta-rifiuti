"""Test della normalizzazione delle regole di categoria.

Il punto delicato è il collegamento fra il nome della scheda nella fonte e la destinazione
usata dalle voci: sono diversi in entrambi i comuni.
"""
import json

import pytest

from ecoscan.etl.normalizza_regole import (
    DESTINAZIONE_NAPOLI, DESTINAZIONE_TORINO, normalizza_napoli, normalizza_torino,
    verifica_destinazioni,
)
from ecoscan.percorsi import GREZZO

FRAZIONI_NAPOLI = [
    {"nome_frazione": "Carta e Cartone", "url": "https://x/carta-e-cartone/", "note": ["Piega le scatole"],
     "regole": [{"polarita": "ammesso", "testo": "Quaderni, libri, buste da lettera", "dettaglio": None,
                 "origine": "estrazione"}]},
    {"nome_frazione": "Umido/Organico", "url": "https://x/umido-organico/", "note": [],
     "regole": [{"polarita": "escluso", "testo": "Legno verniciato", "dettaglio": None,
                 "origine": "trascrizione_manuale"}]},
    {"nome_frazione": "Altri servizi", "url": "https://x/altre-raccolte/", "note": [], "regole": []},
]


def test_nomi_delle_frazioni_diversi_dalle_destinazioni():
    # è il motivo per cui serve una tabella di corrispondenza esplicita
    assert DESTINAZIONE_NAPOLI["Carta e Cartone"] == "Carta e Cartoncino"
    assert DESTINAZIONE_TORINO["Imballaggi in plastica"] == "imballaggi_plastica"


def test_normalizza_napoli():
    regole = normalizza_napoli(FRAZIONI_NAPOLI)
    assert {r.destinazione for r in regole} == {"Carta e Cartoncino", "Organico"}
    carta = next(r for r in regole if r.destinazione == "Carta e Cartoncino")
    assert carta.comune == "Napoli" and carta.origine == "estrazione"
    assert carta.riferimento == "https://x/carta-e-cartone/" and carta.note_frazione == ["Piega le scatole"]
    umido = next(r for r in regole if r.destinazione == "Organico")
    assert umido.polarita == "escluso" and umido.origine == "trascrizione_manuale"


def test_pagina_di_raccordo_non_produce_regole():
    # "Altri servizi" non è un contenitore: nessuna destinazione, nessuna regola
    assert all(r.destinazione is not None for r in normalizza_napoli(FRAZIONI_NAPOLI))


def test_frazione_sconosciuta_ferma_tutto():
    with pytest.raises(SystemExit, match="senza corrispondenza"):
        normalizza_napoli([{"nome_frazione": "Frazione Nuova", "url": "", "note": [], "regole": []}])


def test_verifica_destinazioni_smaschera_un_collegamento_sbagliato():
    regole = normalizza_napoli(FRAZIONI_NAPOLI)
    voci_corrette = {"Napoli": {"Carta e Cartoncino", "Organico", "Vetro"}}
    verifica_destinazioni(regole, voci_corrette)  # non solleva
    with pytest.raises(SystemExit, match="assenti dalle voci"):
        verifica_destinazioni(regole, {"Napoli": {"Carta e Cartone"}})  # nome sbagliato


REGOLE_TORINO = GREZZO / "torino" / "torino_regole.json"
torino = pytest.mark.skipif(not REGOLE_TORINO.is_file(), reason="regole di Torino non estratte")


@torino
def test_torino_tutte_le_schede_collegate():
    schede = json.loads(REGOLE_TORINO.read_text(encoding="utf-8"))
    regole = normalizza_torino(schede)
    assert len(regole) == 60
    assert {r.polarita for r in regole} == {"ammesso", "escluso", "nota"}
    carta = [r for r in regole if r.destinazione == "carta_e_cartone"]
    esclusi = [r.testo for r in carta if r.polarita == "escluso"]
    assert "carta con residui di cibo" in esclusi
    assert all(r.riferimento.startswith("Rifiutologo AMIAT 2025, pagina") for r in regole)


@torino
def test_celle_non_spezzate():
    # separare "Giornali, riviste, libri, quaderni" perderebbe le qualificazioni: resta intera
    regole = normalizza_torino(json.loads(REGOLE_TORINO.read_text(encoding="utf-8")))
    assert any(r.testo == "Giornali, riviste, libri, quaderni" for r in regole)
