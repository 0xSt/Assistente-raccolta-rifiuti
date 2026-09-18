"""I prompt vivono come file di testo versionati in git, non come stringhe nel codice.

Ogni file comincia con righe di commento che ne dichiarano versione e scopo:

    # versione: 1
    # scopo: ...

Questo permette di registrare in ogni traccia *quale* prompt ha prodotto un risultato.
Quando una risposta peggiora, la domanda "cosa era cambiato nel prompt" ha una risposta,
e il confronto fra due versioni è un diff.

L'impronta è calcolata sul contenuto: se qualcuno modifica un prompt senza alzare la
versione, l'impronta cambia lo stesso e la differenza resta visibile.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
INTESTAZIONE = re.compile(r"^#\s*(\w+)\s*:\s*(.+)$")


@dataclass(frozen=True)
class Prompt:
    nome: str
    versione: str
    scopo: str
    testo: str
    impronta: str

    @property
    def etichetta(self) -> str:
        """Identificatore compatto da registrare nelle tracce: `scelta@1:6f3a1c2d`."""
        return f"{self.nome}@{self.versione}:{self.impronta}"


@cache
def carica(nome: str) -> Prompt:
    percorso = CARTELLA / f"{nome}.txt"
    if not percorso.is_file():
        raise FileNotFoundError(f"prompt non trovato: {percorso}")
    grezzo = percorso.read_text(encoding="utf-8")

    intestazioni: dict[str, str] = {}
    corpo: list[str] = []
    for riga in grezzo.splitlines():
        if not corpo and (m := INTESTAZIONE.match(riga)):
            intestazioni[m.group(1).lower()] = m.group(2).strip()
        elif riga.strip() or corpo:
            corpo.append(riga)

    testo = "\n".join(corpo).strip()
    if "versione" not in intestazioni:
        raise ValueError(f"il prompt {nome} non dichiara la versione (riga '# versione: N')")
    return Prompt(nome=nome, versione=intestazioni["versione"],
                  scopo=intestazioni.get("scopo", ""), testo=testo,
                  impronta=hashlib.sha256(testo.encode("utf-8")).hexdigest()[:8])


def tutti() -> list[Prompt]:
    return [carica(f.stem) for f in sorted(CARTELLA.glob("*.txt"))]
