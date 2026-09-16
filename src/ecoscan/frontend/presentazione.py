"""Come una risposta dell'API diventa un messaggio leggibile.

Sta separato dall'interfaccia perché è la parte che si sbaglia più facilmente e che vale la
pena verificare: una regola di esclusione presentata male dice l'opposto del vero, e il
livello di evidenza dev'essere visibile senza che l'utente debba conoscere il progetto.
"""
from __future__ import annotations

VERBO = {"escluso": "**non** va in", "ammesso": "va in"}

SPIEGAZIONE_LIVELLO = {
    1: "Il comune elenca proprio questo oggetto.",
    2: "Il comune non elenca l'oggetto: questa è la regola generale del contenitore.",
    3: "Il comune non dice nulla su questo oggetto.",
}

ETICHETTA_LIVELLO = {1: "voce del dizionario", 2: "regola di categoria", 3: "nessuna regola"}


def titolo(risposta: dict) -> str:
    """La prima riga: dove va, o che non si sa."""
    destinazioni = risposta.get("destinazioni") or []
    if not destinazioni:
        return "Non so dove va questo oggetto."
    verbo = VERBO.get(risposta.get("polarita") or "", "va in")
    oggetto = (risposta.get("oggetto") or "l'oggetto").capitalize()
    return f"{oggetto}: {verbo} **{' oppure '.join(destinazioni)}**"


def corpo(risposta: dict) -> str:
    """Il resto del messaggio: condizioni, avvertenza, livello di evidenza, fonte."""
    righe: list[str] = []

    if condizioni := risposta.get("condizioni"):
        righe.append(f"Vale se è: {', '.join(condizioni)}.")
    if avvertenza := risposta.get("avvertenza"):
        righe.append(f"⚠️ {avvertenza}")

    livello = risposta.get("livello_evidenza", 3)
    righe.append(SPIEGAZIONE_LIVELLO.get(livello, ""))

    if livello == 3:
        righe.append("Puoi controllare sul sito del comune o portarlo a un centro di raccolta.")
    if risposta.get("contraddizione"):
        righe.append("Attenzione: la fonte del comune indica destinazioni diverse per lo "
                     "stesso caso.")
    if chiarimento := risposta.get("chiarimento"):
        righe.append(f"**{chiarimento}**")

    return "\n\n".join(r for r in righe if r)


def nota_fonte(risposta: dict) -> str:
    fonte, riferimento = risposta.get("fonte"), risposta.get("riferimento")
    if not fonte and not riferimento:
        return ""
    livello = ETICHETTA_LIVELLO.get(risposta.get("livello_evidenza", 3), "")
    pezzi = [p for p in (livello, fonte, riferimento) if p]
    return " · ".join(pezzi)


def messaggio(risposta: dict) -> str:
    return "\n\n".join(p for p in (titolo(risposta), corpo(risposta)) if p)


def riassunto_candidati(risposta: dict) -> list[dict]:
    """Righe per la tabella dei candidati: si mostra come l'agente è arrivato alla risposta."""
    return [{
        "livello": c.get("livello"),
        "documento": c.get("testo"),
        "destinazioni": " oppure ".join(c.get("destinazioni") or []) or "-",
        "somiglianza": round(c.get("punteggio") or 0.0, 3),
    } for c in risposta.get("candidati") or []]
