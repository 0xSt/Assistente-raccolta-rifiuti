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
nell'agente (D72).

**Da dove vengono i casi.** Da `data/valutazione/casi.jsonl`, scritti a mano e versionati
in git. Sono un contratto: descrivono cosa il sistema *deve* saper fare, e ogni riga si
discute come si discute una riga di codice. Ogni volta che si osserva un errore vero, il
primo gesto è scriverlo lì: da quel momento quella regressione non ripassa inosservata.

Una sorgente sola è una scelta, non una mancanza. Un dataset di valutazione vale quanto
vale l'autorità delle sue attese, e un'attesa che nessuno ha esaminato fa più danno di un
caso mancante: "corregge" un sistema che funziona (D171, il caso del frullatore). Se in
futuro si aggiungerà una seconda sorgente — casi derivati dagli alias del dizionario,
casi estratti dalle tracce — starà in un file suo e con una sua percentuale, perché
mescolare attese di autorità diversa in un numero solo lo rende illeggibile.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ecoscan.agente.tipi import Riconoscimento
from ecoscan.percorsi import DATI

CARTELLA = DATI / "valutazione"
CASI = CARTELLA / "casi.jsonl"


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
    def valido(self) -> bool:
        """Un caso senza oggetto o senza attesa non misura niente."""
        return bool(self.oggetto.strip() and self.comune.strip() and self.destinazioni_attese)


def leggi(percorso: Path) -> list[Caso]:
    if not percorso.is_file():
        return []
    casi = []
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        if riga.strip():
            campi = {k: v for k, v in json.loads(riga).items() if k in Caso.__annotations__}
            casi.append(Caso(**campi))
    return casi


def tutti(cartella: Path | None = None) -> list[Caso]:
    """I casi da eseguire, senza duplicati e senza quelli che non misurano nulla."""
    casi = leggi((cartella or CARTELLA) / CASI.name)
    visti, unici = set(), []
    for caso in casi:
        if caso.valido and caso.id not in visti:
            visti.add(caso.id)
            unici.append(caso)
    return unici


def aggiungi(caso: Caso, percorso: Path | None = None) -> bool:
    """Accoda un caso, saltandolo se c'è già. Restituisce True se è stato scritto."""
    percorso = percorso or CASI
    if not caso.valido or any(c.id == caso.id for c in leggi(percorso)):
        return False
    percorso.parent.mkdir(parents=True, exist_ok=True)
    with open(percorso, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(caso), ensure_ascii=False) + "\n")
    return True
