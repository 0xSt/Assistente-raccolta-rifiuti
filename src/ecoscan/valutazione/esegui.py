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

Il confronto fra le due dice **dove** intervenire, e lo dice da solo:

| recupero | risposta | diagnosi | dove si lavora |
|---|---|---|---|
| ✓ | ✓ | corretto | — |
| ✓ | ✗ | il documento c'era e non è stato scelto | prompt di scelta, politiche del codice |
| ✗ | ✗ | il documento non è mai arrivato | formulazioni, indice, ricerca |
| ✗ | ✓ | corretto per un'altra strada | da guardare: spesso è il livello 2 |

È esattamente la diagnosi che abbiamo fatto a mano sul caso della forchetta, prima leggendo
`/cerca` e poi le tracce. Questo comando la fa su tutti i casi in una volta.

**Due modalità, perché costano diversamente.** Il recupero non usa modelli generativi: gira
in secondi e si può lanciare a ogni modifica. La scelta chiama il modello una volta per
livello, quindi è lenta ma molto meno della visione. Con `--senza-modello` si misura solo il
tetto; senza, si misura tutto.

**Il confronto fra due esecuzioni** è ciò che rende la misura utile a decidere: un numero
assoluto dice poco, "due casi guadagnati e uno perso" dice cosa ha fatto la modifica.

Uso:
  uv run ecoscan-valuta                          # recupero e scelta
  uv run ecoscan-valuta --senza-modello          # solo recupero, in secondi
  uv run ecoscan-valuta --salva esiti/v0.40.json
  uv run ecoscan-valuta --confronta esiti/v0.39.json
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from ecoscan.agente.agente import Agente, Richiesta
from ecoscan.agente.tipi import Candidato
from ecoscan.valutazione.casi import Caso, tutti

# Le diagnosi possibili, nell'ordine in cui conviene leggerle
CORRETTO = "corretto"
SCELTA_SBAGLIATA = "il documento c'era, non è stato scelto"
RECUPERO_FALLITO = "il documento non è stato recuperato"
ALTRA_STRADA = "corretto per un'altra strada"
# Senza modello non si misura la risposta, solo il tetto: chiamarlo "corretto" farebbe
# leggere come una risposta giusta ciò che è soltanto un documento trovato.
RECUPERATO = "documento recuperato (la risposta non è stata valutata)"


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

    @property
    def risposta_corretta(self) -> bool:
        return bool(self.destinazioni) and set(self.destinazioni) == set(self.caso.destinazioni_attese)

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
        if not self.valutata_la_scelta:
            return RECUPERATO if self.recuperato else RECUPERO_FALLITO
        if self.risposta_corretta:
            return CORRETTO if self.recuperato else ALTRA_STRADA
        return SCELTA_SBAGLIATA if self.recuperato else RECUPERO_FALLITO


def porta_alla_destinazione(candidato: Candidato, attese: list[str]) -> bool:
    """Il documento porta a una delle destinazioni attese?

    Basta una destinazione in comune: un oggetto con più varianti ne offre parecchie, e
    quale sia quella giusta lo decide la condizione, non il recupero.
    """
    return bool(set(candidato.destinazioni) & set(attese))


def valuta_caso(agente: Agente, caso: Caso, con_modello: bool = True) -> Esito:
    """Esegue un caso e misura recupero e risposta.

    Il recupero si misura su **tutti** i livelli, non solo su quello che ha risposto: se la
    voce giusta era al livello 1 e la risposta è arrivata dal 2, vogliamo saperlo.
    """
    richiesta = Richiesta(caso.riconoscimento, caso.comune, caso.testo_utente)
    trovati: list[Candidato] = []
    for livello in (1, 2):
        trovati.extend(agente._recupera(richiesta, livello))

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
                 raggiungibili=raggiungibili)


def esegui(agente: Agente, casi: list[Caso], con_modello: bool = True,
           avanzamento=None) -> list[Esito]:
    esiti = []
    for numero, caso in enumerate(casi, start=1):
        if avanzamento:
            avanzamento(numero, len(casi), caso)
        esiti.append(valuta_caso(agente, caso, con_modello))
    return esiti


# --------------------------------------------------------------------------- riepilogo

def misure(esiti: list[Esito]) -> dict[str, float | int]:
    """I numeri che riassumono un'esecuzione."""
    totale = len(esiti) or 1
    con_scelta = [e for e in esiti if e.valutata_la_scelta]
    livelli = [e for e in esiti if e.livello_corretto is not None]
    return {
        "casi": len(esiti),
        "recupero": round(100 * sum(e.recuperato for e in esiti) / totale, 1),
        "risposte_corrette": round(
            100 * sum(e.risposta_corretta for e in con_scelta) / (len(con_scelta) or 1), 1)
        if con_scelta else None,
        "livello_atteso": round(
            100 * sum(bool(e.livello_corretto) for e in livelli) / (len(livelli) or 1), 1)
        if livelli else None,
        "posizione_media": round(
            sum(e.posizione for e in esiti if e.posizione) / max(
                sum(1 for e in esiti if e.posizione), 1), 1),
    }


def riepiloga(esiti: list[Esito]) -> None:
    print(f"\n{'esito':4} {'caso':44} {'pos.':>5}  diagnosi")
    print("-" * 100)
    buone = (CORRETTO, RECUPERATO)
    for e in sorted(esiti, key=lambda e: (e.diagnosi in buone, e.caso.id)):
        segno = "OK" if e.diagnosi in buone else "  "
        posizione = str(e.posizione) if e.posizione else "-"
        print(f"{segno:4} {e.caso.id[:44]:44} {posizione:>5}  {e.diagnosi}")
        if e.diagnosi in buone:
            continue
        print(f"     atteso:   {', '.join(e.caso.destinazioni_attese)}")
        if e.destinazioni:
            print(f"     ottenuto: {', '.join(e.destinazioni)}")
        # Prima di dare la colpa al recupero, si guarda dove portavano i documenti trovati:
        # se l'attesa non compare da nessuna parte, spesso è l'attesa a essere sbagliata
        if e.raggiungibili:
            print(f"     i documenti trovati portano a: {', '.join(e.raggiungibili[:8])}")
            print("     (se l'attesa non è qui dentro, controlla il caso prima del recupero)")

    m = misure(esiti)
    print(f"\n## Misure su {m['casi']} casi")
    print(f"  recupero (il documento giusto è fra i candidati): {m['recupero']}%")
    if m["risposte_corrette"] is not None:
        print(f"  risposte corrette:                               {m['risposte_corrette']}%")
    if m["livello_atteso"] is not None:
        print(f"  livello di evidenza atteso:                      {m['livello_atteso']}%")
    print(f"  posizione media del documento giusto:            {m['posizione_media']}")

    print("\n## Dove intervenire")
    for diagnosi in (RECUPERO_FALLITO, SCELTA_SBAGLIATA, ALTRA_STRADA):
        quanti = sum(1 for e in esiti if e.diagnosi == diagnosi)
        if quanti:
            print(f"  {quanti:3}  {diagnosi}")


def come_json(esiti: list[Esito]) -> dict:
    return {"misure": misure(esiti),
            "esiti": {e.caso.id: {"recuperato": e.recuperato, "corretta": e.risposta_corretta,
                                  "destinazioni": e.destinazioni, "livello": e.livello,
                                  "posizione": e.posizione, "diagnosi": e.diagnosi}
                      for e in esiti}}


def confronta(prima: dict, adesso: list[Esito]) -> None:
    """Cosa è cambiato rispetto a un'esecuzione salvata.

    È la parte che serve a decidere: un numero assoluto dice poco, "due guadagnati e uno
    perso" dice cosa ha fatto davvero la modifica.
    """
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

    print("\n## Confronto con l'esecuzione precedente")
    for etichetta, valore in misure(adesso).items():
        precedente = prima.get("misure", {}).get(etichetta)
        if valore is None or precedente is None or etichetta == "casi":
            continue
        segno = "+" if valore > precedente else ""
        print(f"  {etichetta:20} {precedente} -> {valore}  ({segno}{round(valore - precedente, 1)})")

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
    ap.add_argument("--salva", type=Path, help="scrive l'esito in JSON, per confronti futuri")
    ap.add_argument("--confronta", type=Path, help="confronta con un esito salvato")
    ap.add_argument("-k", type=int, default=8, help="quanti candidati per livello")
    args = ap.parse_args()

    casi = [c for c in tutti() if not args.comune or c.comune == args.comune]
    if not casi:
        raise SystemExit("Nessun caso in data/valutazione/. Scrivine a mano in casi.jsonl, "
                         "oppure raccogli riscontri dall'interfaccia.")

    from ecoscan.agente.modelli import ModelloOllama
    from ecoscan.agente.recupero import RecuperoQdrant
    from ecoscan.db.vettorizza import VettorizzatoreOllama, apri_qdrant

    recupero = RecuperoQdrant(apri_qdrant(), VettorizzatoreOllama())
    modello = None if args.senza_modello else ModelloOllama()
    agente = Agente(recupero, modello or _ModelloAssente(), k=args.k)

    print(f"{len(casi)} casi" + (" · solo recupero" if args.senza_modello else ""))

    def mostra(numero, totale, caso):
        print(f"  [{numero}/{totale}] {caso.id[:60]}", flush=True)

    esiti = esegui(agente, casi, con_modello=not args.senza_modello,
                   avanzamento=mostra if not args.senza_modello else None)
    riepiloga(esiti)

    if args.confronta:
        if not args.confronta.is_file():
            raise SystemExit(f"Esito da confrontare non trovato: {args.confronta}")
        confronta(json.loads(args.confronta.read_text(encoding="utf-8")), esiti)

    if args.salva:
        args.salva.parent.mkdir(parents=True, exist_ok=True)
        args.salva.write_text(json.dumps(come_json(esiti), ensure_ascii=False, indent=2),
                              encoding="utf-8")
        print(f"\nEsito salvato in {args.salva}")


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
