"""Come si smaltisce, non solo dove.

Per un terzo del dizionario di Napoli la risposta "va in X" è vera e insufficiente. 195
voci su 578 finiscono in un'isola ecologica, 86 a un ecopunto itinerante, 57 chiedono una
prenotazione telefonica: dire il nome del contenitore, lì, non basta a far compiere il
gesto. Manca il *come*.

**Il dato che serve c'è già**: `destinazione.canale` distingue `raccolta_ordinaria`,
`ritiro_domicilio`, `contenitore_dedicato`, `raccolta_itinerante`, `centro_raccolta`. Non
sono cinque etichette, sono **cinque gesti diversi**. La procedura si attacca al canale, non
alla singola destinazione: nove coppie (comune, canale) invece di 902 voci, scritte a mano
una volta e versionate in git.

**Lo sforzo ordina le alternative.** 115 voci di Napoli hanno destinazioni su più canali, e
non sono equivalenti per chi deve muoversi: buttare nel sacco è diverso dal caricare un
microonde in macchina. Il campo `sforzo` le ordina, dalla più comoda alla più faticosa,
così l'utente legge prima ciò che può fare da casa.

**Cosa NON c'è qui, di proposito.** Nessun indirizzo, nessun orario, nessun numero di
telefono. Sono dati che invecchiano e che il progetto non ha ancora estratto dalla fonte:
inventarli sarebbe peggio che ometterli, perché una procedura sbagliata manda una persona a
un cancello chiuso. La colonna `da_verificare` dichiara cosa manca, voce per voce, ed è la
lista di lavoro per quando i luoghi entreranno nei dati.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ecoscan.percorsi import SORGENTI

PROCEDURE = SORGENTI / "manuale" / "procedure.csv"

# Il canale della raccolta ordinaria non ha bisogno di spiegazioni: tutti sanno cos'è un
# sacco. Mostrare una procedura anche lì trasformerebbe ogni risposta in un elenco puntato.
ORDINARIO = "raccolta_ordinaria"


@dataclass(frozen=True)
class Procedura:
    """Come si conferisce a un canale, in un comune."""

    comune: str
    canale: str
    sforzo: int                 # 1 = da casa, 5 = ci devi andare tu
    titolo: str
    destinazione: str = ""      # vuoto = vale per tutto il canale; altrimenti specializza
    passi: list[str] = field(default_factory=list)
    nota: str = ""
    da_verificare: str = ""

    @property
    def da_casa(self) -> bool:
        return self.sforzo <= 2


def _righe(percorso: Path) -> list[Procedura]:
    if not percorso.is_file():
        return []
    procedure = []
    with open(percorso, encoding="utf-8", newline="") as fh:
        for riga in csv.DictReader(fh):
            passi = [p.strip() for p in (riga.get("passi") or "").split("|") if p.strip()]
            procedure.append(Procedura(
                comune=(riga["comune"] or "").strip(), canale=(riga["canale"] or "").strip(),
                destinazione=(riga.get("destinazione") or "").strip(),
                sforzo=int(riga.get("sforzo") or 9), titolo=(riga.get("titolo") or "").strip(),
                passi=passi, nota=(riga.get("nota") or "").strip(),
                da_verificare=(riga.get("da_verificare") or "").strip()))
    return procedure


@lru_cache(maxsize=1)
def tutte(percorso: Path = PROCEDURE) -> tuple[Procedura, ...]:
    """Le procedure conosciute. Si leggono una volta: il file cambia solo a mano."""
    return tuple(_righe(percorso))


def per(comune: str, canale: str, destinazione: str | None = None) -> Procedura | None:
    """La procedura di un canale, specializzata sulla destinazione quando esiste.

    **Perché serve la specializzazione.** La procedura sta sul canale e non sulla voce
    (D166): nove coppie invece di 902 righe, ed è la scelta giusta per quasi tutto. Ma un
    canale può raccogliere contenitori che si usano in modi diversi: sotto
    `contenitore_dedicato` stanno farmaci, pile, abiti e olio esausto, e la procedura
    generica finiva per elencarli tutti e quattro, con la nota dell'olio attaccata anche a
    una cintura di pelle. Informazione non richiesta in una risposta è rumore che toglie
    credito a quella richiesta.

    La riga con la destinazione vince; quella senza resta come ripiego per i contenitori che
    non hanno bisogno di istruzioni proprie. Così si specializza solo dove serve, e
    l'economia di D166 non si perde.
    """
    comune, canale = (comune or "").strip().lower(), (canale or "").strip().lower()
    bersaglio = (destinazione or "").strip().lower()
    candidate = [p for p in tutte()
                 if p.comune.lower() == comune and p.canale.lower() == canale]
    specifica = next((p for p in candidate if p.destinazione.lower() == bersaglio and bersaglio), None)
    return specifica or next((p for p in candidate if not p.destinazione), None)


def per_canali(comune: str, canali: list, con_ordinario: bool = False) -> list[Procedura]:
    """Le procedure dei canali indicati, dalla più comoda alla più faticosa.

    L'ordine è il messaggio: chi legge deve trovare per prima l'alternativa che può fare da
    casa, e solo dopo quella che gli chiede di prendere la macchina.

    La raccolta ordinaria si omette quando ci sono altri canali, perché è l'unica che non
    ha bisogno di essere spiegata e occuperebbe il posto di quella che invece sì.
    """
    visti, trovate = set(), []
    for voce in canali:
        # un elemento può essere il solo canale o la coppia (canale, destinazione): la
        # seconda forma serve a specializzare, la prima resta valida per chi non ce l'ha
        canale, destinazione = voce if isinstance(voce, tuple) else (voce, None)
        if (canale, destinazione) in visti:
            continue
        visti.add((canale, destinazione))
        if (procedura := per(comune, canale, destinazione)) is not None and procedura not in trovate:
            trovate.append(procedura)
    if not con_ordinario and any(p.canale != ORDINARIO for p in trovate):
        trovate = [p for p in trovate if p.canale != ORDINARIO]
    return sorted(trovate, key=lambda p: (p.sforzo, p.canale))


def di_ripiego(comune: str) -> Procedura | None:
    """Cosa resta da dire quando il comune non copre l'oggetto (livello 3).

    "Non lo so" è una risposta onesta ma inutile: chi ha l'oggetto in mano deve comunque
    buttarlo da qualche parte. Il centro di raccolta accetta le tipologie che il dizionario
    non elenca, e indicarlo non è indovinare la destinazione — è dire dove si chiede.
    """
    return per(comune, "centro_raccolta")
