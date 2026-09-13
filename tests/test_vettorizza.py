"""Test dei vettori e della ricerca ibrida.

Il vettorizzatore vero richiede Ollama, quindi i test usano un finto deterministico: a
interessare qui è la meccanica (cache, fusione, filtro per comune), non la qualità del
modello, che si misura con il set di valutazione.
"""
import sqlite3

import numpy as np
import pytest

from ecoscan.db.carica import carica
from ecoscan.db.indicizza import costruisci
from ecoscan.db.vettorizza import (
    calcola, cerca_ibrida, cerca_semantica, fondi_rrf, impronta,
)

DESTINAZIONI = [
    {"comune": "Torino", "nome": "carta_e_cartone", "canale": "raccolta_ordinaria", "colore": "giallo",
     "flussi": ["carta"], "alias_di": "", "note": ""},
    {"comune": "Torino", "nome": "rifiuto_non_recuperabile", "canale": "raccolta_ordinaria",
     "colore": "grigio", "flussi": ["residuo"], "alias_di": "", "note": ""},
]


def voce(slug, nome, destinazione):
    return {"comune": "Torino", "slug": slug, "nome": nome, "nome_originale": nome, "condizioni": [],
            "alias": [], "codice_materiale": None, "destinazioni": [destinazione],
            "avvertenza": None, "motivi": [], "da_revisionare": False}


VOCI = [voce("cartone-per-bevande", "Cartone per bevande Tetra Pak", "carta_e_cartone"),
        voce("giornali", "Giornali e riviste", "carta_e_cartone"),
        voce("pirofile", "Pirofile da forno", "rifiuto_non_recuperabile")]


class VettorizzatoreFinto:
    """Vettori deterministici dal testo: nessuna rete, risultati riproducibili."""

    nome = "finto"

    def __init__(self):
        self.chiamate = 0

    def vettorizza(self, testi, come="documento"):
        self.chiamate += len(testi)
        vettori = []
        for t in testi:
            generatore = np.random.default_rng(abs(hash(t.lower().replace("task: search result | query: ", "")
                                                       .replace("title: none | text: ", ""))) % 2**32)
            vettori.append(generatore.normal(size=8).tolist())
        return vettori


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    carica(c, DESTINAZIONI, VOCI, [], {})
    costruisci(c)
    yield c
    c.close()


def test_calcola_e_non_ricalcola(db):
    v = VettorizzatoreFinto()
    primo = calcola(db, v, avanzamento=lambda *_: None)
    assert primo["calcolati"] == 3 and v.chiamate == 3
    secondo = calcola(db, v, avanzamento=lambda *_: None)
    assert secondo["calcolati"] == 0 and v.chiamate == 3  # nessuna chiamata in più


def test_ricalcola_se_il_testo_cambia(db):
    v = VettorizzatoreFinto()
    calcola(db, v, avanzamento=lambda *_: None)
    db.execute("UPDATE scheda SET testo = 'Testo diverso' WHERE id = 1")
    db.commit()
    assert calcola(db, v, avanzamento=lambda *_: None)["calcolati"] == 1


def test_i_vettori_sono_normalizzati(db):
    calcola(db, VettorizzatoreFinto(), avanzamento=lambda *_: None)
    for (blob,) in db.execute("SELECT vettore FROM scheda_embedding"):
        assert np.isclose(np.linalg.norm(np.frombuffer(blob, dtype=np.float32)), 1.0, atol=1e-6)


def test_ricerca_semantica_trova_il_testo_identico(db):
    v = VettorizzatoreFinto()
    calcola(db, v, avanzamento=lambda *_: None)
    risultati = cerca_semantica(db, "Giornali e riviste", "Torino", v, k=1)
    assert risultati[0]["nome"] == "Giornali e riviste" and risultati[0]["punteggio"] > 0.99


def test_semantica_non_attraversa_i_comuni(db):
    v = VettorizzatoreFinto()
    calcola(db, v, avanzamento=lambda *_: None)
    assert cerca_semantica(db, "Giornali", "Napoli", v) == []


def test_rrf_premia_chi_compare_in_entrambe_le_classifiche():
    lessicale = [{"scheda_id": 1, "testo": "a"}, {"scheda_id": 2, "testo": "b"}]
    semantica = [{"scheda_id": 3, "testo": "c"}, {"scheda_id": 1, "testo": "a"}]
    fusi = fondi_rrf({"lessicale": lessicale, "semantica": semantica}, k=3)
    assert fusi[0]["scheda_id"] == 1                      # unico presente in entrambe
    assert fusi[0]["posizioni"] == {"lessicale": 1, "semantica": 2}


def test_rrf_usa_le_posizioni_non_i_punteggi():
    """BM25 è negativo e il coseno sta fra -1 e 1: sommare i punteggi non avrebbe senso."""
    lessicale = [{"scheda_id": 1, "punteggio": -9.9}]
    semantica = [{"scheda_id": 2, "punteggio": 0.95}]
    fusi = fondi_rrf({"lessicale": lessicale, "semantica": semantica}, k=2)
    assert {f["scheda_id"] for f in fusi} == {1, 2}
    assert fusi[0]["punteggio_rrf"] == fusi[1]["punteggio_rrf"]  # stessa posizione, stesso peso


def test_ibrida_unisce_i_due_metodi(db):
    v = VettorizzatoreFinto()
    calcola(db, v, avanzamento=lambda *_: None)
    risultati = cerca_ibrida(db, "giornali", "Torino", v, k=3)
    assert risultati and all("posizioni" in r for r in risultati)
    assert any("lessicale" in r["posizioni"] for r in risultati)


def test_impronta_dipende_dal_testo():
    assert impronta("a") != impronta("b") and impronta("a") == impronta("a")
