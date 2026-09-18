"""Come si scrivono le condizioni e che domanda fanno.

Le condizioni nei dati sono tutte testo in una lista sola, ma non sono tutte della stessa
natura: "sporco" è uno stato dell'oggetto, "piccole quantità" no. Trattarle allo stesso modo
produceva frasi come "Vale se è: piccole quantità" e pulsanti "Utenza domestica" in risposta
alla domanda "com'è il tuo oggetto?".
"""
from ecoscan import condizioni


def test_lo_stato_dell_oggetto_e_il_caso_normale():
    assert condizioni.tipo("sporco") == condizioni.STATO
    assert condizioni.tipo("compostabile certificato") == condizioni.STATO


def test_le_quantita_e_le_utenze_si_riconoscono():
    """Sono i due gruppi che esistono davvero nei dati: 15 quantità e 5 utenze."""
    assert condizioni.tipo("piccole quantità") == condizioni.QUANTITA
    assert condizioni.tipo("grandi quantità") == condizioni.QUANTITA
    assert condizioni.tipo("piccole quantità da lavori domestici") == condizioni.QUANTITA
    assert condizioni.tipo("utenza domestica") == condizioni.UTENZA


def test_la_domanda_cambia_con_la_natura_della_condizione():
    assert "l'oggetto è" in condizioni.domanda(["pulito", "sporco"])
    assert "quanto ne hai" in condizioni.domanda(["piccole quantità", "grandi quantità"])
    assert "chi lo conferisce" in condizioni.domanda(["utenza domestica", "utenza commerciale"])
    assert condizioni.domanda([]) == ""


def test_condizioni_mescolate_usano_la_domanda_piu_generica():
    """Non dire nulla di falso vale più che essere precisi: "com'è" copre tutto."""
    assert "l'oggetto è" in condizioni.domanda(["sporco", "piccole quantità"])


def test_la_frase_non_dice_piu_vale_se_e_piccole_quantita():
    assert condizioni.frase(["unto"]) == "Vale se è unto."
    assert condizioni.frase(["piccole quantità"]) == "Vale per piccole quantità."
    assert condizioni.frase(["utenza domestica"]) == "Vale per utenza domestica."
    assert condizioni.frase([]) == ""


def test_condizioni_di_tipo_diverso_restano_separate():
    """È il caso del polistirolo a Napoli: grandi quantità E utenza domestica."""
    assert condizioni.frase(["grandi quantità", "utenza domestica"]) == \
        "Vale per grandi quantità e per utenza domestica."
    assert condizioni.frase(["sporco", "piccole quantità"]) == \
        "Vale se è sporco e per piccole quantità."


def test_la_premessa_si_innesta_nelle_varianti():
    """Serve alla riga "se è pulito → Carta e cartone" sotto la risposta."""
    assert condizioni.premessa(["pulito"]) == "se è pulito"
    assert condizioni.premessa(["grandi quantità"]) == "per grandi quantità"
    assert condizioni.premessa([]) == ""
