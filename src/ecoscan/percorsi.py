"""Percorsi del progetto, indipendenti dalla cartella da cui si lancia il comando.

La radice è quella che contiene pyproject.toml; si può forzare con la variabile
d'ambiente ECOSCAN_RADICE (utile in container o nei job pianificati).
"""
from __future__ import annotations

import os
from pathlib import Path


def radice_progetto() -> Path:
    if (env := os.environ.get("ECOSCAN_RADICE")):
        return Path(env).expanduser().resolve()
    for partenza in (Path.cwd(), Path(__file__).resolve().parent):
        for cartella in (partenza, *partenza.parents):
            if (cartella / "pyproject.toml").is_file():
                return cartella
    return Path.cwd()


RADICE = radice_progetto()
DATI = RADICE / "data"
SORGENTI = DATI / "sorgenti"
GREZZO = DATI / "grezzo"
CACHE = DATI / "cache"
SCHEMA_SQL = Path(__file__).resolve().parent / "db" / "schema.sql"
PDF_TORINO = SORGENTI / "Rifiutologo_AMIAT_2025_x_sito.pdf"
