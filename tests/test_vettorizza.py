"""Test dell'indicizzazione dei documenti su Qdrant e della ricerca semantica."""
import pytest

from ecoscan.db.vettorizza import (
    COLLEZIONE, apri_qdrant, cerca, cerca_per_codice, codici_nella_domanda, filtro,
    indicizza, verifica,
)


def test_solo_i_documenti_indicizzabili_finiscono_in_qdrant(ambiente):
    """I documenti per destinazione servono a spiegare, non a essere cercati."""
    attesi = sum(1 for d in ambiente.documenti if d.indicizzabile)
    assert ambiente.qdrant.count(COLLEZIONE).count == attesi
    assert any(not d.indicizzabile for d in ambiente.documenti)


def test_il_filtro_per_comune_e_dentro_la_query(ambiente):
    torino = ambiente.qdrant.count(COLLEZIONE, count_filter=filtro("Torino")).count
    napoli = ambiente.qdrant.count(COLLEZIONE, count_filter=filtro("Napoli")).count
    assert torino and napoli and torino + napoli == ambiente.qdrant.count(COLLEZIONE).count
    risultati = cerca(ambiente.qdrant, "giornale", "Napoli", ambiente.vettorizzatore)
    assert {r["comune"] for r in risultati} == {"Napoli"}


def test_la_ricerca_trova_il_testo_identico(ambiente):
    documento = next(d for d in ambiente.documenti if d.nome == "Giornali e riviste")
    trovati = cerca(ambiente.qdrant, documento.testo, "Torino", ambiente.vettorizzatore, k=1)
    assert trovati[0]["id"] == documento.id and trovati[0]["punteggio"] > 0.99


def test_il_payload_porta_le_varianti(ambiente):
    documento = next(d for d in ambiente.documenti if d.nome == "Cartone da pizza")
    trovato = cerca(ambiente.qdrant, documento.testo, "Torino", ambiente.vettorizzatore, k=1)[0]
    condizioni = {v["condizione"] for v in trovato["varianti"]}
    assert condizioni == {"pulito", "sporco"}
    assert all(v["destinazioni"] for v in trovato["varianti"])


def test_filtro_per_livello(ambiente):
    regole = cerca(ambiente.qdrant, "carta", "Torino", ambiente.vettorizzatore, livello=2, k=5)
    assert regole and all(r["livello"] == 2 for r in regole)


@pytest.mark.parametrize("domanda, atteso", [
    ("PAP 21", ["PAP 21"]),
    ("il simbolo alu 41 sulla lattina", ["ALU 41"]),
    ("C/PAP 81", ["C/PAP 81"]),
    ("una bottiglia di plastica", []),
])
def test_i_codici_materiale_si_riconoscono_nella_domanda(domanda, atteso):
    """Un codice è un identificatore, non un testo da cercare: si aggancia in modo esatto.
    È l'unico caso in cui la vecchia ricerca lessicale batteva quella semantica."""
    assert codici_nella_domanda(domanda) == atteso


def test_la_ricerca_per_codice_trova_il_documento_giusto(ambiente):
    trovati = cerca_per_codice(ambiente.qdrant, "che significa PAP 21?", "Torino")
    assert trovati and trovati[0]["nome"] == "Simbolo PAP"
    assert trovati[0]["per_codice"] == "PAP 21"


def test_un_codice_inesistente_non_trova_nulla(ambiente):
    assert cerca_per_codice(ambiente.qdrant, "PAP 99", "Torino") == []


def test_reindicizzare_non_duplica(ambiente):
    prima = ambiente.qdrant.count(COLLEZIONE).count
    indicizza(ambiente.qdrant, ambiente.documenti, ambiente.vettorizzatore,
              avanzamento=lambda *_: None)
    assert ambiente.qdrant.count(COLLEZIONE).count == prima


def test_la_verifica_passa_su_un_indice_corretto(ambiente):
    falliti = [d for ok, d in verifica(ambiente.documenti, ambiente.qdrant,
                                       ambiente.vettorizzatore, campione=5) if not ok]
    assert not falliti, falliti


def test_la_verifica_si_accorge_dei_vettori_disallineati(ambiente):
    """Conteggi giusti ma vettore invertito: solo l'autorecupero se ne accorge."""
    from qdrant_client import models

    from ecoscan.db.vettorizza import NOME_VETTORE

    # si sceglie un documento di Torino: Napoli ne ha troppo pochi perché "fra i primi 3"
    # possa fallire, e il test non proverebbe nulla
    punti = ambiente.qdrant.scroll(COLLEZIONE, scroll_filter=filtro("Torino"), limit=50,
                                   with_vectors=True, with_payload=True)[0]
    punto = punti[0]
    ambiente.qdrant.upsert(COLLEZIONE, points=[models.PointStruct(
        id=punto.id, vector={NOME_VETTORE: [-x for x in punto.vector[NOME_VETTORE]]},
        payload=punto.payload)])
    descrizioni = [d for ok, d in verifica(ambiente.documenti, ambiente.qdrant,
                                           ambiente.vettorizzatore, campione=20) if not ok]
    assert any("autorecupero" in d for d in descrizioni)


def test_apri_qdrant_distingue_url_e_percorso(tmp_path):
    locale = apri_qdrant(str(tmp_path / "q"))
    assert locale._client.__class__.__name__ == "QdrantLocal"
    locale.close()
