"""I casi di valutazione: cos'è un caso, dove vive, come si legge e si scrive.

Un **caso** è un riconoscimento già avvenuto più la risposta che ci si aspetta:

    {"comune": "Napoli", "oggetto": "forchetta", "materiali": ["acciaio"],
     "destinazioni_attese": ["Plastica e Metalli"], "livello_atteso": 1}

Parte dal riconoscimento e non dalla foto per una ragione precisa: il modello di visione
è il passaggio lento (minuti su CPU) ed è anche quello che vogliamo tenere **fermo** mentre
misuriamo il resto. Se a ogni prova rileggessimo le foto, una differenza nei risultati
potrebbe venire dal recupero, dalla scelta, o dal modello che quel giorno ha visto qualcosa
di diverso: tre cause per un solo effetto. Fissando il riconoscimento, ciò che resta misura
solo recupero e scelta. È lo stesso motivo per cui `analizza` e `rispondi` sono separati
nell'agente (D72). Il riconoscimento si misura a parte, sulle foto (`ecoscan-valuta-foto`).

**Tre insiemi, tre numeri separati.** I casi stanno in `data/valutazione/casi/`, un file
per insieme, e il nome del file è l'origine del caso. Non si mescolano mai in una
percentuale sola, perché hanno autorità e scopi diversi:

| file | cosa contiene | come si legge |
|---|---|---|
| `regressioni.jsonl` | i casi nati da errori osservati | pass/fail: 18 su 18 |
| `campione.jsonl` | un campione stratificato del dizionario | percentuali: è la stima |
| `assenti.jsonl` | oggetti che il comune non copre | le due astensioni |

**Perché il campione esiste.** Le regressioni sono preziose ma sono, per costruzione, i
punti in cui il sistema aveva già sbagliato: una percentuale calcolata lì misura la storia
dei difetti, non il sistema. Il campione è estratto dai dati con `ecoscan-campiona`, quindi
dice quanto funziona *in generale*.

**Perché gli assenti esistono.** Il difetto classico di un sistema RAG è rispondere
comunque. Senza casi la cui risposta giusta è il silenzio, quel difetto non ha un numero e
resta invisibile: un caso "assente" ha `destinazioni_attese` vuote e `livello_atteso: 3`.

**Le attese sono un contratto.** Un dataset vale quanto l'autorità delle sue attese, e
un'attesa che nessuno ha esaminato fa più danno di un caso mancante: "corregge" un sistema
che funziona (D171, il caso del frullatore). Per questo le attese del campione vengono dal
database — cioè dalla fonte ufficiale — e a mano si scrive solo la **domanda**, che è
l'unica parte che una macchina non può inventare.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ecoscan.agente.tipi import Riconoscimento
from ecoscan.percorsi import DATI

CARTELLA = DATI / "valutazione" / "casi"
# l'ordine in cui si leggono, che è anche l'ordine in cui conviene guardarli
INSIEMI = ("regressioni", "campione", "assenti", "chiarimenti")


@dataclass
class Caso:
    """Un riconoscimento e la risposta che ci si aspetta."""

    comune: str
    oggetto: str
    destinazioni_attese: list[str] = field(default_factory=list)
    categoria: str | None = None
    materiali: list[str] = field(default_factory=list)
    stato: str | None = None
    sinonimi: list[str] = field(default_factory=list)
    testo_utente: str | None = None
    livello_atteso: int | None = None      # 1, 2, 3; None = non lo verifichiamo
    nota: str = ""
    origine: str = "regressioni"           # quale insieme: lo decide il nome del file
    voce_fonte: str = ""                   # la voce del dizionario da cui nasce l'attesa
    strato: dict | None = None             # come è stato campionato (comune, canale, ...)
    chiarimento_atteso: bool | None = None # True: deve chiedere. False: non deve. None: non si verifica

    @property
    def id(self) -> str:
        """Identifica il caso senza dipendere da un contatore: un caso ripetuto si
        riconosce anche se le righe vengono riordinate."""
        pezzi = [self.comune, self.oggetto, self.stato or "", self.testo_utente or ""]
        return " · ".join(p for p in pezzi if p)

    @property
    def riconoscimento(self) -> Riconoscimento:
        """Il caso come lo vede l'agente.

        La confidenza è massima perché il riconoscimento qui è un dato, non un'ipotesi:
        vogliamo misurare cosa succede *dopo*, non rieseguire la soglia di confidenza.
        """
        return Riconoscimento(oggetto=self.oggetto, categoria=self.categoria,
                              materiali=list(self.materiali), stato=self.stato,
                              sinonimi=list(self.sinonimi), confidenza=1.0)

    @property
    def negativo(self) -> bool:
        """Un caso senza attese: la risposta giusta è non rispondere.

        Non è un caso incompleto, è il controllo opposto. L'agente deve arrivare al livello
        3 e dire che il comune non copre l'oggetto, invece di indicare il contenitore di
        qualcos'altro che gli somiglia.
        """
        return not self.destinazioni_attese

    @property
    def ambiguo(self) -> bool:
        """Il caso mette alla prova la domanda, in una delle due direzioni.

        Sono due controlli speculari sullo stesso oggetto: uno **senza** dire la condizione,
        dove l'agente deve chiedere; uno **dicendola**, dove deve rispondere e basta. Il
        primo da solo si supererebbe chiedendo sempre, che è il difetto opposto e altrettanto
        inutile — la stessa ragione per cui le astensioni si leggono in coppia.
        """
        return self.chiarimento_atteso is not None

    @property
    def valido(self) -> bool:
        """Un caso senza oggetto o senza attesa non misura niente.

        L'eccezione sono i casi negativi, che l'attesa ce l'hanno e vale il silenzio: lì
        `livello_atteso: 3` è la dichiarazione esplicita che le destinazioni vuote sono
        volute e non una riga scritta a metà.
        """
        if not (self.oggetto.strip() and self.comune.strip()):
            return False
        return bool(self.destinazioni_attese) or self.livello_atteso == 3


def leggi(percorso: Path, origine: str | None = None) -> list[Caso]:
    """Legge un file di casi. L'origine, se non dichiarata nella riga, è il nome del file:
    così l'insieme a cui un caso appartiene non può divergere da dove il caso sta."""
    if not percorso.is_file():
        return []
    casi = []
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        if not riga.strip():
            continue
        campi = {k: v for k, v in json.loads(riga).items() if k in Caso.__annotations__}
        campi.setdefault("origine", origine or percorso.stem)
        casi.append(Caso(**campi))
    return casi


def tutti(cartella: Path | None = None) -> list[Caso]:
    """I casi da eseguire, senza duplicati e senza quelli che non misurano nulla.

    In caso di collisione fra insiemi vince il primo letto, cioè la regressione: è il caso
    discusso a mano, e la sua attesa è quella di cui rispondiamo.
    """
    cartella = cartella or CARTELLA
    casi = [c for insieme in INSIEMI for c in leggi(cartella / f"{insieme}.jsonl", insieme)]
    visti, unici = set(), []
    for caso in casi:
        if caso.valido and caso.id not in visti:
            visti.add(caso.id)
            unici.append(caso)
    return unici


def per_insieme(elementi: list, chiave) -> dict[str, list]:
    """Raggruppa mantenendo l'ordine di `INSIEMI`: le misure si stampano sempre nello
    stesso ordine, così due esecuzioni si confrontano a occhio."""
    gruppi: dict[str, list] = {}
    for elemento in elementi:
        gruppi.setdefault(chiave(elemento), []).append(elemento)
    ordine = {nome: n for n, nome in enumerate(INSIEMI)}
    return dict(sorted(gruppi.items(), key=lambda voce: ordine.get(voce[0], len(INSIEMI))))


def aggiungi(caso: Caso, percorso: Path | None = None) -> bool:
    """Accoda un caso, saltandolo se c'è già. Restituisce True se è stato scritto."""
    percorso = percorso or CARTELLA / f"{caso.origine}.jsonl"
    if not caso.valido or any(c.id == caso.id for c in leggi(percorso)):
        return False
    percorso.parent.mkdir(parents=True, exist_ok=True)
    with open(percorso, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(caso), ensure_ascii=False) + "\n")
    return True
