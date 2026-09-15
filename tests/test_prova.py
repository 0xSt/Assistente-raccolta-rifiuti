"""Test del comando di prova dell'agente.

Del comando si può verificare senza Ollama tutto ciò che riguarda i controlli d'ingresso e
la presentazione: che i messaggi d'errore siano utili e che la risposta venga mostrata senza
ribaltarne il significato.
"""
import pytest

from ecoscan.agente.prova import main, stampa_riconoscimento, stampa_risposta
from ecoscan.agente.tipi import Candidato, Riconoscimento, Risposta


def esegui(argomenti, monkeypatch):
    monkeypatch.setattr("sys.argv", ["ecoscan-analizza", *argomenti])
    with pytest.raises(SystemExit) as uscita:
        main()
    return str(uscita.value)


def test_serve_una_foto_o_un_oggetto(monkeypatch):
    assert "serve --foto oppure --oggetto" in esegui(["--comune", "Torino"], monkeypatch)


def test_foto_inesistente_segnalata(monkeypatch):
    messaggio = esegui(["--foto", "assente.jpg", "--comune", "Torino"], monkeypatch)
    assert "foto non trovata" in messaggio


def test_database_mancante_spiega_cosa_fare(tmp_path, monkeypatch):
    messaggio = esegui(["--oggetto", "x", "--comune", "Torino", "--db", str(tmp_path / "no.db")],
                       monkeypatch)
    assert "ecoscan-carica" in messaggio


def test_la_polarita_non_viene_ribaltata_nella_stampa(capsys):
    """Una regola di esclusione deve leggersi come divieto, non come indicazione."""
    stampa_risposta(Risposta(livello_evidenza=2, comune="Torino", oggetto="tetrapak",
                             destinazioni=["imballaggi_plastica"], polarita="escluso",
                             motivo="regola di categoria"))
    uscita = capsys.readouterr().out
    assert "NON va in: imballaggi_plastica" in uscita


def test_il_livello_3_dice_che_il_comune_non_copre(capsys):
    stampa_risposta(Risposta(livello_evidenza=3, comune="Napoli", motivo="nessuna regola"))
    assert "nessuna destinazione" in capsys.readouterr().out


def test_il_chiarimento_e_evidenziato(capsys):
    stampa_risposta(Risposta(livello_evidenza=1, comune="Torino", destinazioni=["organico"],
                             chiarimento="È vuota o con residui?"))
    uscita = capsys.readouterr().out
    assert "DA CHIEDERE" in uscita and "definitiva:  no" in uscita


def test_i_candidati_mostrano_livello_e_provenienza(capsys):
    stampa_risposta(Risposta(livello_evidenza=1, comune="Torino", destinazioni=["organico"],
                             candidati=[Candidato(1, 1, "Bucce di frutta", nome="Bucce",
                                                  destinazioni=["organico"],
                                                  posizioni={"lessicale": 1, "semantica": 2})]))
    uscita = capsys.readouterr().out
    assert "L1" in uscita and "lessicale #1" in uscita and "semantica #2" in uscita


def test_il_riconoscimento_mostra_la_query_usata(capsys):
    stampa_riconoscimento(Riconoscimento(oggetto="bottiglia", materiali=["vetro"],
                                         stato="vuota", confidenza=0.8))
    uscita = capsys.readouterr().out
    assert "query usata: 'bottiglia vetro vuota'" in uscita and "0.80" in uscita


def test_la_diagnostica_parte_senza_toccare_il_database(monkeypatch, capsys):
    """La diagnostica del canale immagine non ha bisogno né del database né di una foto:
    deve poter girare anche su un'installazione appena montata."""
    from ecoscan.agente import diagnostica

    monkeypatch.setattr(diagnostica, "esegui", lambda modello, url: [(True, f"finto su {modello}")])
    assert esegui(["--diagnostica"], monkeypatch) == "0"
    assert "finto su" in capsys.readouterr().out


def test_la_diagnostica_usa_il_modello_indicato(monkeypatch, capsys):
    from ecoscan.agente import diagnostica

    visti = []
    monkeypatch.setattr(diagnostica, "esegui",
                        lambda modello, url: visti.append(modello) or [(True, "ok")])
    esegui(["--diagnostica", "--modello", "gemma3:4b"], monkeypatch)
    assert visti == ["gemma3:4b"]


def test_la_diagnostica_fallita_esce_con_codice_1(monkeypatch):
    from ecoscan.agente import diagnostica

    monkeypatch.setattr(diagnostica, "esegui", lambda modello, url: [(False, "canale rotto")])
    assert esegui(["--diagnostica"], monkeypatch) == "1"
