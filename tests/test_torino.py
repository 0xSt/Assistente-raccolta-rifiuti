"""Test di regressione dell'estrattore Torino sul PDF reale (saltati se il PDF non è presente)."""
import pytest

from ecoscan.etl.extract_torino import estrai, valida
from ecoscan.percorsi import PDF_TORINO as PDF

pytestmark = pytest.mark.skipif(not PDF.exists(), reason="PDF sorgente non presente in data/sorgenti/")


@pytest.fixture(scope="module")
def voci():
    righe, _ = estrai(PDF)
    valida(righe)
    return {r["voce_originale"]: r["destinazioni_alternative"] for r in righe}


def test_numero_voci(voci):
    assert len(voci) == 324


@pytest.mark.parametrize("voce, attese", [  # coppie verificate a vista sulle pagine del PDF
    ("Divani", "rifiuti_ingombranti|centro_di_raccolta"),
    ("Tappi di sughero", "centro_di_raccolta|organico"),
    ("Cartone da pizza pulito", "carta_e_cartone"),
    ("Cartone da pizza sporco (solo se certificato compostabile)", "organico"),
    ("Bicchieri di cristallo", "rifiuto_non_recuperabile"),
    ("Bicchieri di vetro", "vetro_e_imballaggi_metallo"),
    ("Capsule del caffè in plastica senza residui", "imballaggi_plastica"),
    ("Pile e batterie", "centro_di_raccolta|pile"),
    ("Coperte, plaid e trapunte", "centro_di_raccolta|abiti"),
])
def test_coppie_note(voci, voce, attese):
    assert voci[voce] == attese
