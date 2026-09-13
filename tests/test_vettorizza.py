"""Test dell'indicizzazione su Qdrant e della ricerca ibrida.

Si usa la **modalità locale** di Qdrant su cartella temporanea: nessun container, nessuna
rete, test veloci come gli altri. Il vettorizzatore è finto ma deterministico: qui interessa
la meccanica (filtro, payload, fusione), non la qualità del modello, che si misura con il
set di valutazione.
"""
import sqlite3

import numpy as np
import pytest

from ecoscan.db.carica import carica
from ecoscan.db.indicizza import costruisci
from ecoscan.db.vettorizza import (
    COLLEZIONE, apri_qdrant, cerca_ibrida, cerca_semantica, destinazioni, filtro,
    fondi_rrf, indicizza, schede_da_indicizzare,
)

DESTINAZIONI = [
    {"comune": "Torino", "nome": "carta_e_cartone", "canale": "raccolta_ordinaria", "colore": "giallo",
     "flussi": ["carta"], "alias_di": "", "note": ""},
    {"comune": "Torino", "nome": "rifiuto_non_recuperabile", "canale": "raccolta_ordinaria",
     "colore": "grigio", "flussi": ["residuo"], "alias_di": "", "note": ""},
    {"comune": "Napoli", "nome": "Carta e Cartoncino", "canale": "raccolta_ordinaria", "colore": "blu",
     "flussi": ["carta"], "alias_di": "", "note": ""},
]


def voce(comune, slug, nome, destinazione):
    return {"comune": comune, "slug": slug, "nome": nome, "nome_originale": nome, "condizioni": [],
            "alias": [], "codice_materiale": None, "destinazioni": [destinazione],
            "avvertenza": None, "motivi": [], "da_revisionare": False}


VOCI = [
    voce("Torino", "cartone-bevande", "Cartone per bevande Tetra Pak", "carta_e_cartone"),
    voce("Torino", "giornali", "Giornali e riviste", "carta_e_cartone"),
    voce("Torino", "pirofile", "Pirofile da forno", "rifiuto_non_recuperabile"),
    voce("Napoli", "giornale", "Giornale", "Carta e Cartoncino"),
]


class VettorizzatoreFinto:
    """Vettori deterministici dal testo: nessuna rete, risultati riproducibili."""

    nome = "finto"
    dimensione = 8

    def __init__(self):
        self.chiamate = 0

    def vettorizza(self, testi, come="documento"):
        self.chiamate += len(testi)
        vettori = []
        for t in testi:
            nudo = (t.replace("task: search result | query: ", "")
                     .replace("title: none | text: ", "").lower())
            generatore = np.random.default_rng(abs(hash(nudo)) % 2**32)
            vettori.append(generatore.normal(size=self.dimensione).tolist())
        return vettori


@pytest.fixture
def ambiente(tmp_path):
    db = sqlite3.connect(":memory:")
    carica(db, DESTINAZIONI, VOCI, [], {})
    costruisci(db)
    qdrant = apri_qdrant(str(tmp_path / "qdrant"))
    vettorizzatore = VettorizzatoreFinto()
    indicizza(qdrant, schede_da_indicizzare(db), vettorizzatore, avanzamento=lambda *_: None)
    yield db, qdrant, vettorizzatore
    qdrant.close()
    db.close()


def test_apri_qdrant_distingue_url_e_percorso(tmp_path):
    locale = apri_qdrant(str(tmp_path / "q"))
    assert locale._client.__class__.__name__ == "QdrantLocal"
    locale.close()


def test_tutte_le_schede_indicizzate(ambiente):
    _, qdrant, _ = ambiente
    assert qdrant.count(COLLEZIONE).count == 4


def test_il_filtro_per_comune_e_dentro_la_query(ambiente):
    """Il vincolo D7 diventa strutturale: non è un filtro applicato dopo."""
    db, qdrant, v = ambiente
    assert qdrant.count(COLLEZIONE, count_filter=filtro("Torino")).count == 3
    risultati = cerca_semantica(qdrant, "giornale", "Napoli", v, k=5)
    assert {r["comune"] for r in risultati} == {"Napoli"}


def test_ricerca_semantica_trova_il_testo_identico(ambiente):
    _, qdrant, v = ambiente
    risultati = cerca_semantica(qdrant, "Giornali e riviste", "Torino", v, k=1)
    assert risultati[0]["testo"] == "Giornali e riviste" and risultati[0]["punteggio"] > 0.99


def test_filtro_per_livello(ambiente):
    _, qdrant, v = ambiente
    assert all(r["livello"] == 1 for r in cerca_semantica(qdrant, "giornali", "Torino", v, livello=1))


def test_il_payload_non_contiene_la_destinazione(ambiente):
    """Qdrant trova, SQLite risponde: la destinazione si legge dal relazionale (D9)."""
    db, qdrant, v = ambiente
    risultato = cerca_semantica(qdrant, "Giornali e riviste", "Torino", v, k=1)[0]
    assert "destinazione" not in risultato
    assert destinazioni(db, risultato["scheda_id"]) == "carta_e_cartone"


def test_reindicizzare_non_duplica(ambiente):
    db, qdrant, v = ambiente
    indicizza(qdrant, schede_da_indicizzare(db), v, avanzamento=lambda *_: None)
    assert qdrant.count(COLLEZIONE).count == 4


def test_rrf_premia_chi_compare_in_entrambe_le_classifiche():
    lessicale = [{"scheda_id": 1, "testo": "a"}, {"scheda_id": 2, "testo": "b"}]
    semantica = [{"scheda_id": 3, "testo": "c"}, {"scheda_id": 1, "testo": "a"}]
    fusi = fondi_rrf({"lessicale": lessicale, "semantica": semantica}, k=3)
    assert fusi[0]["scheda_id"] == 1
    assert fusi[0]["posizioni"] == {"lessicale": 1, "semantica": 2}


def test_rrf_usa_le_posizioni_non_i_punteggi():
    """BM25 è negativo e il coseno sta fra -1 e 1: sommare i punteggi non avrebbe senso."""
    fusi = fondi_rrf({"lessicale": [{"scheda_id": 1, "punteggio": -9.9}],
                      "semantica": [{"scheda_id": 2, "punteggio": 0.95}]}, k=2)
    assert fusi[0]["punteggio_rrf"] == fusi[1]["punteggio_rrf"]


def test_ibrida_unisce_i_due_metodi(ambiente):
    db, qdrant, v = ambiente
    risultati = cerca_ibrida(db, qdrant, "giornali", "Torino", v, k=3)
    assert risultati and any("lessicale" in r["posizioni"] for r in risultati)
    assert any("semantica" in r["posizioni"] for r in risultati)
