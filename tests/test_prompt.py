"""Test dei prompt come file versionati.

Il punto: ogni traccia deve poter dire QUALE prompt ha prodotto un risultato. Se qualcuno
modifica un prompt senza alzare la versione, l'impronta cambia comunque.
"""
import pytest

from ecoscan import prompt as prompt_


def test_i_prompt_necessari_esistono():
    nomi = {p.nome for p in prompt_.tutti()}
    assert {"riconoscimento", "scelta"} <= nomi


@pytest.mark.parametrize("nome", ["riconoscimento", "scelta"])
def test_ogni_prompt_dichiara_versione_e_scopo(nome):
    p = prompt_.carica(nome)
    assert p.versione and p.scopo and p.testo
    assert not p.testo.startswith("#")   # le intestazioni non finiscono nel prompt inviato


def test_l_etichetta_identifica_versione_e_contenuto():
    p = prompt_.carica("scelta")
    assert p.etichetta == f"scelta@{p.versione}:{p.impronta}"


def test_l_impronta_cambia_col_contenuto():
    diverso = prompt_.Prompt("x", "1", "", "un altro testo", "")
    assert prompt_.carica("scelta").impronta != diverso.impronta


def test_il_prompt_di_riconoscimento_non_chiede_la_destinazione():
    """Il modello di visione non conosce le regole del comune: se gliele chiedessimo,
    inventerebbe (D9)."""
    testo = prompt_.carica("riconoscimento").testo.lower()
    assert "non dire dove va buttato" in testo


def test_il_prompt_di_scelta_vincola_ai_candidati():
    testo = prompt_.carica("scelta").testo.lower()
    assert "solo fra le voci elencate" in testo and "0" in testo


def test_prompt_inesistente_segnalato():
    with pytest.raises(FileNotFoundError):
        prompt_.carica("inventato")


def test_il_prompt_di_scelta_vieta_la_corrispondenza_per_solo_materiale():
    """Scegliere "molletta di plastica" per un sandalo perché entrambi sono di plastica è
    l'errore osservato nella prima prova su foto vere."""
    testo = prompt_.carica("scelta").testo.lower()
    assert "non un oggetto dello stesso materiale" in testo
    assert "rispondi con numero 0" in testo and "meglio dire" in testo


def test_la_versione_del_prompt_di_scelta_e_avanzata():
    """Il prompt è stato corretto dopo le prove su foto reali: la versione deve dirlo."""
    assert int(prompt_.carica("scelta").versione) >= 2
