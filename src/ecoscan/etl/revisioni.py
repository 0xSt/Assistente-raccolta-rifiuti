"""Decisioni prese a mano sulle voci che il Transform non sa risolvere da solo.

Il Transform si riesegue ogni volta che ne cambiamo le regole e riscrive il file
normalizzato da zero: una correzione fatta lì dentro andrebbe persa. Le decisioni stanno
quindi in un CSV versionato per comune, che il Transform legge e applica.

Colonne: slug, azione, valore, nota.

| azione         | effetto                                                              |
|----------------|----------------------------------------------------------------------|
| conferma       | la scelta del Transform va bene: la voce non è più da revisionare     |
| non_separare   | la voce NON è composta: niente separazione, il nome resta intero      |
| nome           | sostituisce il nome normalizzato                                     |
| alias          | sostituisce gli alias (più valori separati da ";")                   |
| condizione     | sostituisce le condizioni (più valori separati da ";")               |
| avvertenza     | imposta l'avvertenza (es. il testo di una nota a piè di pagina)       |
| scarta         | la voce non descrive un rifiuto reale: esclusa                        |
| da_decidere    | segnaposto: nessun effetto, la voce resta da revisionare              |

Una decisione su uno slug inesistente fa fallire l'esecuzione: vuol dire che la fonte è
cambiata e la decisione va rivista, non ignorata.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from ecoscan.percorsi import DATI

CARTELLA = DATI / "revisioni"
AZIONI = {"conferma", "non_separare", "nome", "alias", "condizione", "avvertenza", "scarta", "da_decidere"}
SEPARATORE_VALORI = ";"


def percorso(comune: str) -> Path:
    return CARTELLA / f"{comune.lower()}.csv"


def carica(comune: str, file: Path | None = None) -> dict[str, list[dict]]:
    """Decisioni per slug. Restituisce un dizionario vuoto se il file non esiste."""
    file = file or percorso(comune)
    per_slug: dict[str, list[dict]] = defaultdict(list)
    if not file.is_file():
        return per_slug
    with open(file, encoding="utf-8-sig") as fh:
        for riga in csv.DictReader(fh):
            slug, azione = riga["slug"].strip(), riga["azione"].strip()
            if not slug or not azione:
                continue
            if azione not in AZIONI:
                raise ValueError(f"azione non riconosciuta in {file.name}: {azione!r}")
            per_slug[slug].append({"azione": azione, "valore": riga.get("valore", "").strip(),
                                   "nota": riga.get("nota", "").strip()})
    return per_slug


def vietata_separazione(decisioni: list[dict]) -> bool:
    return any(d["azione"] == "non_separare" for d in decisioni)


def applica(voce, decisioni: list[dict]):
    """Applica le decisioni a una voce già trasformata. Restituisce None se va scartata."""
    if not decisioni:
        return voce
    for d in decisioni:
        azione, valore = d["azione"], d["valore"]
        if azione == "scarta":
            return None
        if azione == "nome":
            voce.nome = valore
        elif azione == "alias":
            voce.alias = [v.strip() for v in valore.split(SEPARATORE_VALORI) if v.strip()]
        elif azione == "condizione":
            voce.condizioni = sorted({v.strip() for v in valore.split(SEPARATORE_VALORI) if v.strip()})
        elif azione == "avvertenza":
            voce.avvertenza = valore
    if any(d["azione"] == "da_decidere" for d in decisioni):
        return voce
    voce.da_revisionare = False
    voce.motivi = [f"risolto a mano: {d['nota'] or d['azione']}" for d in decisioni]
    return voce


def verifica_slug(decisioni: dict[str, list[dict]], slug_esistenti: set[str], comune: str) -> None:
    if (orfani := sorted(set(decisioni) - slug_esistenti)):
        raise SystemExit(
            f"Decisioni di revisione su voci inesistenti ({comune}): {orfani}. "
            "La fonte è cambiata: rivedi le decisioni invece di ignorarle.")
