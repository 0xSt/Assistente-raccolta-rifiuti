"""Come si scrive una condizione, e che domanda fa.

Le condizioni di una voce non sono tutte della stessa natura, ma nei dati stanno tutte
nella stessa lista. Tre tipi, contati sul database vero:

- **stato dell'oggetto** — "pulito", "sporco", "unto", "vuoto": la maggioranza. La domanda
  giusta è "com'è il tuo oggetto?";
- **quantità** — "piccole quantità", "grandi quantità" (15 casi): la domanda giusta è
  "quanto ne hai?", e la frase è "vale per piccole quantità", non "vale se è piccole
  quantità";
- **chi conferisce** — "utenza domestica" (5 casi): la domanda è "chi lo butta?".

Trattarle tutte come stati produceva frasi come "Vale se è: piccole quantità" e pulsanti
tipo "Utenza domestica" in risposta a "com'è il tuo oggetto?".

Sta qui, e non nel frontend, perché serve in due punti: la domanda la compone l'agente e la
frase la scrive la presentazione. La classificazione è la stessa, e duplicarla significa
vederla divergere.

Non tocca i dati: `condizione` resta un testo solo nel database. Se un giorno le condizioni
avranno un tipo proprio nel livello normalizzato, questo modulo diventa la sua lettura.
"""
from __future__ import annotations

STATO, QUANTITA, UTENZA = "stato", "quantita", "utenza"

SEGNALI = ((QUANTITA, ("quantità", "quantita")),
           (UTENZA, ("utenza", "domestica", "domestico", "commerciale", "non domestica")))

DOMANDA = {
    STATO: "Per rispondere con certezza devo sapere se l'oggetto è: {opzioni}?",
    QUANTITA: "Per rispondere con certezza devo sapere quanto ne hai: {opzioni}?",
    UTENZA: "Per rispondere con certezza devo sapere chi lo conferisce: {opzioni}?",
}

PREMESSA = {STATO: "se è {condizioni}", QUANTITA: "per {condizioni}",
            UTENZA: "per {condizioni}"}


def tipo(condizione: str) -> str:
    """Di che natura è una condizione. Lo stato è il caso normale, quindi il predefinito."""
    piatta = (condizione or "").lower()
    for etichetta, segnali in SEGNALI:
        if any(s in piatta for s in segnali):
            return etichetta
    return STATO


def tipo_comune(condizioni: list[str]) -> str:
    """Il tipo di un gruppo di condizioni. Se sono mescolate vince lo stato, che è la
    formulazione più generica e non dice nulla di falso."""
    tipi = {tipo(c) for c in condizioni if c}
    return tipi.pop() if len(tipi) == 1 else STATO


def domanda(opzioni: list[str]) -> str:
    """La domanda da fare all'utente per sciogliere il dubbio fra più condizioni."""
    if not opzioni:
        return ""
    return DOMANDA[tipo_comune(opzioni)].format(opzioni=" oppure ".join(opzioni))


def premessa(condizioni: list[str]) -> str:
    """Le condizioni come pezzo di frase: "se è unto", "per grandi quantità".

    Condizioni di tipo diverso restano separate ("per grandi quantità e per utenza
    domestica"): mescolarle in un'apertura sola produceva "vale se è grandi quantità".
    """
    pezzi = []
    for etichetta in (STATO, QUANTITA, UTENZA):
        gruppo = [c for c in condizioni if c and tipo(c) == etichetta]
        if gruppo:
            pezzi.append(PREMESSA[etichetta].format(condizioni=", ".join(gruppo)))
    return " e ".join(pezzi)


def frase(condizioni: list[str]) -> str:
    """Come si scrive la condizione che si è applicata, sotto la risposta."""
    return f"Vale {testo}." if (testo := premessa(condizioni)) else ""
