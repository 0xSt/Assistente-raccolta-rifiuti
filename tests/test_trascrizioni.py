"""Test delle trascrizioni manuali (esclusioni di Napoli lette dalle immagini informative)."""
import pytest

from ecoscan.etl.trascrizioni import TRASCRIZIONE_NAPOLI, applica, carica_trascrizione


@pytest.fixture(scope="module")
def trascrizione():
    return carica_trascrizione()


def test_file_presente_e_versionato():
    assert TRASCRIZIONE_NAPOLI.is_file()


def test_esclusioni_umido(trascrizione):
    regole = trascrizione["Umido/Organico"]["regole"]
    esclusi = [r["testo"] for r in regole if r["polarita"] == "escluso"]
    assert esclusi == ["Legno verniciato", "Lettiere per animali", "Liquidi, olio vegetale",
                       "Mozziconi e cenere di sigaretta", "Pannolini e assorbenti",
                       "Tessuti naturali e sintetici"]
    # l'avviso generale in coda all'elenco non è un oggetto escluso
    note = [r["testo"] for r in regole if r["polarita"] == "nota"]
    assert note == ["NON METTERE NESSUN OGGETTO IN PLASTICA"]


def test_assenze_verificate(trascrizione):
    # sapere che una frazione non pubblica esclusioni è un dato, non un'incognita
    assert trascrizione["Plastica e Metalli"]["assenza_verificata"]
    assert trascrizione["Carta e Cartone"]["assenza_verificata"]
    assert not trascrizione["Umido/Organico"]["assenza_verificata"]


def test_origine_distinta(trascrizione):
    assert all(r["origine"] == "trascrizione_manuale" for r in trascrizione["Umido/Organico"]["regole"])


def test_applica_non_sostituisce_le_regole_estratte():
    frazioni = [
        {"nome_frazione": "Umido/Organico", "regole": [{"polarita": "ammesso", "testo": "Bucce"}]},
        {"nome_frazione": "Plastica e Metalli", "regole": [{"polarita": "ammesso", "testo": "Bottiglie"}]},
        {"nome_frazione": "Vetro", "regole": [{"polarita": "escluso", "testo": "Bicchieri"}]},
    ]
    umido, plastica, vetro = applica(frazioni)
    assert umido["regole"][0] == {"polarita": "ammesso", "testo": "Bucce", "origine": "estrazione"}
    assert sum(1 for r in umido["regole"] if r["polarita"] == "escluso") == 6
    assert umido["trascrizione_manuale"]["data"] == "2026-09-12"
    assert plastica["assenza_esclusioni_verificata"] and len(plastica["regole"]) == 1
    # il Vetro non è nella trascrizione: resta com'è, senza assenza verificata
    assert vetro["regole"][0]["origine"] == "estrazione"
    assert not vetro["assenza_esclusioni_verificata"]
