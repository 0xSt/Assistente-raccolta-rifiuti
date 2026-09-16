"""Test delle sonde sul retrieval.

Le sonde misurano *dove* finisce la scheda attesa. I test verificano la meccanica del
conteggio: la qualità dei risultati si misura eseguendole sui dati veri.
"""
import pytest

from ecoscan.db.sonda import Esito, Sonda, _posizione, carica_sonde, riepilogo


def test_la_sonda_dice_quale_scheda_ha_trovato():
    """Cercando "Scarpe" come sottostringa si accetta "Laccio per scarpe", che è un altro
    oggetto: restituire il testo trovato rende visibile il falso positivo."""
    risultati = [{"testo": "Laccio per scarpe"}, {"testo": "Scarpe utilizzabile"}]
    assert _posizione(risultati, "Scarpe") == (1, "Laccio per scarpe")
    assert _posizione(risultati, "Scarpe utilizz") == (2, "Scarpe utilizzabile")


def test_posizione_assente():
    assert _posizione([{"testo": "Biscotto"}], "Scarpe") == (None, "")
    assert _posizione([], "Scarpe") == (None, "")


def test_il_file_delle_sonde_e_versionato_e_valido():
    sonde = carica_sonde()
    assert len(sonde) >= 25
    assert {s.comune for s in sonde} == {"Napoli", "Torino"}
    assert all(s.domanda and s.atteso for s in sonde)


def test_ogni_sonda_ha_una_nota():
    """Una sonda senza spiegazione, fra sei mesi, non si sa più perché c'era."""
    assert all(s.nota for s in carica_sonde())


def test_le_sonde_coprono_le_famiglie_che_contano():
    """Codici materiale, parafrasi d'uso e controlli facili: senza le prime due il banco
    di prova misura solo i casi comodi; senza i terzi non ci si accorge di una rottura."""
    note = [s.nota.lower() for s in carica_sonde()]
    assert sum("codice materiale" in n for n in note) >= 3
    assert sum("parafrasi" in n for n in note) >= 5
    assert sum("controllo facile" in n for n in note) >= 5


def test_ogni_attesa_corrisponde_a_un_documento_reale():
    """Un'attesa scritta a memoria misura sé stessa: due sonde erano già fallite così."""
    import sqlite3

    from ecoscan.db.documenti import costruisci
    from ecoscan.db.vettorizza import DB

    if not DB.is_file():
        pytest.skip("database non costruito")
    with sqlite3.connect(DB) as db:
        documenti = costruisci(db)
    for sonda in carica_sonde():
        assert any(sonda.atteso.lower() in d.testo.lower()
                   for d in documenti if d.comune == sonda.comune), sonda


def test_migliore_prende_la_posizione_piu_alta():
    esito = Esito(Sonda("Napoli", "x", "y"), {"semantica": 7})
    assert esito.migliore == 7
    assert Esito(Sonda("Napoli", "x", "y"), {"semantica": None}).migliore is None


def test_il_riepilogo_segnala_le_domande_mai_trovate(capsys):
    esiti = [Esito(Sonda("Napoli", "sandalo", "Scarpe"),
                   {"semantica": None}, primo="Salse"),
             Esito(Sonda("Napoli", "bottiglia", "Bottiglia"),
                   {"semantica": 1}, trovato="Bottiglia in plastica")]
    riepilogo(esiti, k=20)
    uscita = capsys.readouterr().out
    assert "Mai trovate" in uscita and "sandalo" in uscita
    assert "al primo posto 1" in uscita


def test_il_riepilogo_mostra_il_primo_risultato_quando_l_attesa_fallisce(capsys):
    """Sapere cosa ha trovato al posto giusto indirizza la correzione."""
    riepilogo([Esito(Sonda("Napoli", "sandalo", "Scarpe utilizzabile"),
                     {"semantica": None}, primo="Salse")], k=20)
    assert "primo: Salse" in capsys.readouterr().out
