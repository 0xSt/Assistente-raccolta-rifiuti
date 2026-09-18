"""Famiglie di materiali, e quando due si escludono.

Nasce da un errore osservato: una forchetta d'acciaio a cui il sistema ha risposto "Non
Riciclabile" citando la voce "Forchetta in plastica". Il modello aveva riconosciuto
l'acciaio e l'aveva perfino scritto nel motivo della scelta; nessuno gli ha impedito di
scegliere un documento che dichiarava un materiale diverso.

La regola è una sola: **se il documento dichiara un materiale e l'oggetto ne dichiara un
altro di un'altra famiglia, quel documento non può essere la risposta.** Vale per qualunque
modello, quindi sta nel codice e non nel prompt, come già la politica che scarta le
corrispondenze `solo_materiale`.

Due cautele, perché il riconoscimento può sbagliare:

- si decide solo quando **entrambe** le parti nominano un materiale. Un documento che non
  dice di che materiale è ("Scatolette per tonno") non viene mai escluso;
- un documento che ne nomina più d'uno ("Barattolo in metallo o plastica") è compatibile con
  ciascuno: basta una famiglia in comune.

Le famiglie sono poche e verificate sui dati dei due comuni: contengono le parole che
compaiono davvero nei dizionari di ASIA e AMIAT, non un'ontologia dei materiali.
"""
from __future__ import annotations

import re

FAMIGLIE: dict[str, set[str]] = {
    # I plurali ci sono perché le fonti li usano: il contenitore di Napoli si chiama
    # "Plastica e Metalli", e senza "metalli" un documento che lo nomina sembrerebbe
    # parlare solo di plastica.
    "plastica": {"plastica", "plastiche", "plastico", "polistirolo", "polietilene", "pvc",
                 "pet", "nylon", "plexiglass", "gomma", "gomme", "silicone"},
    "metallo": {"metallo", "metalli", "metallico", "metallica", "metallici", "metalliche",
                "acciaio", "alluminio", "latta", "lattine", "ferro", "ottone", "bronzo",
                "rame", "zinco", "banda stagnata", "inox"},
    "vetro": {"vetro", "vetri", "cristallo"},
    "carta": {"carta", "cartone", "cartoni", "cartoncino", "cartaceo"},
    "legno": {"legno", "legni", "legnoso", "sughero", "bambu", "bambù"},
    "tessuto": {"tessuto", "tessuti", "stoffa", "cotone", "lana", "pelle", "cuoio"},
    "ceramica": {"ceramica", "porcellana", "terracotta", "gres"},
    "compostabile": {"compostabile", "compostabili", "biodegradabile", "biodegradabili",
                     "mater-bi", "mater bi"},
}

# Parola -> famiglia, costruito una volta: le famiglie non cambiano a runtime
_DI_PAROLA = {parola: famiglia for famiglia, parole in FAMIGLIE.items() for parola in parole}
_COMPOSTE = {parola: famiglia for parola, famiglia in _DI_PAROLA.items() if " " in parola}


def famiglia(parola: str) -> str | None:
    """La famiglia di un materiale, o None se la parola non ne nomina uno."""
    return _DI_PAROLA.get((parola or "").strip().lower())


def famiglie_nel_testo(testo: str) -> set[str]:
    """Le famiglie di materiale nominate in un testo libero.

    Il confronto è per parola intera: "cartaceo" non deve nascere da "carta" dentro un'altra
    parola, e "gommone" non deve diventare "gomma".
    """
    piatto = (testo or "").lower()
    trovate = {f for p in re.findall(r"[a-zàèéìòù]+", piatto) if (f := famiglia(p))}
    # le parole composte ("banda stagnata") non compaiono fra i token singoli
    trovate |= {f for parola, f in _COMPOSTE.items() if parola in piatto}
    return trovate


def famiglie_dichiarate(materiali: list[str]) -> set[str]:
    """Le famiglie dichiarate dal riconoscimento. Ogni voce può essere una frase."""
    return {f for m in materiali or [] for f in famiglie_nel_testo(m)}


def incompatibili(testo: str, materiali: list[str]) -> bool:
    """Il documento nomina un materiale, l'oggetto un altro, e non hanno nulla in comune.

    Falso quando una delle due parti tace: non sapere non è una ragione per escludere.
    """
    dell_oggetto = famiglie_dichiarate(materiali)
    if not dell_oggetto:
        return False
    del_documento = famiglie_nel_testo(testo)
    if not del_documento:
        return False
    return not (del_documento & dell_oggetto)
