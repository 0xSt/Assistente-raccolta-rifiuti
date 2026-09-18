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


def test_il_prompt_di_scelta_chiede_di_dichiarare_il_tipo_di_corrispondenza():
    """Scegliere "molletta di plastica" per un sandalo perché entrambi sono di plastica è
    l'errore osservato nelle prove su foto vere. Il modello deve dichiarare che tipo di
    corrispondenza ha trovato, così il codice può scartare quelle che non valgono."""
    testo = prompt_.carica("scelta").testo.lower()
    for tipo in ("stesso_oggetto", "sinonimo", "categoria", "solo_materiale", "nessuna"):
        assert tipo in testo
    assert "numero 0" in testo and "meglio dire" in testo


def test_il_prompt_di_riconoscimento_chiede_i_sinonimi():
    """Sono il ponte fra il vocabolario del modello e quello della fonte."""
    testo = prompt_.carica("riconoscimento").testo.lower()
    assert "sinonimi" in testo and "categoria" in testo


def test_le_versioni_dei_prompt_sono_avanzate():
    """I prompt sono stati corretti dopo le prove su foto reali: le versioni devono dirlo."""
    assert int(prompt_.carica("scelta").versione) >= 5
    assert int(prompt_.carica("riconoscimento").versione) >= 3


def test_il_prompt_di_riconoscimento_avverte_dei_nomi_ambigui():
    """"Ciabatta" in italiano è sia una calzatura sia un tipo di pane, e il modello ha
    scelto il significato sbagliato."""
    testo = prompt_.carica("riconoscimento").testo.lower()
    assert "ambiguo" in testo and "ciabatta" in testo


def test_il_prompt_di_scelta_rende_vincolante_la_categoria():
    testo = prompt_.carica("scelta").testo.lower()
    assert "categoria" in testo and "vincolante" in testo
    assert "non reinterpretare" in testo


def test_il_prompt_di_scelta_evita_gli_oggetti_vicini_ma_diversi():
    """Per un sandalo il modello aveva scelto "Stivali": stessa famiglia, oggetto diverso."""
    testo = prompt_.carica("scelta").testo.lower()
    assert "stessa famiglia" in testo and "stivali" in testo
    assert int(prompt_.carica("scelta").versione) >= 5


def test_il_riconoscimento_da_priorita_alle_parole_dell_utente():
    """Il modello aveva riconosciuto "scatola" davanti a un cartone della pizza, ignorando
    l'utente che aveva scritto "è unto"."""
    testo = prompt_.carica("riconoscimento").testo.lower()
    assert "vince sulla tua impressione" in testo
    assert "cartone della pizza" in testo and "scatola" in testo
    assert int(prompt_.carica("riconoscimento").versione) >= 4


def test_il_prompt_di_scelta_preferisce_la_voce_specifica_e_lo_stato():
    """A Torino il modello ha scelto "Scatole in cartone" per un cartone della pizza unto."""
    testo = prompt_.carica("scelta").testo.lower()
    assert "scegli la specifica" in testo and "cartone da pizza" in testo
    assert "stato" in testo and int(prompt_.carica("scelta").versione) >= 6


def test_il_prompt_di_scelta_copre_i_nomi_collettivi():
    """Osservato su foto vera: per una forchetta d'acciaio il modello aveva "Stoviglie in
    metallo" fra i candidati e rispondeva "nessuna". Una voce che nomina un insieme copre
    ogni oggetto dell'insieme, e va scelta invece di rinunciare."""
    testo = prompt_.carica("scelta").testo.lower()
    assert "insieme" in testo and "stoviglie" in testo
    assert "forchetta di acciaio la voce giusta è \"stoviglie in metallo\"" in testo


def test_il_prompt_di_scelta_limita_quando_dire_nessuna():
    """"Nessuna" non deve diventare la risposta comoda: vale quando l'elenco parla d'altro,
    non quando la voce è più larga dell'oggetto."""
    testo = prompt_.carica("scelta").testo.lower()
    assert "non che la voce è più generica" in testo
    assert int(prompt_.carica("scelta").versione) >= 8


def test_il_prompt_di_scelta_rifiuta_i_fratelli():
    """Caso del microonde: il modello aveva scelto "Bistecchiera elettrica" dichiarando
    `categoria`, motivandola con "è un elettrodomestico, come il microonde". Il "come" è la
    spia: descrive una somiglianza fra pari, non un'appartenenza."""
    testo = prompt_.carica("scelta").testo.lower()
    assert "fratello" in testo
    assert "bistecchiera" in testo, "senza controesempio la definizione da sola non basta"
    assert "contiene" in testo


def test_la_categoria_e_definita_come_contenimento():
    testo = prompt_.carica("scelta").testo.lower()
    assert "la voce contiene l'oggetto" in testo
