"""Dai documenti ai candidati, e dalla condizione dichiarata alla variante giusta.

Il recupero è un **oggetto con un'interfaccia** (`Recupero`), non una funzione legata a
Qdrant: l'agente dichiara cosa gli serve — dei candidati, dato un elenco di domande, un
comune e un livello — e non sa da dove arrivino. Oggi l'unica implementazione è
`RecuperoQdrant`; una ricerca ibrida, o un doppio finto nei test, si aggiungono come
implementazioni alternative senza toccare l'agente.

La ricerca restituisce **documenti**: un oggetto con tutte le sue varianti, oppure una
regola di categoria. Il modello sceglie l'oggetto, che è il compito in cui è bravo; la
variante la sceglie il codice in base a ciò che l'utente ha detto, o la si chiede.

Tutto ciò che serve a rispondere è nel payload del documento: destinazioni, condizioni,
avvertenza, fonte. Non c'è più nessuna lettura aggiuntiva dal relazionale.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

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


# Preposizioni e articoli: non dicono nulla sull'oggetto. "cartone della pizza" e "Cartone
# per pizze" sono lo stesso oggetto, e differiscono solo per una di queste parole.
PAROLE_DI_SERVIZIO = {"dell", "della", "del", "dei", "degli", "delle", "dal", "dalla",
                      "nel", "nella", "sul", "sulla", "con", "per", "tra", "fra", "una",
                      "uno", "gli", "che", "cui", "questo", "questa", "sono", "essere"}


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


class Recupero(Protocol):
    """Da cosa cerchiamo a cosa abbiamo trovato.

    È tutto ciò che l'agente pretende dal recupero: un nome con cui dire nelle tracce quale
    strategia era in uso, e dei candidati per un comune e un livello di evidenza.
    """

    @property
    def nome(self) -> str: ...

    def candidati(self, domande: list[str], comune: str, livello: int,
                  k: int = 8) -> list[Candidato]: ...


@dataclass
class RecuperoQdrant:
    """Ricerca semantica su Qdrant, con aggancio esatto dei codici materiale.

    Una ricerca per ogni domanda, i risultati uniti senza duplicati: nessuna fusione da
    tarare, i documenti già trovati non si ripetono e gli altri si accodano. Con documenti
    per oggetto bastano poche domande.
    """

    qdrant: object
    vettorizzatore: object

    @property
    def nome(self) -> str:
        return f"qdrant:{getattr(self.vettorizzatore, 'nome', '?')}"

    def candidati(self, domande: list[str], comune: str, livello: int,
                  k: int = 8) -> list[Candidato]:
        trovati: dict[str, Candidato] = {}
        for domanda in (d for d in domande if d and d.strip()):
            self._aggancia_codici(trovati, domanda, comune, livello)
            self._cerca_per_somiglianza(trovati, domanda, comune, livello, k)
        # ordinati per somiglianza: il modello legge un elenco, e l'ordine è un'informazione
        ordinati = sorted(trovati.values(), key=lambda c: (c.per_codice is None, -c.punteggio))
        return ordinati[:k + 4]

    def _aggancia_codici(self, trovati: dict[str, Candidato], domanda: str, comune: str,
                         livello: int) -> None:
        """Un codice materiale scritto sull'oggetto ("PAP 21") è una corrispondenza esatta:
        vale più di qualunque somiglianza, e precede i risultati semantici."""
        for payload in cerca_per_codice(self.qdrant, domanda, comune, k=2):
            if payload.get("livello") == livello:
                trovati.setdefault(payload["id"], Candidato.da_payload(payload))

    def _cerca_per_somiglianza(self, trovati: dict[str, Candidato], domanda: str, comune: str,
                               livello: int, k: int) -> None:
        for payload in cerca(self.qdrant, domanda, comune, self.vettorizzatore,
                             livello=livello, k=k):
            esistente = trovati.get(payload["id"])
            if esistente is None:
                trovati[payload["id"]] = Candidato.da_payload(payload)
            else:
                # lo stesso documento trovato da più domande: vale il punteggio migliore
                esistente.punteggio = max(esistente.punteggio, payload.get("punteggio", 0.0))


def nomina_l_oggetto(candidato: Candidato, riconoscimento: Riconoscimento,
                     testo_utente: str | None = None) -> bool:
    """Il documento nomina proprio l'oggetto riconosciuto?

    "Cartone della pizza" e "Cartone per pizze" condividono le parole che contano; "Cartone
    da imballaggio" no. Serve a preferire il documento specifico a quello generico, che è
    l'errore che il modello continua a fare.
    """
    nome = _radicalizza(candidato.nome or candidato.testo.split(".")[0])
    for testo in (riconoscimento.oggetto, testo_utente):
        parole = [p for p in _radicalizza(testo or "").split()
                  if len(p) >= 4 and p not in PAROLE_DI_SERVIZIO]
        if parole and all(p in nome for p in parole):
            return True
    return False


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

    # Nessuna corrisponde: si chiede, elencando le condizioni come le scrive la fonte.
    # Le varianti senza condizione non si nominano: "grandi quantità oppure nessuna
    # condizione?" è una domanda a cui nessuno saprebbe rispondere.
    condizioni = [v.condizione for v in varianti if v.condizione]
    return None, condizioni if len(condizioni) >= 2 else []
