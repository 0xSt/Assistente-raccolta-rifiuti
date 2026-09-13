"""Trascrizioni manuali: dati presenti nella fonte ma non estraibili in automatico.

Le esclusioni di alcune frazioni di Napoli sono pubblicate solo come grafica dentro
un'immagine. Sono state lette a occhio e trascritte alla lettera in un CSV versionato.

Il CSV registra anche le **assenze verificate**: sapere che una frazione non pubblica
esclusioni è un dato, diverso dal non averle ancora cercate.

Ogni regola che arriva da qui porta `origine: "trascrizione_manuale"`: è affidabile ma
non riproducibile da uno script, e va distinta da ciò che l'estrattore ricava da solo.
"""
from __future__ import annotations

import csv
from pathlib import Path

from ecoscan.percorsi import SORGENTI

TRASCRIZIONE_NAPOLI = SORGENTI / "manuale" / "napoli_esclusioni.csv"
TIPI = {"escluso", "nota", "assenza_verificata"}


def carica_trascrizione(percorso: Path = TRASCRIZIONE_NAPOLI) -> dict[str, dict]:
    """Restituisce, per nome di frazione: regole trascritte e flag di assenza verificata."""
    per_frazione: dict[str, dict] = {}
    if not percorso.is_file():
        return per_frazione
    with open(percorso, encoding="utf-8") as fh:
        for riga in csv.DictReader(fh):
            frazione = riga["frazione"].strip()
            tipo = riga["tipo"].strip()
            if tipo not in TIPI:
                raise ValueError(f"tipo non riconosciuto nella trascrizione: {tipo!r}")
            voce = per_frazione.setdefault(frazione, {"regole": [], "assenza_verificata": False,
                                                      "fonte": riga["fonte"], "data": riga["data"]})
            if tipo == "assenza_verificata":
                voce["assenza_verificata"] = True
                voce["motivo_assenza"] = riga["note"]
            else:
                voce["regole"].append({"polarita": tipo, "testo": riga["testo"].strip(),
                                       "dettaglio": None, "origine": "trascrizione_manuale"})
    return per_frazione


def applica(frazioni: list[dict], trascrizione: dict[str, dict] | None = None) -> list[dict]:
    """Aggiunge alle frazioni estratte le regole trascritte a mano. Non sostituisce nulla."""
    trascrizione = carica_trascrizione() if trascrizione is None else trascrizione
    for fr in frazioni:
        for regola in fr["regole"]:
            regola.setdefault("origine", "estrazione")
        voce = trascrizione.get(fr["nome_frazione"])
        fr["assenza_esclusioni_verificata"] = bool(voce and voce["assenza_verificata"])
        if not voce:
            continue
        fr["regole"].extend(voce["regole"])
        if voce["regole"]:
            fr["trascrizione_manuale"] = {"fonte": voce["fonte"], "data": voce["data"]}
    return frazioni
