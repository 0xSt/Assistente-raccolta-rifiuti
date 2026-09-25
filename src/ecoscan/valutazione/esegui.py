"""Misurare il recupero e la scelta, separatamente.

**Perché separarli.** In un sistema come questo il recupero è un filtro che nessuno può
aggirare: se il documento giusto non è fra i candidati, nessun modello, nessun prompt e
nessuna riformulazione potranno sceglierlo. Il recupero fissa quindi un **tetto** alla
correttezza finale, e la scelta può solo restare sotto quel tetto.

Da qui la struttura della misura. Per ogni caso si guardano due cose:

1. **recupero** — fra i candidati c'è almeno un documento che porta alla destinazione
   attesa? È il classico *recall@k*: non interessa dove sta in classifica, interessa che ci
   sia, perché il modello legge tutto l'elenco. Se manca, il caso è perso in partenza;
2. **risposta** — la destinazione finale è quella attesa?

**Due errori diversi, due numeri diversi.** La risposta non è "giusta o sbagliata": può
sbagliare in due modi che si riparano in punti diversi e che pesano diversamente per chi
usa l'app.

- **contenitore sbagliato** — fra le destinazioni proposte ce n'è una che non è fra le
  attese. È il danno vero: manda una persona al cassonetto sbagliato;
- **canale perso** — le destinazioni proposte sono tutte giuste, ma ne manca una. È
  l'errore di microonde e divano: la risposta diceva "isola ecologica" ed era vera, ma
  taceva il ritiro a domicilio, che era l'alternativa comoda.

L'uguaglianza esatta degli insiemi, usata fino alla v0.42.0, li confondeva in un numero
solo. Oggi sono `contenitore_corretto` (non mandare nessuno nel posto sbagliato) e
`copertura` (non perdere un'alternativa).

Il confronto fra recupero e risposta dice **dove** intervenire, e lo dice da solo:

| recupero | risposta | diagnosi | dove si lavora |
|---|---|---|---|
| ✓ | ✓ | corretto | — |
| ✓ | tutte giuste, ne manca una | canale perso | politiche del codice, presentazione |
| ✓ | ✗ | il documento c'era e non è stato scelto | prompt di scelta, politiche del codice |
| ✗ | ✗ | il documento non è mai arrivato | formulazioni, indice, ricerca |
| ✗ | ✓ | corretto per un'altra strada | da guardare: spesso è il livello 2 |

**I casi negativi** (quelli senza attesa, livello 3) non entrano in questa tabella: lì la
risposta giusta è *non rispondere*, e si misurano con le due astensioni.

**Due modalità, perché costano diversamente.** Il recupero non usa modelli generativi: gira
in secondi e si può lanciare a ogni modifica. La scelta chiama il modello una volta per
livello, quindi è lenta ma molto meno della visione. Con `--senza-modello` si misura solo il
tetto; senza, si misura tutto.

**Il confronto fra due esecuzioni** è ciò che rende la misura utile a decidere: un numero
assoluto dice poco, "due casi guadagnati e uno perso" dice cosa ha fatto la modifica. Ogni
esecuzione salvata porta con sé la configurazione che l'ha prodotta, e il confronto avvisa
se le due non sono confrontabili.

Uso:
  uv run ecoscan-valuta                          # recupero e scelta
  uv run ecoscan-valuta --senza-modello          # solo recupero, in secondi
  uv run ecoscan-valuta --salva esiti/v0.43.json
  uv run ecoscan-valuta --confronta esiti/v0.42.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ecoscan import configurazione as conf
from ecoscan.agente.agente import Agente, Richiesta
from ecoscan.agente.tipi import Candidato
from ecoscan.percorsi import DATI
from ecoscan.valutazione.casi import Caso, per_insieme, tutti

# Le diagnosi possibili, nell'ordine in cui conviene leggerle
CORRETTO = "corretto"
CANALE_PERSO = "contenitore giusto, manca un'alternativa"
SCELTA_SBAGLIATA = "il documento c'era, non è stato scelto"
RECUPERO_FALLITO = "il documento non è stato recuperato"
ALTRA_STRADA = "corretto per un'altra strada"
# Senza modello non si misura la risposta, solo il tetto: chiamarlo "corretto" farebbe
# leggere come una risposta giusta ciò che è soltanto un documento trovato.
RECUPERATO = "documento recuperato (la risposta non è stata valutata)"
# I casi negativi hanno una coppia di diagnosi tutta loro: il successo è il silenzio.
ASTENUTO = "astensione corretta: nessuna regola del comune copre l'oggetto"
NON_ASTENUTO = "ha risposto invece di astenersi"
# La domanda ha una coppia sua, per lo stesso motivo delle astensioni: chiedere sempre e
# non chiedere mai sono due difetti opposti, e un numero solo li confonderebbe.
CORRETTO_CON_DOMANDA = "ha chiesto, come doveva: la destinazione è provvisoria"
MANCATA_DOMANDA = "doveva chiedere la condizione e ha risposto lo stesso"
DOMANDA_INUTILE = "ha chiesto una condizione che l'utente aveva già dichiarato"

# Dove finiscono gli esiti salvati da sé: non versionati (vedi .gitignore)
ESECUZIONI = DATI / "valutazione" / "esecuzioni"


@dataclass
class Esito:
    """Come è andato un caso."""

    caso: Caso
    recuperato: bool                       # recall@k: il documento giusto era fra i candidati
    destinazioni: list[str] = field(default_factory=list)
    livello: int | None = None
    candidati: int = 0
    posizione: int | None = None           # dove stava il primo documento giusto (1-based)
    valutata_la_scelta: bool = True
    raggiungibili: list[str] = field(default_factory=list)   # dove portano i candidati trovati
    chiarimento: str | None = None         # la domanda fatta all'utente, se c'è stata
    opzioni: list[str] = field(default_factory=list)         # le risposte possibili
    scelto: str | None = None              # quale voce ha risposto

    @property
    def contenitore_corretto(self) -> bool | None:
        """Nessuna destinazione proposta è fuori dalle attese, e qualcosa è stato proposto.

        È la metrica che protegge l'utente: un contenitore sbagliato manda una persona a
        buttare il vetro nell'organico, mentre un'alternativa mancante gli fa solo fare più
        strada. `None` quando la scelta non è stata valutata.

        Per un caso negativo il senso si rovescia: è corretto proprio il non rispondere.
        """
        if not self.valutata_la_scelta:
            return None
        if self.caso.negativo:
            return not self.destinazioni
        return bool(self.destinazioni) and set(self.destinazioni) <= set(self.caso.destinazioni_attese)

    @property
    def copertura(self) -> float | None:
        """Quante delle destinazioni attese sono state dette, fra 0 e 1.

        Distingue "va all'isola ecologica" da "va all'isola ecologica **oppure** chiami il
        numero verde e te lo vengono a prendere". Non si applica ai casi negativi, che non
        hanno attese.
        """
        if not self.valutata_la_scelta or self.caso.negativo:
            return None
        attese = set(self.caso.destinazioni_attese)
        return len(set(self.destinazioni) & attese) / len(attese)

    @property
    def ha_chiesto(self) -> bool:
        return bool(self.chiarimento)

    @property
    def dalla_voce_attesa(self) -> bool | None:
        """La risposta è arrivata dalla voce che il caso aveva in mente.

        `None` quando non c'è modo di dirlo: un caso senza `voce_fonte`, o un esito senza
        documento scelto.
        """
        if not (self.caso.voce_fonte and self.scelto):
            return None
        return self.scelto in self.caso.voce_fonte

    @property
    def chiarimento_corretto(self) -> bool | None:
        """Ha chiesto quando doveva, e taciuto quando non serviva.

        `None` quando il caso non lo verifica, quando la scelta non è stata eseguita, o
        quando **ha risposto un'altra voce**. L'ultimo caso è il difetto di attribuzione
        scoperto il 25/09: su undici mancate domande, dieci erano risposte arrivate da una
        voce diversa — «Barattolo in vetro» al posto di «Contenitori creme», «Tende in
        stoffa» al posto di «Pantofole di stoffa». Lì la domanda non era nemmeno in gioco:
        la voce scelta aveva una variante sola e nulla da chiedere. Contarle come domande
        mancate dava la colpa al chiarimento di un difetto della **scelta**.
        """
        if self.caso.chiarimento_atteso is None or not self.valutata_la_scelta:
            return None
        if self.dalla_voce_attesa is False:
            return None
        return self.ha_chiesto == self.caso.chiarimento_atteso

    @property
    def provvisoria(self) -> bool:
        """La risposta è accompagnata da una domanda che era dovuta.

        Non si misura come definitiva: l'agente ha detto "probabilmente X, ma dimmi Y", e
        pretendere che X sia già la risposta completa significherebbe punirlo per aver
        fatto la cosa giusta. Il caso si giudica sulla domanda, non sulla destinazione.
        """
        return bool(self.caso.chiarimento_atteso) and self.chiarimento_corretto is True

    @property
    def perfetta(self) -> bool:
        """Contenitore giusto e nessuna alternativa persa: il vecchio `risposta_corretta`.

        Serve al confronto fra esecuzioni, che deve avere una nozione binaria di "caso
        vinto" per poter dire quanti se ne guadagnano e quanti se ne perdono.
        """
        return bool(self.contenitore_corretto) and (self.copertura is None or self.copertura == 1.0)

    @property
    def livello_corretto(self) -> bool | None:
        """`None` quando non lo sappiamo, non `False`.

        Senza modello il livello non viene mai determinato, e confrontare `None` con
        l'atteso dava `False` per ogni caso: la misura riportava 0% di livelli corretti su
        un'esecuzione in cui il livello non era stato misurato affatto. Una metrica che
        mente è peggio di una metrica che manca, perché la si legge.
        """
        if self.caso.livello_atteso is None or not self.valutata_la_scelta:
            return None
        return self.livello == self.caso.livello_atteso

    @property
    def diagnosi(self) -> str:
        if self.caso.negativo:
            if not self.valutata_la_scelta:
                return RECUPERATO if self.recuperato else ASTENUTO
            return ASTENUTO if self.contenitore_corretto else NON_ASTENUTO
        if not self.valutata_la_scelta:
            return RECUPERATO if self.recuperato else RECUPERO_FALLITO
        if self.chiarimento_corretto is False:
            return MANCATA_DOMANDA if self.caso.chiarimento_atteso else DOMANDA_INUTILE
        if self.provvisoria:
            return CORRETTO_CON_DOMANDA
        if self.perfetta:
            return CORRETTO if self.recuperato else ALTRA_STRADA
        if self.contenitore_corretto:
            return CANALE_PERSO
        return SCELTA_SBAGLIATA if self.recuperato else RECUPERO_FALLITO

    @property
    def mancate(self) -> list[str]:
        """Le destinazioni attese che la risposta non ha detto: il dettaglio del canale perso."""
        return [d for d in self.caso.destinazioni_attese if d not in self.destinazioni]

    @property
    def di_troppo(self) -> list[str]:
        """Le destinazioni proposte che non erano attese: il dettaglio del contenitore sbagliato."""
        return [d for d in self.destinazioni if d not in self.caso.destinazioni_attese]


def porta_alla_destinazione(candidato: Candidato, attese: list[str]) -> bool:
    """Il documento porta a una delle destinazioni attese?

    Basta una destinazione in comune: un oggetto con più varianti ne offre parecchie, e
    quale sia quella giusta lo decide la condizione, non il recupero.
    """
    return bool(set(candidato.destinazioni) & set(attese))


def valuta_caso(agente: Agente, caso: Caso, con_modello: bool = True,
                sessione: str | None = None) -> Esito:
    """Esegue un caso e misura recupero e risposta, dentro una traccia tutta sua.

    Il recupero si misura su **tutti** i livelli, non solo su quello che ha risposto: se la
    voce giusta era al livello 1 e la risposta è arrivata dal 2, vogliamo saperlo.

    **La traccia è il motivo per cui questo non è solo un contatore.** Le percentuali dicono
    quanti casi vanno male; la traccia dice *perché quel caso* è andato male: quali domande
    sono state poste all'indice, quali documenti sono usciti e in che ordine, cosa ha
    risposto il modello e cosa ha scartato la politica dei materiali. È la stessa traccia
    che si registra per una conversazione vera, quindi si legge con gli stessi occhi.
    """
    ingressi = {"caso": caso.id, "comune": caso.comune, "oggetto": caso.oggetto,
                "testo_utente": caso.testo_utente,
                "destinazioni_attese": caso.destinazioni_attese,
                "livello_atteso": caso.livello_atteso, "voce_fonte": caso.voce_fonte}
    with agente.tracciatore.turno("valutazione", sessione or caso.origine, ingressi) as radice:
        esito = _valuta(agente, caso, con_modello)
        radice.uscita({"destinazioni": esito.destinazioni, "livello": esito.livello,
                       "chiarimento": esito.chiarimento, "opzioni": esito.opzioni,
                       "recuperato": esito.recuperato, "posizione": esito.posizione,
                       "candidati": esito.candidati, "diagnosi": esito.diagnosi,
                       "raggiungibili": esito.raggiungibili})
        # i tag, non gli attributi: sui tag l'interfaccia di MLflow filtra, ed è così che
        # dopo una valutazione si aprono le sole tracce dei casi falliti
        agente.tracciatore.etichetta(
            radice, caso=caso.id, insieme=caso.origine, comune=caso.comune,
            diagnosi=esito.diagnosi, recuperato="si" if esito.recuperato else "no",
            posizione=esito.posizione, livello=esito.livello,
            chiede="si" if esito.ha_chiesto else "no", scelto=esito.scelto,
            chiarimento_atteso={True: "si", False: "no"}.get(caso.chiarimento_atteso),
            atteso=" · ".join(caso.destinazioni_attese) or "(nessuna: deve astenersi)")
    return esito


def _valuta(agente: Agente, caso: Caso, con_modello: bool) -> Esito:
    richiesta = Richiesta(caso.riconoscimento, caso.comune, caso.testo_utente)
    trovati: list[Candidato] = []
    for livello in (1, 2):
        trovati.extend(agente.recupera(richiesta, livello))

    posizione = next((i for i, c in enumerate(trovati, start=1)
                      if porta_alla_destinazione(c, caso.destinazioni_attese)), None)

    # dove portano i documenti trovati: senza questo, un caso con l'attesa sbagliata è
    # indistinguibile da un recupero fallito, ed è successo al primo giro (il frullatore)
    raggiungibili: list[str] = []
    for candidato in trovati:
        raggiungibili.extend(d for d in candidato.destinazioni if d not in raggiungibili)

    if not con_modello:
        return Esito(caso=caso, recuperato=posizione is not None, candidati=len(trovati),
                     posizione=posizione, valutata_la_scelta=False,
                     raggiungibili=raggiungibili)

    risposta = agente.rispondi(caso.riconoscimento, caso.comune, caso.testo_utente)
    return Esito(caso=caso, recuperato=posizione is not None, destinazioni=risposta.destinazioni,
                 livello=risposta.livello_evidenza, candidati=len(trovati), posizione=posizione,
                 raggiungibili=raggiungibili, chiarimento=risposta.chiarimento,
                 opzioni=list(risposta.opzioni),
                 # quale voce ha risposto: senza, un caso che si aspettava una voce e ne ha
                 # trovata un'altra sembra un difetto della domanda invece che della scelta
                 scelto=next((c.nome for c in risposta.candidati
                              if c.id == risposta.scelto_id), None))


def esegui(agente: Agente, casi: list[Caso], con_modello: bool = True,
           avanzamento=None, sessione: str | None = None) -> list[Esito]:
    """Esegue i casi. `avanzamento(numero, totale, caso, esito)` viene chiamato **dopo**
    ciascuno, con l'esito già in mano: così la riga di avanzamento può dire com'è andato
    invece di annunciare soltanto cosa sta per fare."""
    esiti = []
    for numero, caso in enumerate(casi, start=1):
        esito = valuta_caso(agente, caso, con_modello, sessione)
        esiti.append(esito)
        if avanzamento:
            avanzamento(numero, len(casi), caso, esito)
    return esiti


class Avanzamento:
    """La riga che dice a che punto siamo.

    Serve più di quanto sembri: anche `--senza-modello`, che sulla carta "gira in secondi",
    calcola un embedding per ogni formulazione di ogni caso — sette domande per due livelli
    — e su CPU diventano minuti. Senza avanzamento sembra bloccato, e la reazione naturale
    è interromperlo proprio mentre sta lavorando.

    Su un terminale vero riscrive sempre la stessa riga; quando l'uscita è rediretta su file
    stampa una riga ogni dieci casi, perché un file pieno di ritorni a capo non si legge.
    """

    def __init__(self, totale: int, interattivo: bool | None = None):
        self.totale = totale
        self.inizio = time.monotonic()
        self.interattivo = sys.stdout.isatty() if interattivo is None else interattivo

    def __call__(self, numero: int, totale: int, caso: Caso, esito: Esito) -> None:
        trascorso = time.monotonic() - self.inizio
        per_caso = trascorso / numero
        mancano = per_caso * (totale - numero)
        segno = "ok" if esito.diagnosi in (CORRETTO, RECUPERATO, ASTENUTO) else "NO"
        riga = (f"  [{numero:3}/{totale}] {segno}  {caso.id[:46]:48} "
                f"{per_caso:.1f} s/caso · {self._resta(mancano)}")
        if self.interattivo:
            print(f"\r{riga[:110]:110}", end="", flush=True)
        elif numero % 10 == 0 or numero == totale:
            print(riga, flush=True)

    @staticmethod
    def _resta(secondi: float) -> str:
        if secondi < 1:
            return "finito"
        if secondi < 90:
            return f"~{secondi:.0f} s alla fine"
        return f"~{secondi / 60:.0f} min alla fine"

    def fine(self) -> float:
        trascorso = time.monotonic() - self.inizio
        if self.interattivo:
            print(f"\r{' ' * 110}\r", end="")
        return trascorso


# --------------------------------------------------------------------------- riepilogo

def soglie_recall(k: int) -> list[int]:
    """I punti in cui si legge la curva del recall: il primo, la metà, il massimo.

    Si derivano da `k` invece di essere fissi, altrimenti lanciare con `-k 20` produrrebbe
    una curva che si ferma a 8 e non direbbe nulla su ciò che si sta provando.
    """
    return sorted({1, max(2, k // 2), k})


def _percentuale(quanti: int, su: int) -> float | None:
    return round(100 * quanti / su, 1) if su else None


def misure(esiti: list[Esito], k: int = 8) -> dict[str, float | int | None]:
    """I numeri che riassumono un'esecuzione.

    Ogni numero ha il **suo** denominatore, e vale `None` quando non è stato misurato:
    le percentuali della scelta si calcolano sui casi in cui la scelta è stata eseguita, le
    astensioni sui soli casi negativi, il recall sui soli casi con un'attesa. Un numero che
    manca si nota; un numero calcolato su un denominatore sbagliato no.
    """
    positivi = [e for e in esiti if not e.caso.negativo]
    negativi = [e for e in esiti if e.caso.negativo]
    con_scelta = [e for e in positivi if e.valutata_la_scelta and not e.provvisoria]
    coperture = [e.copertura for e in con_scelta if e.copertura is not None]
    livelli = [e for e in esiti if e.livello_corretto is not None]

    valori: dict[str, float | int | None] = {"casi": len(esiti)}

    # A) la curva del recall: dove arriva il tetto, e se allargare k servirebbe
    for n in soglie_recall(k):
        valori[f"recall@{n}"] = _percentuale(
            sum(1 for e in positivi if e.posizione and e.posizione <= n), len(positivi))
    # `recupero` resta la percentuale di casi in cui il documento c'era, comunque sia
    # ordinato: coincide con l'ultimo punto della curva, ma non dipende da `posizione`
    valori["recupero"] = _percentuale(sum(1 for e in positivi if e.recuperato),
                                      len(positivi))

    # B) i due errori della risposta, separati
    valori["contenitore_corretto"] = _percentuale(
        sum(1 for e in con_scelta if e.contenitore_corretto), len(con_scelta))
    valori["copertura"] = round(100 * sum(coperture) / len(coperture), 1) if coperture else None
    valori["risposte_perfette"] = _percentuale(
        sum(1 for e in con_scelta if e.perfetta), len(con_scelta))
    valori["livello_atteso"] = _percentuale(
        sum(1 for e in livelli if e.livello_corretto), len(livelli))

    # D) le due astensioni, da leggere in coppia: tacere sempre non è prudenza, è mutismo
    valori["astensione_corretta"] = _percentuale(
        sum(1 for e in negativi if e.contenitore_corretto),
        len([e for e in negativi if e.valutata_la_scelta]))
    valori["astensione_a_sproposito"] = _percentuale(
        sum(1 for e in con_scelta if not e.destinazioni), len(con_scelta))

    # C) le due domande, da leggere in coppia come le astensioni: chiedere sempre e non
    # chiedere mai sono due difetti opposti, e un numero solo li confonderebbe
    # il denominatore sono i casi in cui la domanda era **giudicabile**: la scelta
    # eseguita, e la risposta arrivata dalla voce che il caso aveva in mente
    dovute = [e for e in esiti
              if e.caso.chiarimento_atteso is True and e.chiarimento_corretto is not None]
    inutili = [e for e in esiti
               if e.caso.chiarimento_atteso is False and e.chiarimento_corretto is not None]
    valori["domanda_dovuta"] = _percentuale(sum(1 for e in dovute if e.ha_chiesto), len(dovute))
    valori["domanda_inutile"] = _percentuale(sum(1 for e in inutili if e.ha_chiesto),
                                             len(inutili))
    return valori


ETICHETTE = {
    "recupero": "recupero (il documento giusto è fra i candidati)",
    "contenitore_corretto": "contenitore corretto (nessuna destinazione sbagliata)",
    "copertura": "copertura delle alternative attese",
    "risposte_perfette": "risposte perfette (contenitore giusto e nulla di perso)",
    "livello_atteso": "livello di evidenza atteso",
    "astensione_corretta": "astensione corretta (sui casi non coperti)",
    "astensione_a_sproposito": "astensione a sproposito (sui casi coperti)",
    "domanda_dovuta": "domanda fatta quando serviva (condizione non dichiarata)",
    "domanda_inutile": "domanda fatta quando NON serviva (condizione dichiarata)",
}


def _riga_caso(e: Esito, buone: tuple[str, ...]) -> None:
    segno = "OK" if e.diagnosi in buone else "  "
    posizione = str(e.posizione) if e.posizione else "-"
    print(f"{segno:4} {e.caso.id[:44]:44} {posizione:>5}  {e.diagnosi}")
    if e.diagnosi in buone:
        return
    if e.caso.destinazioni_attese:
        print(f"     atteso:   {', '.join(e.caso.destinazioni_attese)}")
    if e.destinazioni:
        print(f"     ottenuto: {', '.join(e.destinazioni)}")
    # i due errori si leggono senza doverli dedurre confrontando due elenchi
    if e.di_troppo:
        print(f"     di troppo (contenitore sbagliato): {', '.join(e.di_troppo)}")
    elif e.mancate and e.destinazioni:
        print(f"     mancano (canale perso): {', '.join(e.mancate)}")
    if e.scelto and e.caso.voce_fonte and e.scelto not in e.caso.voce_fonte:
        print(f"     ha risposto la voce «{e.scelto}», il caso si aspettava "
              f"«{e.caso.voce_fonte}»")
    if e.caso.chiarimento_atteso is not None:
        atteso = "doveva chiedere" if e.caso.chiarimento_atteso else "non doveva chiedere"
        fatto = f"ha chiesto: «{e.chiarimento}»" if e.ha_chiesto else "non ha chiesto"
        print(f"     {atteso}, {fatto}")
        if e.opzioni:
            print(f"     opzioni offerte: {', '.join(e.opzioni)}")
    # Prima di dare la colpa al recupero, si guarda dove portavano i documenti trovati:
    # se l'attesa non compare da nessuna parte, spesso è l'attesa a essere sbagliata
    if e.raggiungibili and not e.destinazioni:
        print(f"     i documenti trovati portano a: {', '.join(e.raggiungibili[:8])}")
        print("     (se l'attesa non è qui dentro, controlla il caso prima del recupero)")


def _per_strato(esiti: list[Esito], nome: str, chiave) -> None:
    """Il recupero spezzato per comune o per canale.

    La media nasconde che gli ingombranti vanno peggio della raccolta ordinaria: è la
    media a dire "88%", ed è lo strato a dire dove scrivere le prossime formulazioni.
    """
    strati: dict[str, list[Esito]] = {}
    for e in esiti:
        if (valore := chiave(e)):
            strati.setdefault(valore, []).append(e)
    if len(strati) < 2:
        return
    print(f"\n## Recupero per {nome}")
    for valore, gruppo in sorted(strati.items()):
        trovati = sum(1 for e in gruppo if e.recuperato)
        print(f"  {valore:28} {trovati:3}/{len(gruppo):<3} {_percentuale(trovati, len(gruppo))}%")


def riepiloga(esiti: list[Esito], k: int = 8) -> None:
    print(f"\n{'esito':4} {'caso':44} {'pos.':>5}  diagnosi")
    print("-" * 100)
    buone = (CORRETTO, CORRETTO_CON_DOMANDA, RECUPERATO, ASTENUTO)
    for e in sorted(esiti, key=lambda e: (e.diagnosi in buone, e.caso.id)):
        _riga_caso(e, buone)

    for insieme, gruppo in per_insieme(esiti, chiave=lambda e: e.caso.origine).items():
        m = misure(gruppo, k)
        # le regressioni si leggono come pass/fail: sono i casi che NON devono tornare
        # indietro, e una percentuale su diciotto casi scelti apposta non stima niente
        if insieme == "regressioni":
            passati = sum(1 for e in gruppo
                          if e.diagnosi in (CORRETTO, CORRETTO_CON_DOMANDA, RECUPERATO,
                                            ASTENUTO))
            print(f"\n## Regressioni: {passati}/{len(gruppo)} superate")
            continue
        print(f"\n## Misure sull'insieme «{insieme}» ({m['casi']} casi)")
        recall = "  ".join(f"@{n} {m[f'recall@{n}']}%" for n in soglie_recall(k)
                           if m.get(f"recall@{n}") is not None)
        if recall:
            print(f"  recall:                                          {recall}")
        for chiave, etichetta in ETICHETTE.items():
            if chiave != "recupero" and m.get(chiave) is not None:
                print(f"  {etichetta:48} {m[chiave]}%")

    _per_strato([e for e in esiti if not e.caso.negativo], "comune", lambda e: e.caso.comune)
    _per_strato([e for e in esiti if not e.caso.negativo], "canale",
                lambda e: (e.caso.strato or {}).get("canale"))

    altra_voce = [e for e in esiti if e.dalla_voce_attesa is False]
    if altra_voce:
        print(f"\n## Risposte arrivate da un'altra voce: {len(altra_voce)}")
        print("  (la domanda non era in gioco: è la scelta ad aver preso un altro documento)")
        for e in altra_voce[:10]:
            print(f"  {e.caso.id[:44]:46} «{e.scelto}» invece di «{e.caso.voce_fonte[:36]}»")

    print("\n## Dove intervenire")
    for diagnosi in (RECUPERO_FALLITO, SCELTA_SBAGLIATA, CANALE_PERSO, NON_ASTENUTO,
                     MANCATA_DOMANDA, DOMANDA_INUTILE, ALTRA_STRADA):
        quanti = sum(1 for e in esiti if e.diagnosi == diagnosi)
        if quanti:
            print(f"  {quanti:3}  {diagnosi}")


# --------------------------------------------------------------------------- persistenza

def descrizione_esecuzione(agente: Agente, casi: list[Caso], k: int,
                           con_modello: bool) -> dict:
    """Le condizioni in cui la misura è stata presa.

    Senza questo blocco si confrontano due esecuzioni fatte con `k` diversi, o con due
    versioni del prompt di scelta, e si legge la differenza come merito della modifica.
    `agente.configurazione()` è lo stesso oggetto che forma la versione dell'app nelle
    tracce MLflow: valutazione e osservabilità restano allineate per costruzione.
    """
    conteggio: dict[str, int] = {}
    for caso in casi:
        conteggio[caso.origine] = conteggio.get(caso.origine, 0) + 1
    return {"data": datetime.now().isoformat(timespec="minutes"),
            "k": k,
            "modalita": "completa" if con_modello else "senza_modello",
            "casi": conteggio,
            "configurazione": agente.configurazione()}


def come_json(esiti: list[Esito], esecuzione: dict | None = None,
              k: int = 8) -> dict:
    return {"esecuzione": esecuzione or {},
            "misure": misure(esiti, k),
            "esiti": {e.caso.id: {"recuperato": e.recuperato,
                                  "contenitore_corretto": e.contenitore_corretto,
                                  "copertura": e.copertura,
                                  "destinazioni": e.destinazioni, "livello": e.livello,
                                  "posizione": e.posizione, "diagnosi": e.diagnosi,
                                  "chiarimento": e.chiarimento, "scelto": e.scelto}
                      for e in esiti}}


def differenze_di_configurazione(prima: dict, adesso: dict) -> dict[str, tuple]:
    """Cosa è cambiato fra le condizioni di due esecuzioni."""
    vecchia = {**prima.get("configurazione", {}), "k": prima.get("k"),
               "modalita": prima.get("modalita")}
    nuova = {**adesso.get("configurazione", {}), "k": adesso.get("k"),
             "modalita": adesso.get("modalita")}
    return {c: (vecchia.get(c), nuova.get(c)) for c in sorted(set(vecchia) | set(nuova))
            if vecchia.get(c) != nuova.get(c)}


def confronta(prima: dict, adesso: list[Esito], esecuzione: dict | None = None,
              k: int = 8) -> None:
    """Cosa è cambiato rispetto a un'esecuzione salvata.

    È la parte che serve a decidere: un numero assoluto dice poco, "due guadagnati e uno
    perso" dice cosa ha fatto davvero la modifica.
    """
    print("\n## Confronto con l'esecuzione precedente")
    if (differenze := differenze_di_configurazione(prima.get("esecuzione", {}),
                                                   esecuzione or {})):
        # non blocca: a volte confrontare due configurazioni è proprio ciò che si vuole.
        # Deve solo essere detto, o la differenza si attribuisce alla modifica sbagliata.
        print("  ATTENZIONE: le due esecuzioni non sono state fatte nelle stesse condizioni")
        for campo, (vecchio, nuovo) in differenze.items():
            print(f"    {campo}: {vecchio} -> {nuovo}")
        print()

    vecchi = prima.get("esiti", {})
    guadagnati, persi, nuovi = [], [], []
    for e in adesso:
        vecchio = vecchi.get(e.caso.id)
        if vecchio is None:
            nuovi.append(e)
        elif e.diagnosi == CORRETTO and vecchio["diagnosi"] != CORRETTO:
            guadagnati.append(e)
        elif e.diagnosi != CORRETTO and vecchio["diagnosi"] == CORRETTO:
            persi.append((e, vecchio))

    for etichetta, valore in misure(adesso, k).items():
        precedente = prima.get("misure", {}).get(etichetta)
        if valore is None or precedente is None or etichetta == "casi":
            continue
        segno = "+" if valore > precedente else ""
        print(f"  {etichetta:24} {precedente} -> {valore}  ({segno}{round(valore - precedente, 1)})")

    print(f"\n  guadagnati: {len(guadagnati)}")
    for e in guadagnati:
        print(f"     + {e.caso.id}")
    print(f"  persi: {len(persi)}")
    for e, _ in persi:
        print(f"     - {e.caso.id}  ({e.diagnosi})")
    if nuovi:
        print(f"  casi nuovi, non confrontabili: {len(nuovi)}")
    if persi:
        print("\n  Attenzione: una modifica che guadagna casi e ne perde altri va guardata "
              "caso per caso, non solo nella media.")


# --------------------------------------------------------------------------- comando

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Misura recupero e scelta sui casi di valutazione.")
    ap.add_argument("--senza-modello", action="store_true",
                    help="misura solo il recupero: gira in secondi, non chiama Ollama")
    ap.add_argument("--comune", help="limita a un comune")
    ap.add_argument("--insieme", help="limita a un insieme di casi (regressione, campione, assenti)")
    ap.add_argument("--salva", type=Path, help="scrive l'esito in JSON, per confronti futuri")
    ap.add_argument("--confronta", type=Path, help="confronta con un esito salvato")
    ap.add_argument("-k", type=int, default=8, help="quanti candidati per livello")
    ap.add_argument("--senza-mlflow", action="store_true",
                    help="non registra l'esecuzione come run di MLflow")
    ap.add_argument("--senza-tracce", action="store_true",
                    help="registra le misure ma non una traccia per caso (più veloce)")
    ap.add_argument("--prova-mlflow", action="store_true",
                    help="scrive una run minuscola e riferisce: serve a capire se il "
                         "problema è il server o la valutazione")
    args = ap.parse_args()

    if args.prova_mlflow:
        from ecoscan.osservabilita.valutazione_registrata import prova
        raise SystemExit(0 if prova() else 1)

    casi = [c for c in tutti()
            if (not args.comune or c.comune == args.comune)
            and (not args.insieme or c.origine == args.insieme)]
    if not casi:
        raise SystemExit("Nessun caso in data/valutazione/casi/: scrivine a mano, "
                         "una riga per caso, oppure lancia `uv run ecoscan-campiona`.")

    from ecoscan.agente.modelli import ModelloOllama
    from ecoscan.agente.recupero import RecuperoQdrant
    from ecoscan.db.vettorizza import VettorizzatoreOllama, apri_qdrant

    # Le impostazioni in testa, come fanno gli altri comandi: è il modo più rapido per
    # accorgersi che si sta misurando con un indice o un modello diversi da quelli creduti.
    print("Impostazioni: " + " | ".join(f"{c}={v}" for c, v in conf.riepilogo().items()))

    con_modello = not args.senza_modello
    conteggio = ", ".join(f"{len(gruppo)} {insieme}" for insieme, gruppo
                          in per_insieme(casi, chiave=lambda c: c.origine).items())
    print(f"\n{len(casi)} casi ({conteggio}) · k={args.k} · "
          + ("recupero e scelta" if con_modello else "solo recupero, nessun modello"))
    print("Preparo Qdrant e il vettorizzatore...", flush=True)

    recupero = RecuperoQdrant(apri_qdrant(), VettorizzatoreOllama())
    modello = None if args.senza_modello else ModelloOllama()
    agente = Agente(recupero, modello or _ModelloAssente(), k=args.k)
    if con_modello:
        print("Su CPU la scelta richiede qualche secondo per caso.", flush=True)

    esecuzione = descrizione_esecuzione(agente, casi, args.k, con_modello)
    esiti, durata, registrazione = _esegui_registrando(agente, casi, con_modello, esecuzione,
                                                       args)
    print(f"Eseguiti {len(casi)} casi in {durata:.0f} s "
          f"({durata / max(len(casi), 1):.1f} s per caso).")
    riepiloga(esiti, args.k)

    if args.confronta:
        if not args.confronta.is_file():
            raise SystemExit(f"Esito da confrontare non trovato: {args.confronta}")
        confronta(json.loads(args.confronta.read_text(encoding="utf-8")), esiti,
                  esecuzione, args.k)

    # L'esito si salva **sempre**, anche senza `--salva`: una misura costa minuti di CPU e
    # non deve dipendere dall'essersi ricordati di un'opzione. `--salva` serve a darle un
    # nome che si ricorda, per i confronti.
    salvati = [_salva(esiti, esecuzione, args.k, args.salva)] if args.salva else []
    salvati.append(_salva(esiti, esecuzione, args.k, _percorso_automatico(esecuzione)))
    for percorso in salvati:
        print(f"Esito salvato in {percorso}")

    if registrazione is not None:
        registrazione.scrivi(esecuzione, misure(esiti, args.k),
                             come_json(esiti, esecuzione, args.k))
        registrazione.riferisci(tracce=len(esiti))


def _esegui_registrando(agente: Agente, casi: list[Caso], con_modello: bool,
                        esecuzione: dict, args) -> tuple[list[Esito], float, object]:
    """Esegue i casi dentro una run aperta, così ogni caso lascia la sua traccia.

    La run si apre **prima**: una traccia creata mentre una run è in corso le resta
    agganciata, e nell'interfaccia si aprono dalla run stessa. Registrare alla fine
    lascerebbe le tracce nell'esperimento senza legame con la misura che le ha prodotte.

    Il tracciatore punta allo stesso archivio della run — che può essere quello locale, se
    il server non risponde — altrimenti misura e tracce finirebbero in due posti diversi.
    """
    avanzamento = Avanzamento(len(casi))
    if args.senza_mlflow:
        esiti = esegui(agente, casi, con_modello=con_modello, avanzamento=avanzamento)
        return esiti, avanzamento.fine(), None

    from ecoscan.osservabilita.tracciamento import Tracciatore
    from ecoscan.osservabilita.valutazione_registrata import ESPERIMENTO, registrazione

    sessione = f"valutazione {esecuzione['data']}"
    with registrazione(sessione) as apertura:
        if not args.senza_tracce:
            # `attivo=True` e non `conf.MLFLOW_ATTIVO`: come per la misura, le tracce di una
            # valutazione non sono osservabilità facoltativa (D184). Le foto non servono:
            # qui non ce ne sono, i casi partono dal riconoscimento.
            tracciatore = Tracciatore(indirizzo=apertura.indirizzo, esperimento=ESPERIMENTO,
                                      attivo=True, salva_foto=False)
            tracciatore.configura(agente.configurazione())
            agente.tracciatore = tracciatore
        esiti = esegui(agente, casi, con_modello=con_modello, avanzamento=avanzamento,
                       sessione=sessione)
        return esiti, avanzamento.fine(), apertura


def _percorso_automatico(esecuzione: dict) -> Path:
    """Un nome che ordina da sé: data, ora e modalità."""
    quando = str(esecuzione.get("data", "")).replace(":", "").replace("-", "")
    return ESECUZIONI / f"{quando}-{esecuzione.get('modalita', 'valutazione')}.json"


def _salva(esiti: list[Esito], esecuzione: dict, k: int, percorso: Path) -> Path:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(come_json(esiti, esecuzione, k), ensure_ascii=False,
                                   indent=2), encoding="utf-8")
    return percorso


class _ModelloAssente:
    """Sta al posto del modello quando si misura il solo recupero: se qualcuno prova a
    usarlo, meglio un errore chiaro che una risposta silenziosamente vuota."""

    nome = "(nessun modello: solo recupero)"

    def riconosci(self, *_argomenti, **_parametri):
        raise RuntimeError("valutazione senza modello: il riconoscimento non si esegue")

    def scegli(self, *_argomenti, **_parametri):
        raise RuntimeError("valutazione senza modello: la scelta non si esegue")


if __name__ == "__main__":
    main()
