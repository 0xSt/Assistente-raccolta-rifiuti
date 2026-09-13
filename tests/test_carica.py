"""Test del caricamento relazionale.

Il database è un artefatto derivato: si ricostruisce da zero. I test verificano che i
controlli di coerenza blocchino i dati zoppi e che la struttura regga le interrogazioni
che serviranno all'agente.
"""
import sqlite3

import pytest

from ecoscan.db.carica import carica, leggi_destinazioni, leggi_jsonl, verifica
from ecoscan.percorsi import DATI

DESTINAZIONI = [
    {"comune": "Torino", "nome": "carta_e_cartone", "canale": "raccolta_ordinaria",
     "colore": "giallo", "flussi": ["carta"], "alias_di": "", "note": ""},
    {"comune": "Torino", "nome": "organico", "canale": "raccolta_ordinaria",
     "colore": "marrone", "flussi": ["organico"], "alias_di": "", "note": ""},
    {"comune": "Torino", "nome": "cartone", "canale": "", "colore": "", "flussi": [],
     "alias_di": "carta_e_cartone", "note": "variante"},
]

VOCI = [
    {"comune": "Torino", "slug": "cartone-da-pizza-pulito", "nome": "Cartone da pizza",
     "nome_originale": "Cartone da pizza pulito", "condizioni": ["pulito"], "alias": ["Scatola pizza"],
     "codice_materiale": None, "destinazioni": ["carta_e_cartone"], "avvertenza": None,
     "motivi": [], "da_revisionare": False},
    {"comune": "Torino", "slug": "cartone-da-pizza-sporco", "nome": "Cartone da pizza",
     "nome_originale": "Cartone da pizza sporco", "condizioni": ["sporco"], "alias": [],
     "codice_materiale": None, "destinazioni": ["organico", "cartone"], "avvertenza": None,
     "motivi": ["risolto a mano: conferma"], "da_revisionare": False},
]

REGOLE = [
    {"comune": "Torino", "destinazione": "carta_e_cartone", "polarita": "escluso",
     "testo": "carta con residui di cibo", "dettaglio": None, "origine": "estrazione",
     "fonte": "amiat", "riferimento": "pagina 8"},
]


@pytest.fixture
def db():
    connessione = sqlite3.connect(":memory:")
    carica(connessione, DESTINAZIONI, VOCI, REGOLE, {"Torino": {"x": [
        {"azione": "conferma", "valore": "", "nota": "due oggetti"}]}})
    yield connessione
    connessione.close()


def test_conteggi(db):
    assert db.execute("SELECT count(*) FROM voce").fetchone()[0] == 2
    assert db.execute("SELECT count(*) FROM regola").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM decisione_revisione").fetchone()[0] == 1


def test_alias_di_destinazione_punta_alla_stessa_riga(db):
    """"cartone" è una variante: la voce che la usa deve finire su "carta_e_cartone"."""
    assert db.execute("SELECT count(*) FROM destinazione").fetchone()[0] == 2
    alias = db.execute("SELECT alias FROM destinazione_alias").fetchall()
    assert alias == [("cartone",)]
    destinazioni = db.execute("""SELECT d.nome FROM voce v JOIN voce_destinazione vd ON vd.voce_id = v.id
                                 JOIN destinazione d ON d.id = vd.destinazione_id
                                 WHERE v.slug = 'cartone-da-pizza-sporco' ORDER BY vd.ordine""").fetchall()
    assert destinazioni == [("organico",), ("carta_e_cartone",)]


def test_stesso_nome_condizioni_diverse(db):
    """Le due voci hanno lo stesso nome: è la condizione a distinguerle."""
    righe = db.execute("""SELECT vc.condizione, d.nome FROM voce v
                          JOIN voce_condizione vc ON vc.voce_id = v.id
                          JOIN voce_destinazione vd ON vd.voce_id = v.id
                          JOIN destinazione d ON d.id = vd.destinazione_id
                          WHERE v.nome = 'Cartone da pizza' AND d.nome != 'carta_e_cartone'
                             OR (v.nome = 'Cartone da pizza' AND vc.condizione = 'pulito')
                          ORDER BY vc.condizione""").fetchall()
    assert ("pulito", "carta_e_cartone") in righe and ("sporco", "organico") in righe


def test_revisione_manuale_registrata(db):
    assert db.execute("SELECT revisione_manuale FROM voce WHERE slug = 'cartone-da-pizza-sporco'"
                      ).fetchone()[0] == 1
    assert db.execute("SELECT revisione_manuale FROM voce WHERE slug = 'cartone-da-pizza-pulito'"
                      ).fetchone()[0] == 0


def test_chiavi_esterne_attive(db):
    db.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO voce_destinazione VALUES (1, 999, 0)")


def test_verifica_blocca_destinazione_ignota():
    voci = [{**VOCI[0], "destinazioni": ["contenitore_inventato"]}]
    with pytest.raises(SystemExit, match="assenti da data/riferimento"):
        verifica(DESTINAZIONI, voci, [])


def test_verifica_blocca_destinazione_mai_usata():
    with pytest.raises(SystemExit, match="mai usate"):
        verifica(DESTINAZIONI + [{"comune": "Torino", "nome": "dimenticata", "canale": "centro_raccolta",
                                  "colore": "", "flussi": [], "alias_di": "", "note": ""}], VOCI, REGOLE)


def test_verifica_blocca_alias_orfano():
    destinazioni = [DESTINAZIONI[0], DESTINAZIONI[1],
                    {**DESTINAZIONI[2], "alias_di": "inesistente"}]
    with pytest.raises(SystemExit, match="che non esiste"):
        verifica(destinazioni, VOCI, REGOLE)


def test_verifica_ignora_i_comuni_assenti():
    """Caricare un comune solo è legittimo: le destinazioni dell'altro non vanno controllate."""
    destinazioni = DESTINAZIONI + [{"comune": "Napoli", "nome": "Vetro", "canale": "raccolta_ordinaria",
                                    "colore": "verde", "flussi": ["vetro"], "alias_di": "", "note": ""}]
    verifica(destinazioni, VOCI, REGOLE)  # non solleva


def test_file_di_riferimento_coerente():
    """Il CSV versionato deve essere leggibile e avere canali validi."""
    destinazioni = leggi_destinazioni()
    canali = {"raccolta_ordinaria", "contenitore_dedicato", "centro_raccolta",
              "raccolta_itinerante", "ritiro_domicilio", ""}
    assert all(d["canale"] in canali for d in destinazioni)
    assert all(d["canale"] or d["alias_di"] for d in destinazioni), "solo gli alias possono non avere canale"
    assert {d["comune"] for d in destinazioni} == {"Napoli", "Torino"}


@pytest.mark.skipif(not (DATI / "normalizzato" / "torino_voci.jsonl").is_file(),
                    reason="normalizzato non generato")
def test_dati_reali_superano_la_verifica():
    voci = leggi_jsonl(DATI / "normalizzato" / "torino_voci.jsonl")
    regole = leggi_jsonl(DATI / "normalizzato" / "regole.jsonl")
    verifica(leggi_destinazioni(), voci, regole)
