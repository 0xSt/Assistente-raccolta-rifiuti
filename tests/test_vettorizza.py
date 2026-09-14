"""Test dell'indicizzazione su Qdrant e della ricerca ibrida.

Si usa la **modalità locale** di Qdrant su cartella temporanea: nessun container, nessuna
rete, test veloci come gli altri. Il vettorizzatore è finto ma deterministico: qui interessa
la meccanica (filtro, payload, fusione), non la qualità del modello, che si misura con il
set di valutazione.
"""
import sqlite3

import pytest

from tests.conftest import VettorizzatoreFinto

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


# Servono abbastanza schede per comune: con meno di POSIZIONI_AUTORECUPERO+1 il controllo
# dell'autorecupero non potrebbe mai fallire, e il test sarebbe inutile.
VOCI = [
    voce("Torino", "cartone-bevande", "Cartone per bevande Tetra Pak", "carta_e_cartone"),
    voce("Torino", "giornali", "Giornali e riviste", "carta_e_cartone"),
    voce("Torino", "pirofile", "Pirofile da forno", "rifiuto_non_recuperabile"),
    voce("Torino", "quaderni", "Quaderni e blocchi per appunti", "carta_e_cartone"),
    voce("Torino", "specchi", "Specchi rotti", "rifiuto_non_recuperabile"),
    voce("Torino", "stracci", "Stracci e strofinacci", "rifiuto_non_recuperabile"),
    voce("Napoli", "giornale", "Giornale", "Carta e Cartoncino"),
]


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
    assert qdrant.count(COLLEZIONE).count == len(VOCI)


def test_il_filtro_per_comune_e_dentro_la_query(ambiente):
    """Il vincolo D7 diventa strutturale: non è un filtro applicato dopo."""
    db, qdrant, v = ambiente
    assert qdrant.count(COLLEZIONE, count_filter=filtro("Torino")).count == len(VOCI) - 1
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
    assert qdrant.count(COLLEZIONE).count == len(VOCI)


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


def test_verifica_passa_su_un_indice_corretto(ambiente):
    from ecoscan.db.vettorizza import verifica
    esiti = verifica(*ambiente, campione=4)
    falliti = [d for ok, d in esiti if not ok]
    assert not falliti, falliti


def test_verifica_accorge_di_punti_mancanti(ambiente):
    from qdrant_client import models

    from ecoscan.db.vettorizza import COLLEZIONE, verifica
    db, qdrant, v = ambiente
    qdrant.delete(COLLEZIONE, points_selector=models.PointIdsList(points=[1]))
    descrizioni = [d for ok, d in verifica(db, qdrant, v, campione=4) if not ok]
    assert any("identificatori" in d for d in descrizioni)


def test_verifica_accorge_di_vettori_sbagliati(ambiente):
    """Conteggi giusti ma vettore disallineato: solo l'autorecupero se ne accorge.

    Il vettore viene invertito, così la scheda diventa il risultato *peggiore* per il proprio
    testo e finisce fuori dalle prime posizioni tollerate.
    """
    from qdrant_client import models

    from ecoscan.db.vettorizza import COLLEZIONE, NOME_VETTORE, verifica
    db, qdrant, v = ambiente
    punto = qdrant.scroll(COLLEZIONE, limit=1, with_vectors=True, with_payload=True)[0][0]
    invertito = [-x for x in punto.vector[NOME_VETTORE]]
    qdrant.upsert(COLLEZIONE, points=[models.PointStruct(id=punto.id,
                                                         vector={NOME_VETTORE: invertito},
                                                         payload=punto.payload)])
    descrizioni = [d for ok, d in verifica(db, qdrant, v, campione=10) if not ok]
    assert any("autorecupero" in d for d in descrizioni)
    assert not any("identificatori" in d for d in descrizioni)  # i conteggi tornano lo stesso


def test_la_polarita_e_parte_della_risposta(ambiente):
    """Una regola `escluso` dice dove l'oggetto NON va: mostrarne solo la destinazione
    ribalterebbe il significato."""
    import sqlite3

    from ecoscan.db.carica import carica
    from ecoscan.db.indicizza import costruisci
    from ecoscan.db.vettorizza import destinazioni

    db = sqlite3.connect(":memory:")
    regole = [{"comune": "Torino", "destinazione": "carta_e_cartone", "polarita": "escluso",
               "testo": "scontrini", "dettaglio": None, "origine": "estrazione",
               "fonte": "amiat", "riferimento": "pagina 8"},
              {"comune": "Torino", "destinazione": "carta_e_cartone", "polarita": "ammesso",
               "testo": "giornali", "dettaglio": None, "origine": "estrazione",
               "fonte": "amiat", "riferimento": "pagina 8"}]
    carica(db, DESTINAZIONI, VOCI, regole, {})
    costruisci(db)
    per_testo = {t: sid for sid, t in db.execute(
        "SELECT id, testo FROM scheda WHERE regola_id IS NOT NULL")}
    assert destinazioni(db, per_testo["scontrini"]) == "NO carta_e_cartone"
    assert destinazioni(db, per_testo["giornali"]) == "SI carta_e_cartone"
    db.close()


def test_l_autorecupero_dice_quali_schede_ha_mancato(ambiente):
    """Un controllo che fallisce senza dire cosa è fallito non serve a niente."""
    from qdrant_client import models

    from ecoscan.db.vettorizza import COLLEZIONE, NOME_VETTORE, verifica
    db, qdrant, v = ambiente
    punto = qdrant.scroll(COLLEZIONE, limit=1, with_vectors=True, with_payload=True)[0][0]
    qdrant.upsert(COLLEZIONE, points=[
        models.PointStruct(id=punto.id, vector={NOME_VETTORE: [-x for x in punto.vector[NOME_VETTORE]]},
                           payload=punto.payload)])
    descrizione = next(d for ok, d in verifica(db, qdrant, v, campione=10)
                       if not ok and "autorecupero" in d)
    assert "mancate:" in descrizione and "ha trovato" in descrizione
