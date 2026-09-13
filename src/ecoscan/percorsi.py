"""Percorsi del progetto, indipendenti dalla cartella da cui si lancia il comando.

La radice è quella che contiene pyproject.toml; si può forzare con la variabile
d'ambiente ECOSCAN_RADICE (utile in container o nei job pianificati).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values


def radice_progetto() -> Path:
    if (env := os.environ.get("ECOSCAN_RADICE")):
        return Path(env).expanduser().resolve()
    for partenza in (Path.cwd(), Path(__file__).resolve().parent):
        for cartella in (partenza, *partenza.parents):
            if (cartella / "pyproject.toml").is_file():
                return cartella
    return Path.cwd()


RADICE = radice_progetto()

def carica_impostazioni(radice: Path = RADICE) -> dict[str, str]:
    """Porta nell'ambiente le impostazioni del file .env (vedi .env.example).

    Una variabile già presente nell'ambiente vince sul file: è ciò che permette a Docker di
    sovrascriverla senza toccare il disco. Una variabile presente ma **vuota** conta come
    assente, altrimenti basterebbe un `ECOSCAN_X=` lasciato in giro per far ignorare il file
    in silenzio.

    ECOSCAN_RADICE fa eccezione e resta solo una variabile vera: serve a trovare il .env.
    """
    applicate = {}
    for chiave, valore in dotenv_values(radice / ".env").items():
        if valore is None or os.environ.get(chiave, "").strip():
            continue
        os.environ[chiave] = valore
        applicate[chiave] = valore
    return applicate


carica_impostazioni()
DATI = RADICE / "data"
SORGENTI = DATI / "sorgenti"
GREZZO = DATI / "grezzo"
CACHE = DATI / "cache"
SCHEMA_SQL = Path(__file__).resolve().parent / "db" / "schema.sql"
PDF_TORINO = SORGENTI / "Rifiutologo_AMIAT_2025_x_sito.pdf"
