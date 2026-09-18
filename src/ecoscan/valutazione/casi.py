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

**Da dove vengono i casi.** Due sorgenti, nello stesso formato:

- `manuale` — scritti a mano in `data/valutazione/casi.jsonl`, versionati in git. Sono i
  casi che descrivono cosa il sistema *deve* saper fare, compresi quelli nati da un errore
  osservato;
- `riscontro` — generati dai giudizi degli utenti sulle risposte vere (il pollice su e giù
  dell'interfaccia). Vivono in `data/valutazione/da_riscontri.jsonl`, non versionato,
  perché cresce da sé e dipende da chi ha usato l'applicazione.

Tenerli separati serve: i primi sono un contratto che decidiamo noi, i secondi un campione
di ciò che succede davvero. Si misurano insieme, ma solo i primi si discutono in revisione.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ecoscan.agente.tipi import Riconoscimento
from ecoscan.percorsi import DATI

CARTELLA = DATI / "valutazione"
CASI_MANUALI = CARTELLA / "casi.jsonl"
CASI_DA_RISCONTRI = CARTELLA / "da_riscontri.jsonl"


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
    origine: str = "manuale"               # manuale | riscontro
    nota: str = ""

    @property
    def id(self) -> str:
        """Identifica il caso senza dipendere da un contatore: due file che crescono in
        parallelo non si scontrano, e un caso ripetuto si riconosce."""
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


def caso_da_riscontro(riscontro: dict) -> Caso | None:
    """Il giudizio di un utente diventa un caso, quando dice abbastanza da essere rieseguito.

    Un riscontro è utile alla valutazione solo se porta con sé **un'attesa**: dove la
    risposta doveva andare a finire. Da qui le tre strade:

    - pollice su → l'attesa sono le destinazioni che il sistema ha dato. Fissa un
      comportamento giusto perché non regredisca: è il caso di non-regressione;
    - pollice giù con un'alternativa → l'attesa è quella dell'utente. È il caso più
      prezioso, perché nasce da un errore vero;
    - pollice giù senza alternativa → `None`. Sapere che una risposta è sbagliata senza
      sapere quale fosse quella giusta non si può misurare: resta nel registro grezzo dei
      riscontri, da leggere a mano, ma non entra nel dataset.

    Il `motivo` "oggetto_sbagliato" è a parte: il difetto sta nel riconoscimento, cioè
    proprio nel passaggio che i casi tengono fermo. Un caso costruito su un oggetto
    sbagliato misurerebbe recupero e scelta su una domanda che non era quella giusta.

    Il riconoscimento si ripesca dal `contesto`, ed è ciò che rende il caso rieseguibile
    senza la foto: materiali, categoria e stato erano l'input vero della cascata.
    """
    contesto = riscontro.get("contesto") or {}
    riconosciuto = contesto.get("riconoscimento") or {}
    oggetto = (riscontro.get("oggetto") or riconosciuto.get("oggetto") or "").strip()
    comune = (riscontro.get("comune") or contesto.get("comune") or "").strip()
    if not oggetto or not comune:
        return None

    corretta = bool(riscontro.get("corretta"))
    attesa = (riscontro.get("destinazione_attesa") or "").strip()
    if corretta:
        attese = [d for d in (riscontro.get("destinazioni_date") or []) if d]
    elif riscontro.get("motivo") == "oggetto_sbagliato":
        return None
    elif attesa:
        attese = [attesa]
    else:
        return None
    if not attese:
        return None

    motivo = riscontro.get("motivo") or ("confermata" if corretta else "corretta dall'utente")
    nota = " — ".join(filter(None, [motivo, (riscontro.get("nota") or "").strip()]))
    return Caso(comune=comune, oggetto=oggetto, destinazioni_attese=attese,
                categoria=riconosciuto.get("categoria"),
                materiali=list(riconosciuto.get("materiali") or []),
                stato=riconosciuto.get("stato"),
                sinonimi=list(riconosciuto.get("sinonimi") or []),
                testo_utente=contesto.get("testo_utente"),
                origine="riscontro", nota=nota)


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
    """I casi manuali più quelli nati dai riscontri, senza duplicati.

    Se lo stesso caso esiste in entrambi, vince il manuale: è quello che abbiamo deciso noi,
    e il riscontro potrebbe portare un'attesa sbagliata dell'utente.
    """
    cartella = cartella or CARTELLA
    manuali = leggi(cartella / CASI_MANUALI.name)
    visti = {c.id for c in manuali}
    da_riscontri = [c for c in leggi(cartella / CASI_DA_RISCONTRI.name) if c.id not in visti]
    return [c for c in [*manuali, *da_riscontri] if c.valido]


def aggiungi(caso: Caso, percorso: Path | None = None) -> bool:
    """Accoda un caso, saltandolo se c'è già. Restituisce True se è stato scritto.

    Il controllo dei duplicati evita che dieci pollici su sullo stesso oggetto diventino
    dieci casi identici, che gonfierebbero le percentuali senza misurare niente di nuovo.
    """
    percorso = percorso or CASI_DA_RISCONTRI
    if not caso.valido:
        return False
    if any(c.id == caso.id for c in leggi(percorso)):
        return False
    percorso.parent.mkdir(parents=True, exist_ok=True)
    with open(percorso, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(caso), ensure_ascii=False) + "\n")
    return True
