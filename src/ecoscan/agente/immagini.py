"""Preparazione delle immagini prima di mandarle al modello.
- si converte in **RGB**, perché una PNG con canale alfa o in scala di grigi può essere
  interpretata male;
- si ridimensiona il lato lungo a una misura nota;
- si ricodifica in JPEG, che a parità di contenuto pesa molto meno di una PNG fotografica.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from ecoscan import configurazione as conf

# Qualita' JPEG: 85 e' il punto in cui il file smette di calare sensibilmente e gli
# artefatti non sono ancora visibili. Non e' un parametro perche' nessuno ha mai avuto
# motivo di cambiarla, e un parametro mai passato e' una promessa che nessuno mantiene.
QUALITA = 85


@dataclass(frozen=True)
class Informazioni:
    formato: str
    larghezza: int
    altezza: int
    modo: str
    byte: int

    def __str__(self) -> str:
        return (f"{self.formato} {self.larghezza}x{self.altezza} {self.modo}, "
                f"{self.byte / 1024:.0f} KB")


def informazioni(dati: bytes) -> Informazioni:
    with Image.open(io.BytesIO(dati)) as immagine:
        return Informazioni(immagine.format or "?", immagine.width, immagine.height,
                            immagine.mode, len(dati))


def prepara(dati: bytes, lato_max: int | None = None) -> bytes:
    """Restituisce un JPEG RGB con il lato lungo non superiore a `lato_max`.

    Se l'immagine è già più piccola non viene ingrandita: interpolare pixel inventati non
    aggiunge informazione.
    """
    lato_max = lato_max or conf.LATO_MAX_IMMAGINE
    with Image.open(io.BytesIO(dati)) as immagine:
        immagine = immagine.convert("RGB")
        if max(immagine.size) > lato_max:
            immagine.thumbnail((lato_max, lato_max), Image.LANCZOS)
        uscita = io.BytesIO()
        immagine.save(uscita, format="JPEG", quality=QUALITA, optimize=True)
        return uscita.getvalue()
