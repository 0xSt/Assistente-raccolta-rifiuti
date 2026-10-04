"""Famiglie di materiali, e quando due si escludono.

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
    """
    dell_oggetto = famiglie_dichiarate(materiali)
    if not dell_oggetto:
        return False
    del_documento = famiglie_nel_testo(testo)
    if not del_documento:
        return False
    return not (del_documento & dell_oggetto)


def dichiarato(testo: str) -> str | None:
    """L'unico materiale nominato da un testo, se ne nomina esattamente uno.

    Un documento che ne nomina due ("Barattolo in metallo o plastica") non distingue niente:
    non serve a formulare una domanda, perché entrambe le risposte porterebbero a lui.
    """
    famiglie = famiglie_nel_testo(testo)
    return famiglie.pop() if len(famiglie) == 1 else None


def distinzione(documenti: list[tuple[str, tuple[str, ...]]]) -> list[str]:
    """I materiali che distinguono documenti omonimi, quando portano in posti diversi.

    Restituisce l'elenco vuoto quando la domanda non servirebbe: un materiale solo, oppure
    più materiali che portano tutti nello stesso contenitore.
    """
    per_famiglia: dict[str, set[str]] = {}
    for nome, destinazioni in documenti:
        if (famiglia_ := dichiarato(nome)) and destinazioni:
            per_famiglia.setdefault(famiglia_, set()).update(destinazioni)
    if len(per_famiglia) < 2:
        return []
    if len({frozenset(d) for d in per_famiglia.values()}) < 2:
        return []
    return sorted(per_famiglia)
