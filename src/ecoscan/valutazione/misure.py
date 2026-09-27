"""Dai singoli esiti ai numeri che riassumono un'esecuzione.

Funzioni pure: ricevono una lista di `Esito` e restituiscono un dizionario. Non stampano
e non scrivono niente, ed è la ragione per cui stanno qui e non dentro il comando.

**Le percentuali si leggono a coppie.** Ogni metrica presa da sola si massimizza con un
comportamento degenere — non rispondere mai, elencare tutto, tacere sempre, chiedere
sempre — e la coppia è ciò che impedisce di barare senza accorgersene.

**Un numero che manca vale `None`, non zero.** Zero è una misura; `None` dice che non
c'era niente da misurare, e la differenza si vede stampata.
"""
from __future__ import annotations

from ecoscan.valutazione.diagnosi import DIAGNOSI_BUONE, Esito


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

    # Il pass/fail delle regressioni si calcolava dentro la stampa, quindi era l'unico
    # numero del progetto senza serie storica: ora entra nel JSON e su MLflow come gli
    # altri. Vale solo dove ci sono regressioni, e altrove resta `None`.
    regressioni = [e for e in esiti if e.caso.origine == "regressioni"]
    if regressioni:
        valori["regressioni_superate"] = sum(1 for e in regressioni
                                             if e.diagnosi in DIAGNOSI_BUONE)
    return valori


ETICHETTE = {
    "contenitore_corretto": "contenitore corretto (nessuna destinazione sbagliata)",
    "copertura": "copertura delle alternative attese",
    "risposte_perfette": "risposte perfette (contenitore giusto e nulla di perso)",
    "livello_atteso": "livello di evidenza atteso",
    "astensione_corretta": "astensione corretta (sui casi non coperti)",
    "astensione_a_sproposito": "astensione a sproposito (sui casi coperti)",
    "domanda_dovuta": "domanda fatta quando serviva (condizione non dichiarata)",
    "domanda_inutile": "domanda fatta quando NON serviva (condizione dichiarata)",
}
