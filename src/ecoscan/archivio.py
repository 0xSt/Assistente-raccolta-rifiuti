"""Leggere e scrivere i file del progetto: JSONL, JSON, e l'apertura del database.

Erano quattro implementazioni della stessa riga di `json.loads` — in `db/carica.py`, in
`ispeziona.py`, in `valutazione/casi.py` e in `valutazione/foto.py`, le ultime due identiche
campo per campo — e tre copie parola per parola dello stesso messaggio d'errore sul
database mancante. Il nucleo è condiviso; quello che **non** si condivide è la politica sul
file assente, perché è diversa di proposito:

- chi **costruisce** (il caricamento) tratta un file mancante come un insieme vuoto: un
  comune di cui non si sono ancora estratti i dati non deve far fallire il caricamento
  degli altri;
- chi **ispeziona o misura** si ferma e dice quale comando produce il file che manca: lì un
  insieme vuoto sarebbe un riepilogo di zero righe, cioè una risposta sbagliata travestita
  da risposta.

Sta al primo livello del pacchetto, e non sotto `db/`, perché lo usano anche la valutazione
e gli ispettori, e perché il frontend non deve poter importare `ecoscan.db` (c'è un test che
lo verifica).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, TypeVar

from ecoscan.percorsi import DB

T = TypeVar("T")


def _righe(percorso: Path) -> list[dict]:
    return [json.loads(r) for r in percorso.read_text(encoding="utf-8").splitlines() if r.strip()]


def leggi_jsonl(percorso: Path) -> list[dict]:
    """Le righe di un JSONL. Un file che non c'è è un insieme vuoto."""
    return _righe(percorso) if percorso.is_file() else []


def esigi_jsonl(percorso: Path, comando: str) -> list[dict]:
    """Le righe di un JSONL, fermandosi se il file non c'è e dicendo chi lo produce."""
    if not percorso.is_file():
        raise SystemExit(f"File non trovato: {percorso}\nLancia prima: uv run {comando}")
    return _righe(percorso)


def da_jsonl(tipo: type[T], percorso: Path, **aggiunte: Any) -> list[T]:
    """Un JSONL letto come dataclass, scartando i campi che il tipo non conosce.

    Lo scarto è voluto: i file dei casi e delle foto portano anche note e campi di lavoro
    che non appartengono al tipo, e un campo in più non deve far fallire la lettura di un
    dataset scritto a mano.
    """
    fuori = []
    for riga in leggi_jsonl(percorso):
        campi = {k: v for k, v in riga.items() if k in tipo.__annotations__}
        fuori.append(tipo(**{**aggiunte, **campi}))
    return fuori


def apri_database(percorso: Path | None = None, sola_lettura: bool = True) -> sqlite3.Connection:
    """Il database relazionale, fermandosi con un messaggio utile se non c'è.

    In sola lettura per difetto: chi interroga non deve poter scrivere, e una connessione
    `mode=ro` lo rende un fatto invece di una buona intenzione. Il caricamento, che il
    database lo ricostruisce, passa `sola_lettura=False`.
    """
    percorso = percorso or DB
    if not percorso.is_file():
        raise SystemExit(f"Database non trovato: {percorso}\nLancia prima: uv run ecoscan-carica")
    if not sola_lettura:
        return sqlite3.connect(percorso)
    return sqlite3.connect(f"file:{percorso}?mode=ro", uri=True)


def salva_json(percorso: Path, corpo: Any) -> Path:
    """Scrive un JSON leggibile, creando la cartella se manca. Restituisce il percorso."""
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(corpo, ensure_ascii=False, indent=2), encoding="utf-8")
    return percorso
