"""Misurare il recupero e la scelta, separatamente.

"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from ecoscan import configurazione as conf
from ecoscan.archivio import salva_json
from ecoscan.agente.agente import Agente, Richiesta
from ecoscan.agente.tipi import Candidato
from ecoscan.percorsi import VALUTAZIONE
from ecoscan.valutazione.casi import Caso, per_insieme, tutti

# `diagnosi` e `misure` stanno in due moduli loro: sono la parte pura della valutazione —
# nessun argparse, nessun MLflow, nessuna stampa — e si leggono e si provano da sole. Qui
# restano ri-esportate, perche' `esegui` e' il nome con cui il resto del progetto le
# conosce e un taglio interno non deve diventare un compito per chi lo importa.
from ecoscan.valutazione.diagnosi import (  # noqa: F401
    ALTRA_STRADA, ASTENUTO, CANALE_PERSO, CORRETTO, CORRETTO_CON_DOMANDA, DIAGNOSI_BUONE,
    DOMANDA_INUTILE,
    Esito, MANCATA_DOMANDA, NON_ASTENUTO, RECUPERATO, RECUPERO_FALLITO, SCELTA_SBAGLIATA,
    porta_alla_destinazione,
)
from ecoscan.valutazione.misure import ETICHETTE, _percentuale, misure, soglie_recall  # noqa: F401

ESECUZIONI = VALUTAZIONE / "esecuzioni"


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
        segno = "ok" if esito.diagnosi in DIAGNOSI_BUONE else "NO"
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
    for e in sorted(esiti, key=lambda e: (e.diagnosi in DIAGNOSI_BUONE, e.caso.id)):
        _riga_caso(e, DIAGNOSI_BUONE)

    for insieme, gruppo in per_insieme(esiti, chiave=lambda e: e.caso.origine).items():
        m = misure(gruppo, k)
        # le regressioni si leggono come pass/fail: sono i casi che NON devono tornare
        # indietro, e una percentuale su diciotto casi scelti apposta non stima niente
        if insieme == "regressioni":
            print(f"\n## Regressioni: {m['regressioni_superate']}/{len(gruppo)} superate")
            continue
        print(f"\n## Misure sull'insieme «{insieme}» ({m['casi']} casi)")
        recall = "  ".join(f"@{n} {m[f'recall@{n}']}%" for n in soglie_recall(k)
                           if m.get(f"recall@{n}") is not None)
        if recall:
            print(f"  recall:                                          {recall}")
        for chiave, etichetta in ETICHETTE.items():
            if m.get(chiave) is not None:
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
        elif (e.diagnosi in DIAGNOSI_BUONE) and vecchio["diagnosi"] not in DIAGNOSI_BUONE:
            guadagnati.append(e)
        elif (e.diagnosi not in DIAGNOSI_BUONE) and vecchio["diagnosi"] in DIAGNOSI_BUONE:
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
    with _esecuzione_registrata(agente, casi, con_modello, esecuzione, args) as aperta:
        esiti, durata, registrazione = aperta
        print(f"Eseguiti {len(casi)} casi in {durata:.0f} s "
              f"({durata / max(len(casi), 1):.1f} s per caso).")
        riepiloga(esiti, args.k)

        if args.confronta:
            if not args.confronta.is_file():
                raise SystemExit(f"Esito da confrontare non trovato: {args.confronta}")
            confronta(json.loads(args.confronta.read_text(encoding="utf-8")), esiti,
                      esecuzione, args.k)

        for percorso in salva_sempre(come_json(esiti, esecuzione, args.k), esecuzione,
                                     args.salva):
            print(f"Esito salvato in {percorso}")

        if registrazione is not None:
            registrazione.scrivi(esecuzione, misure(esiti, args.k),
                                 come_json(esiti, esecuzione, args.k))
            registrazione.riferisci(tracce=0 if args.senza_tracce else len(esiti))


@contextmanager
def _esecuzione_registrata(agente: Agente, casi: list[Caso], con_modello: bool,
                           esecuzione: dict, args) -> Iterator[tuple[list[Esito], float, object]]:
    """Esegue i casi dentro una run aperta, così ogni caso lascia la sua traccia.

    La run si apre **prima** e resta aperta fino alla scrittura delle misure. Prima:
    perché una traccia creata mentre una run è in corso le resta agganciata, e
    nell'interfaccia si aprono dalla run stessa. Fino alla fine: perché `log_params` fuori
    da una run ne apre un'altra da sé, e misure e tracce finirebbero in due run diverse —
    che è esattamente ciò che questo comando vuole evitare.
    """
    avanzamento = Avanzamento(len(casi))
    if args.senza_mlflow:
        esiti = esegui(agente, casi, con_modello=con_modello, avanzamento=avanzamento)
        yield esiti, avanzamento.fine(), None
        return

    from ecoscan.osservabilita.valutazione_registrata import registrazione, traccia_dentro

    sessione = f"valutazione {esecuzione['data']}"
    with registrazione(sessione) as apertura:
        if not args.senza_tracce:
            # niente foto: qui non ce ne sono, i casi partono dal riconoscimento
            traccia_dentro(apertura, agente, salva_foto=False)
        esiti = esegui(agente, casi, con_modello=con_modello, avanzamento=avanzamento,
                       sessione=sessione)
        yield esiti, avanzamento.fine(), apertura


def percorso_automatico(esecuzione: dict) -> Path:
    """Un nome che ordina da sé: data, ora e modalità."""
    quando = str(esecuzione.get("data", "")).replace(":", "").replace("-", "")
    return ESECUZIONI / f"{quando}-{esecuzione.get('modalita', 'valutazione')}.json"


def salva_sempre(corpo: dict, esecuzione: dict, scelto: Path | None) -> list[Path]:
    """Scrive l'esito, con il nome scelto se c'è e comunque con quello automatico.

    L'esito si salva **sempre**, anche senza `--salva`: una misura costa minuti di CPU e
    non deve dipendere dall'essersi ricordati di un'opzione. `--salva` serve a darle un
    nome che si ricorda, per i confronti.
    """
    percorsi = ([scelto] if scelto else []) + [percorso_automatico(esecuzione)]
    return [salva_json(p, corpo) for p in percorsi]



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
