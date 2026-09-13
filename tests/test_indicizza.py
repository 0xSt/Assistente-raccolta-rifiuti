"""Test dell'indice lessicale e della ricerca.

L'indice è un artefatto derivato: si ricostruisce dal livello relazionale. I test partono
da un database minimo costruito in memoria, più alcune prove sui dati reali di Torino.
"""
import sqlite3

import pytest

from ecoscan.db.carica import carica
from ecoscan.db.indicizza import cerca, costruisci, espressione_fts, radice, termini
from ecoscan.percorsi import DATI

DESTINAZIONI = [
    {"comune": "Torino", "nome": "vetro_e_imballaggi_metallo", "canale": "raccolta_ordinaria",
     "colore": "blu", "flussi": ["vetro", "metalli"], "alias_di": "", "note": ""},
    {"comune": "Torino", "nome": "rifiuto_non_recuperabile", "canale": "raccolta_ordinaria",
     "colore": "grigio", "flussi": ["residuo"], "alias_di": "", "note": ""},
]


def voce(slug, nome, condizioni, destinazione, alias=()):
    return {"comune": "Torino", "slug": slug, "nome": nome, "nome_originale": nome,
            "condizioni": list(condizioni), "alias": list(alias), "codice_materiale": None,
            "destinazioni": [destinazione], "avvertenza": None, "motivi": [], "da_revisionare": False}


VOCI = [
    voce("bicchieri-di-vetro", "Bicchieri di vetro", [], "vetro_e_imballaggi_metallo"),
    voce("bicchieri-di-cristallo", "Bicchieri di cristallo", [], "rifiuto_non_recuperabile"),
    voce("cartone-per-bevande", "Cartone per bevande", [], "rifiuto_non_recuperabile",
         alias=["Tetrapak"]),
]

REGOLE = [
    {"comune": "Torino", "destinazione": "vetro_e_imballaggi_metallo", "polarita": "escluso",
     "testo": "lampadine", "dettaglio": "Oggetti in ceramica, lampadine e specchi NON vanno nel vetro!",
     "origine": "estrazione", "fonte": "amiat", "riferimento": "pagina 10"},
    {"comune": "Torino", "destinazione": "vetro_e_imballaggi_metallo", "polarita": "escluso",
     "testo": "specchi", "dettaglio": "Oggetti in ceramica, lampadine e specchi NON vanno nel vetro!",
     "origine": "estrazione", "fonte": "amiat", "riferimento": "pagina 10"},
    {"comune": "Torino", "destinazione": "vetro_e_imballaggi_metallo", "polarita": "nota",
     "testo": "Svuotare gli imballaggi", "dettaglio": None, "origine": "estrazione",
     "fonte": "amiat", "riferimento": "pagina 10"},
]


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    carica(c, DESTINAZIONI, VOCI, REGOLE, {})
    costruisci(c)
    yield c
    c.close()


@pytest.mark.parametrize("parola, attesa", [
    ("bicchiere", "bicchier"),   # per trovare anche "Bicchieri"
    ("bottiglie", "bottigli"),
    ("plastica", "plastic"),
    ("vetro", "vetr"),
    ("unto", "unto"),            # parole corte restano intere
    ("cd", "cd"),
])
def test_radice(parola, attesa):
    assert radice(parola) == attesa


def test_termini_scarta_le_parole_corte_e_gli_accenti():
    assert termini("Capsule di caffè in plastica") == ["capsul", "caff", "plastic"]


def test_espressione_and_e_or():
    assert espressione_fts("bicchiere vetro") == '"bicchier" AND "vetr"'
    assert espressione_fts("bicchiere vetro", "OR") == '"bicchier" OR "vetr"'
    assert espressione_fts("di") is None


def test_una_voce_genera_una_scheda_per_nome_e_una_per_alias(db):
    tipi = dict(db.execute("SELECT tipo, count(*) FROM scheda GROUP BY tipo").fetchall())
    assert tipi == {"voce": 3, "alias": 1, "regola": 2}  # la nota non è indicizzata


def test_ricerca_singolare_trova_il_plurale(db):
    risultati = cerca(db, "bicchiere di vetro", "Torino")
    assert risultati and risultati[0]["nome"] == "Bicchieri di vetro"


def test_alias_raggiungibile(db):
    """Chi cerca "tetrapak" non deve sperare che assomigli a "Cartone per bevande"."""
    risultati = cerca(db, "tetrapak", "Torino")
    assert risultati and risultati[0]["tipo"] == "alias" and risultati[0]["nome"] == "Cartone per bevande"


def test_oggetti_simili_con_destinazioni_diverse_sono_entrambi_candidati(db):
    """Il caso in cui l'agente deve chiedere all'utente: entrambi vanno restituiti."""
    destinazioni = {r["destinazione"] for r in cerca(db, "bicchieri", "Torino")}
    assert destinazioni == {"vetro_e_imballaggi_metallo", "rifiuto_non_recuperabile"}


def test_ripiego_da_and_a_or(db):
    # nessuna scheda contiene tutti i termini: si ripiega su OR invece di non dare nulla
    risultati = cerca(db, "bicchieri di porcellana", "Torino")
    assert risultati and all(r["strategia"] == "or" for r in risultati)
    assert cerca(db, "bicchieri di vetro", "Torino")[0]["strategia"] == "and"


def test_il_dettaglio_non_e_indicizzato(db):
    """Il dettaglio degli esclusi è la frase intera: indicizzarla renderebbe ogni oggetto
    escluso raggiungibile con le parole di tutti gli altri."""
    risultati = cerca(db, "ceramica", "Torino", livello=2)
    assert not risultati


def test_filtro_per_livello(db):
    assert all(r["livello"] == 2 for r in cerca(db, "lampadine", "Torino", livello=2))
    assert all(r["livello"] == 1 for r in cerca(db, "bicchieri", "Torino", livello=1))


def test_la_ricerca_non_attraversa_i_comuni(db):
    assert cerca(db, "bicchieri", "Napoli") == []


@pytest.mark.skipif(not (DATI / "ecoscan.db").is_file(), reason="database non costruito")
def test_dati_reali():
    with sqlite3.connect(DATI / "ecoscan.db") as reale:
        risultati = cerca(reale, "capsula caffe plastica", "Torino")
        nomi = {r["nome"] for r in risultati}
        assert "Capsule del caffè in plastica" in nomi
