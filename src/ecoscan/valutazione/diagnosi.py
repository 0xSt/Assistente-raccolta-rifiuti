"""Che cosa è andato storto, e dove: la diagnosi di un singolo caso.

Una risposta sbagliata può nascere in quattro punti — il riconoscimento, il recupero, la
scelta, la composizione — e una percentuale complessiva non li distingue. `Esito` è il tipo
che li separa: porta il caso, ciò che il sistema ha risposto, e undici proprietà che
leggono quei dati in una diagnosi.

Sta in un modulo suo perché è la metà del valore della valutazione e non ha niente a che
vedere con argparse, con MLflow o con la stampa: si legge, e si prova, da sola.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ecoscan.agente.tipi import Candidato
from ecoscan.valutazione.casi import Caso


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

# Le diagnosi che contano come caso vinto. Esisteva in tre versioni diverse — tre
# valori nella riga di avanzamento, quattro nel riepilogo, uno solo nel confronto — e
# lo stesso esito risultava NO mentre l'esecuzione girava e OK quando finiva.
# `CORRETTO_CON_DOMANDA` è un caso vinto: ha chiesto quando doveva, ed è esattamente il
# comportamento che il sistema vuole.
DIAGNOSI_BUONE = (CORRETTO, CORRETTO_CON_DOMANDA, RECUPERATO, ASTENUTO)

# Dove finiscono gli esiti salvati da sé: non versionati (vedi .gitignore)


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
