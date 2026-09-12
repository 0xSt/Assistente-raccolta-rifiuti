"""Test dell'estrattore delle regole di categoria di Torino (pagine 8-12 del Rifiutologo).

I test sul PDF si saltano se il file non è presente; quelli sulla classificazione delle
frasi usano i testi reali osservati nelle schede.
"""
import pytest

from ecoscan.etl.extract_torino_regole import classifica_frase, estrai, valida
from ecoscan.percorsi import PDF_TORINO


@pytest.mark.parametrize("frase, tipo, esclusi", [
    # forma a elenco: il soggetto prima di "NON" elenca gli oggetti esclusi
    ("Medicinali, pile, oli, lampadine e indumenti NON vanno gettati nel rifiuto non recuperabile!",
     "elenco", ["Medicinali", "pile", "oli", "lampadine", "indumenti"]),
    ("Lettiere chimiche per animali, mozziconi, segatura e polvere NON sono rifiuti organici!",
     "elenco", ["Lettiere chimiche per animali", "mozziconi", "segatura", "polvere"]),
    ("Cartoni per bevande (tipo Tetra Pak®), giocattoli, scarpe NON rientrano tra i rifiuti in plastica!",
     "elenco", ["Cartoni per bevande (tipo Tetra Pak®)", "giocattoli", "scarpe"]),
    # forma imperativa: è un'avvertenza, non elenca esclusi
    ("Non gettare pile di tipologia diversa da quelle sopra indicate.", "avvertenza", []),
    ("Non gettare l’olio negli scarichi, potresti causare seri problemi alle tue condutture!",
     "avvertenza", []),
    ("Insieme ai farmaci non gettare la scatola che li contiene.", "avvertenza", []),
    ("", "assente", []),
])
def test_classifica_frase(frase, tipo, esclusi):
    assert classifica_frase(frase) == (tipo, esclusi)


def test_frase_di_forma_nuova_non_viene_separata_a_caso():
    # meglio segnalare che inventare una separazione
    assert classifica_frase("Questa scheda usa una formula mai vista prima") == ("ignota", [])


pdf = pytest.mark.skipif(not PDF_TORINO.exists(), reason="PDF sorgente non presente")


@pytest.fixture(scope="module")
def schede():
    s = estrai(PDF_TORINO)
    valida(s)
    return {x["nome_frazione"]: x for x in s}


@pdf
def test_dieci_schede(schede):
    assert len(schede) == 10
    assert "Carta e cartone" in schede and "Rifiuti ingombranti" in schede


@pdf
def test_carta_ammessi_ed_esclusi(schede):
    regole = schede["Carta e cartone"]["regole"]
    ammessi = [r["testo"] for r in regole if r["polarita"] == "ammesso"]
    esclusi = [r["testo"] for r in regole if r["polarita"] == "escluso"]
    assert "Giornali, riviste, libri, quaderni" in ammessi
    assert esclusi == ["Scontrini", "carta forno", "carta plastificata", "carta con residui di cibo"]


@pdf
def test_schede_descrittive_non_producono_ammessi(schede):
    # Farmaci, Oli esausti e Rifiuti ingombranti hanno solo prosa, non la griglia di celle
    for nome in ("Farmaci", "Oli esausti", "Rifiuti ingombranti"):
        assert not [r for r in schede[nome]["regole"] if r["polarita"] == "ammesso"]
    assert schede["Rifiuti ingombranti"]["descrizione"]


@pdf
def test_le_due_colonne_sono_separate(schede):
    # su p8 le due schede affiancate non devono mescolarsi
    assert schede["Rifiuto non recuperabile"]["colonna"] == "sx"
    assert schede["Carta e cartone"]["colonna"] == "dx"
