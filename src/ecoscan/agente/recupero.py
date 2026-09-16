"""Dai documenti ai candidati, e dalla condizione dichiarata alla variante giusta.

La ricerca restituisce **documenti**: un oggetto con tutte le sue varianti, oppure una
regola di categoria. Il modello sceglie l'oggetto, che è il compito in cui è bravo; la
variante la sceglie il codice in base a ciò che l'utente ha detto, o la si chiede.

Tutto ciò che serve a rispondere è nel payload del documento: destinazioni, condizioni,
avvertenza, fonte. Non c'è più nessuna lettura aggiuntiva dal relazionale.
"""
from __future__ import annotations

import re

from ecoscan.agente.tipi import Candidato, Riconoscimento, Variante
from ecoscan.db.vettorizza import cerca, cerca_per_codice

# Le fonti nominano lo stesso stato con parole diverse: Napoli scrive "unto", Torino
# "sporco". Poche equivalenze, verificate sui dati dei due comuni.
CONDIZIONI_EQUIVALENTI = {
    "unto": {"sporco"},
    "sporco": {"unto"},
    "pulito": {"non unto", "non sporco"},
    "vuoto": {"senza residuo", "senza residui"},
    "pieno": {"con residuo", "con residui"},
    "con residuo": {"pieno", "sporco", "unto"},
    "senza residuo": {"vuoto", "pulito"},
}


def radice(parola: str) -> str:
    """Toglie la vocale finale alle parole lunghe: l'utente scrive al plurale e la fonte
    al singolare ("non utilizzabili" contro "non utilizzabile")."""
    return parola[:-1] if len(parola) >= 5 and parola[-1] in "aeio" else parola


def _radicalizza(testo: str) -> str:
    return " ".join(radice(p) for p in re.findall(r"[a-z0-9]+", (testo or "").lower()))


def menzionata(condizione: str, noto: str) -> bool:
    """La condizione compare nel testo, tenendo conto della negazione.

    "unto" NON è menzionata in "non unto": senza questo controllo le due varianti di un
    oggetto sarebbero indistinguibili proprio quando l'utente è stato più preciso.
    """
    testo = _radicalizza(noto)
    if not testo:
        return False
    base = (condizione or "").lower().strip()
    for variante in {base, *CONDIZIONI_EQUIVALENTI.get(base, set())}:
        c = _radicalizza(variante)
        if not c or c not in testo:
            continue
        if c.startswith("non ") or f"non {c}" not in testo:
            return True
    return False


def candidati(qdrant, vettorizzatore, domande: list[str], comune: str, livello: int,
              k: int = 8) -> list[Candidato]:
    """Una ricerca per ogni domanda, i risultati uniti senza duplicati.

    Nessuna fusione da tarare: i documenti già trovati non si ripetono, gli altri si
    accodano. Con documenti per oggetto bastano poche domande.
    """
    trovati: dict[str, Candidato] = {}
    for domanda in (d for d in domande if d and d.strip()):
        for payload in cerca_per_codice(qdrant, domanda, comune, k=2):
            if payload.get("livello") == livello:
                trovati.setdefault(payload["id"], Candidato.da_payload(payload))
        for payload in cerca(qdrant, domanda, comune, vettorizzatore, livello=livello, k=k):
            trovati.setdefault(payload["id"], Candidato.da_payload(payload))
    return list(trovati.values())[:k + 4]


def scegli_variante(candidato: Candidato, testi: list[str | None]) -> tuple[Variante | None, list[str]]:
    """La variante che corrisponde a ciò che sappiamo, e le condizioni ancora in gioco.

    Se l'oggetto ha una variante sola, non c'è nulla da decidere. Se ne ha più d'una e
    l'utente ha dichiarato la condizione, si prende quella: "è unto" manda il cartone
    nell'organico e quello pulito nella carta, ed è la differenza che dà senso all'app.
    Se nessuna corrisponde, le condizioni tornano indietro per farne una domanda.
    """
    varianti = candidato.varianti
    if not varianti:
        return None, []
    if len(varianti) == 1:
        return varianti[0], []

    noto = " ".join(t for t in testi if t)
    for variante in varianti:
        if variante.condizioni and all(menzionata(c, noto) for c in variante.condizioni):
            return variante, []
    for variante in varianti:
        if any(menzionata(c, noto) for c in variante.condizioni):
            return variante, []

    # nessuna corrisponde: si chiede, elencando le alternative come le scrive la fonte
    condizioni = [v.condizione or "nessuna condizione" for v in varianti]
    return None, condizioni
