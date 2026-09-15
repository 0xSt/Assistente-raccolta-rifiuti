"""Test della preparazione delle immagini.

Le foto degli smartphone arrivano grandi, a volte con canale alfa o in scala di grigi: qui
si verifica che vengano ricondotte a una forma sola prima di partire verso il modello.
"""
import io

import pytest
from PIL import Image

from ecoscan.agente.immagini import informazioni, prepara


def immagine(larghezza, altezza, modo="RGB", formato="PNG") -> bytes:
    uscita = io.BytesIO()
    Image.new(modo, (larghezza, altezza), color=(200, 30, 30) if modo == "RGB" else 128).save(
        uscita, format=formato)
    return uscita.getvalue()


def test_informazioni_legge_formato_e_dimensioni():
    info = informazioni(immagine(640, 480))
    assert (info.formato, info.larghezza, info.altezza, info.modo) == ("PNG", 640, 480, "RGB")


def test_una_foto_grande_viene_rimpicciolita():
    ridotta = informazioni(prepara(immagine(4000, 3000), lato_max=1024))
    assert max(ridotta.larghezza, ridotta.altezza) == 1024
    assert ridotta.formato == "JPEG"


def test_le_proporzioni_restano():
    ridotta = informazioni(prepara(immagine(4000, 2000), lato_max=1000))
    assert (ridotta.larghezza, ridotta.altezza) == (1000, 500)


def test_una_foto_piccola_non_viene_ingrandita():
    """Interpolare pixel inventati non aggiunge informazione."""
    ridotta = informazioni(prepara(immagine(300, 200), lato_max=1024))
    assert (ridotta.larghezza, ridotta.altezza) == (300, 200)


@pytest.mark.parametrize("modo", ["RGBA", "L", "P"])
def test_ogni_modo_diventa_rgb(modo):
    """Un canale alfa o una scala di grigi possono essere interpretati male dal modello."""
    assert informazioni(prepara(immagine(100, 100, modo=modo))).modo == "RGB"


def test_il_peso_cala_sensibilmente():
    grande = immagine(3000, 2000)
    assert len(prepara(grande, lato_max=1024)) < len(grande) / 2
