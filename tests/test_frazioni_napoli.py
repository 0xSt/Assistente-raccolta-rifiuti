"""Test delle pagine frazione di Napoli.

La fixture riproduce la struttura REALE osservata sulla pagina del Vetro (12/09/2026):
gli ammessi sono <strong> sotto un'immagine, gli esclusi un elenco puntato <ul><li>.
È la differenza di markup che faceva restituire zero esclusioni alla prima versione.
"""
from ecoscan.etl.extract_napoli import parse_pagina_frazione

PAGINA_VETRO = """
<html><body>
<h1>Vetro</h1>
<h2>Il contenitore per la raccolta del Vetro è contraddistinto dal colore <b>VERDE</b></h2>
<h4>SI</h4>
<h3>Cosa differenziare nel contenitore del Vetro</h3>
<div><img src="Bottiglie.png"><strong>Bottiglie</strong></div>
<div><img src="Bottiglie-rotte.png"><strong>Bottiglie rotte</strong></div>
<div><img src="Barattoli.png"><strong>Barattoli e Vasetti</strong><br>(anche piccoli)</div>
<h4>Svuotare gli imballaggi in vetro e metterli sfusi nei contenitori</h4>
<h4>NO</h4>
<h3>Cosa non differenziare nel contenitore del Vetro</h3>
<ul>
  <li>Lastre di vetro</li><li>Tazze e tazzine</li><li>Bicchieri</li>
  <li>Pirofile</li><li>Piatti</li>
</ul>
<h4>Devi buttare qualcosa ma non sai dove? Scrivi qui il tipo di rifiuto e scoprilo</h4>
<ul><li><a href="/servizi/">Servizi</a></li></ul>
</body></html>
"""


def frazione():
    return parse_pagina_frazione(PAGINA_VETRO, "https://www.asianapoli.it/x/vetro/")


def test_nome_e_colore():
    fr = frazione()
    assert fr["nome_frazione"] == "Vetro" and fr["colore"] == "verde"


def test_ammessi():
    ammessi = {r["testo"]: r["dettaglio"] for r in frazione()["regole"] if r["polarita"] == "ammesso"}
    assert set(ammessi) == {"Bottiglie", "Bottiglie rotte", "Barattoli e Vasetti"}
    assert ammessi["Barattoli e Vasetti"] == "(anche piccoli)"


def test_esclusi_dall_elenco_puntato():
    esclusi = [r["testo"] for r in frazione()["regole"] if r["polarita"] == "escluso"]
    assert esclusi == ["Lastre di vetro", "Tazze e tazzine", "Bicchieri", "Pirofile", "Piatti"]


def test_menu_di_navigazione_escluso():
    # l'elenco dopo "Devi buttare qualcosa..." è un menu: non deve diventare una regola
    assert all("Servizi" not in r["testo"] for r in frazione()["regole"])


PAGINA_PLASTICA = """
<html><body>
<h1>Plastica e Metalli</h1>
<h2>Il contenitore per la raccolta della Plastica è contraddistinto dal colore <b>GIALLO</b></h2>
<h4>SI</h4>
<h3>Cosa differenziare nel contenitore della Plastica</h3>
<div><img src="/uploads/2024/09/Bottiglie.png"><strong>Bottiglie e flaconi in plastica</strong></div>
<h4>Piatti e bicchieri in plastica possono essere anche sporchi ma svuotati di ogni residuo</h4>
<img src="https://www.asianapoli.it/wp-content/uploads/2024/09/info-plastica.png">
<h4>Devi buttare qualcosa ma non sai dove?</h4>
</body></html>
"""


def test_frazione_senza_sezione_esclusi():
    # su Plastica, Umido e Carta la sezione "NO" non esiste: le esclusioni sono
    # disegnate dentro un'immagine informativa, quindi non estraibili come testo
    fr = parse_pagina_frazione(PAGINA_PLASTICA, "")
    assert [r["polarita"] for r in fr["regole"]] == ["ammesso"]
    assert fr["immagini_informative"] == [
        "https://www.asianapoli.it/wp-content/uploads/2024/09/info-plastica.png"]


def test_immagini_di_contenuto_non_sono_informative():
    # le immagini degli oggetti ammessi non vanno confuse con l'immagine delle esclusioni
    assert frazione()["immagini_informative"] == []


def test_note_senza_etichette_grafiche():
    note = frazione()["note"]
    assert any("Svuotare gli imballaggi" in n for n in note)
    assert "SI" not in note and "NO" not in note  # sono etichette della sezione, non note
