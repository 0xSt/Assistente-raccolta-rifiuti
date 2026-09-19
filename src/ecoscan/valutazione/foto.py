"""La valutazione sulle foto: quanto costa il modello di visione, in errori e in secondi.

I casi di `ecoscan-valuta` tengono fermo il riconoscimento, di proposito (D153): misurano
recupero e scelta senza il rumore del modello di visione. Resta però la domanda che quel
taglio lascia fuori, ed è quella che interessa a chi usa l'app: **partendo da una foto
vera, quante volte arriva la risposta giusta?**

Questo comando la misura, e lo fa in un modo che separa la colpa. Per ogni foto esegue
**due volte** la stessa richiesta:

1. **reale** — riconoscimento dalla foto, poi risposta. È il percorso dell'utente;
2. **ideale** — riconoscimento *dichiarato* nell'etichetta (l'oggetto vero), poi risposta.
   È lo stesso percorso senza il modello di visione.

La differenza fra i due numeri è il **costo del riconoscimento**, isolato:

    corrette dalla foto 68%   ·   corrette dall'oggetto vero 86%   ->   -18 punti di visione

Senza il secondo giro, una risposta sbagliata dalla foto non direbbe se il modello ha visto
male o se il resto del sistema ha sbagliato. Con il secondo giro lo dice, e costa pochi
secondi in più per foto: è `rispondi`, non `analizza`.

**I tempi.** Su CPU il riconoscimento domina tutto il resto, ed è l'argomento con cui si
difende (o si abbandona) la scelta del modello locale. Si riportano **mediana e p90**, mai
la media: i tempi hanno code lunghe, e la media di dieci foto veloci e una lenta descrive
una situazione che non è capitata a nessuno.

**Perché si esegue una volta per rilascio e non a ogni modifica.** Venti foto sono
venti-quaranta minuti su CPU. È il motivo per cui questa misura è separata da
`ecoscan-valuta`, che gira in secondi: strumenti con costi diversi hanno ritmi diversi.

**Le etichette.** `data/valutazione/foto/foto.jsonl`, una riga per foto:

    {"file": "bottiglia.jpg", "comune": "Napoli", "oggetto": "bottiglia di plastica",
     "destinazioni_attese": ["Plastica e Metalli"], "nota": "controluce"}

Le immagini stanno in `data/valutazione/foto/immagini/` e **non sono versionate**: sono
foto di casa, pesano, e il progetto non ne ha bisogno per funzionare. Le etichette sì,
perché descrivono cosa il sistema deve saper fare.

Uso:
  uv run ecoscan-valuta-foto
  uv run ecoscan-valuta-foto --solo-reale      # salta il secondo giro, se hai fretta
  uv run ecoscan-valuta-foto --salva esiti/foto-v0.43.json
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ecoscan.agente.agente import Agente
from ecoscan.agente.tipi import Riconoscimento, Risposta
from ecoscan.percorsi import DATI
from ecoscan.valutazione.casi import Caso
from ecoscan.valutazione.esegui import Esito

CARTELLA = DATI / "valutazione" / "foto"
ETICHETTE = CARTELLA / "foto.jsonl"
IMMAGINI = CARTELLA / "immagini"


@dataclass
class Foto:
    """Una foto etichettata: il file, cosa c'è dentro e dove deve finire."""

    file: str
    comune: str
    oggetto: str
    destinazioni_attese: list[str] = field(default_factory=list)
    testo_utente: str | None = None
    nota: str = ""

    @property
    def caso(self) -> Caso:
        """La foto vista come caso: permette di riusare le stesse metriche di
        `ecoscan-valuta`, invece di inventarne un secondo insieme che poi nessuno sa
        confrontare con il primo."""
        return Caso(comune=self.comune, oggetto=self.oggetto,
                    destinazioni_attese=list(self.destinazioni_attese),
                    testo_utente=self.testo_utente, nota=self.nota, origine="foto")

    def dati(self, cartella: Path | None = None) -> bytes:
        percorso = (cartella or IMMAGINI) / self.file
        if not percorso.is_file():
            raise SystemExit(f"Foto mancante: {percorso}")
        return percorso.read_bytes()


@dataclass
class EsitoFoto:
    """Come è andata una foto: i due giri e i tempi."""

    foto: Foto
    riconosciuto: str                      # cosa ha visto il modello
    reale: Esito                           # dalla foto
    ideale: Esito | None                   # dall'oggetto vero, senza visione
    secondi_riconoscimento: float
    secondi_risposta: float

    @property
    def secondi_totali(self) -> float:
        return round(self.secondi_riconoscimento + self.secondi_risposta, 2)

    @property
    def colpa_della_visione(self) -> bool:
        """Sbagliata dalla foto ma giusta dall'oggetto vero: il difetto è nel riconoscimento.

        È la sola domanda per cui questo comando esiste. Senza il secondo giro si saprebbe
        che la risposta è sbagliata, non da dove viene l'errore.
        """
        return (self.ideale is not None
                and not self.reale.perfetta and self.ideale.perfetta)


def leggi_etichette(percorso: Path | None = None) -> list[Foto]:
    percorso = percorso or ETICHETTE
    if not percorso.is_file():
        raise SystemExit(
            f"Etichette mancanti: {percorso}\n"
            "Una riga per foto: file, comune, oggetto, destinazioni_attese.")
    foto = []
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        if riga.strip():
            campi = {k: v for k, v in json.loads(riga).items() if k in Foto.__annotations__}
            foto.append(Foto(**campi))
    return foto


def _esito(caso: Caso, risposta: Risposta) -> Esito:
    """Un `Esito` costruito da una risposta già ottenuta.

    `recuperato` si legge dai candidati della risposta e non da una ricerca a parte: qui
    interessa il percorso vero, e la risposta porta già con sé i documenti che ha visto.
    """
    attese = set(caso.destinazioni_attese)
    posizione = next((i for i, c in enumerate(risposta.candidati, start=1)
                      if set(c.destinazioni) & attese), None)
    return Esito(caso=caso, recuperato=posizione is not None,
                 destinazioni=risposta.destinazioni, livello=risposta.livello_evidenza,
                 candidati=len(risposta.candidati), posizione=posizione)


def valuta_foto(agente: Agente, foto: Foto, con_ideale: bool = True,
                cartella: Path | None = None) -> EsitoFoto:
    immagine = foto.dati(cartella)

    inizio = time.monotonic()
    riconoscimento = agente.modello.riconosci(immagine, foto.testo_utente)
    secondi_riconoscimento = round(time.monotonic() - inizio, 2)

    inizio = time.monotonic()
    risposta = agente.rispondi(riconoscimento, foto.comune, foto.testo_utente)
    secondi_risposta = round(time.monotonic() - inizio, 2)

    ideale = None
    if con_ideale:
        # stesso percorso, riconoscimento dichiarato: la confidenza massima è la stessa
        # convenzione dei casi (il riconoscimento è un dato, non un'ipotesi)
        vero = Riconoscimento(oggetto=foto.oggetto, confidenza=1.0)
        ideale = _esito(foto.caso, agente.rispondi(vero, foto.comune, foto.testo_utente))

    return EsitoFoto(foto=foto, riconosciuto=riconoscimento.oggetto or "(non riconosciuto)",
                     reale=_esito(foto.caso, risposta), ideale=ideale,
                     secondi_riconoscimento=secondi_riconoscimento,
                     secondi_risposta=secondi_risposta)


def percentile(valori: list[float], quantile: float) -> float | None:
    """Il p50 e il p90 col metodo del **rango più vicino**: il valore restituito è sempre
    un tempo davvero misurato, non un'interpolazione fra due misure.

    Su venti foto la differenza fra i metodi è di frazioni di secondo, ma dire "il p90 è
    41 secondi" avendo cronometrato 41 secondi è più difendibile che dire 38,7, che non è
    successo a nessuna foto.
    """
    if not valori:
        return None
    ordinati = sorted(valori)
    indice = min(len(ordinati) - 1, math.ceil(quantile * len(ordinati)) - 1)
    return round(ordinati[max(0, indice)], 2)


def misure_foto(esiti: list[EsitoFoto]) -> dict[str, float | int | None]:
    totale = len(esiti) or 1
    con_ideale = [e for e in esiti if e.ideale is not None]
    riconoscimenti = [e.secondi_riconoscimento for e in esiti]
    risposte = [e.secondi_risposta for e in esiti]
    return {
        "foto": len(esiti),
        "corrette_dalla_foto": round(100 * sum(e.reale.perfetta for e in esiti) / totale, 1),
        "contenitore_corretto": round(
            100 * sum(bool(e.reale.contenitore_corretto) for e in esiti) / totale, 1),
        "corrette_dall_oggetto_vero": round(
            100 * sum(e.ideale.perfetta for e in con_ideale) / len(con_ideale), 1)
        if con_ideale else None,
        "perse_dalla_visione": sum(e.colpa_della_visione for e in esiti) if con_ideale else None,
        "riconoscimento_p50": percentile(riconoscimenti, 0.5),
        "riconoscimento_p90": percentile(riconoscimenti, 0.9),
        "risposta_p50": percentile(risposte, 0.5),
        "risposta_p90": percentile(risposte, 0.9),
        "totale_p50": percentile([e.secondi_totali for e in esiti], 0.5),
        "secondi_complessivi": round(sum(riconoscimenti) + sum(risposte), 1),
    }


def riepiloga(esiti: list[EsitoFoto]) -> None:
    print(f"\n{'esito':4} {'foto':22} {'visto':22} {'sec':>6}  risposta")
    print("-" * 100)
    for e in esiti:
        segno = "OK" if e.reale.perfetta else ("VIS" if e.colpa_della_visione else "  ")
        print(f"{segno:4} {e.foto.file[:21]:22} {e.riconosciuto[:21]:22} "
              f"{e.secondi_totali:6.1f}  {' oppure '.join(e.reale.destinazioni) or '(nessuna)'}")
        if not e.reale.perfetta:
            print(f"     atteso: {', '.join(e.foto.destinazioni_attese)}"
                  f"   (oggetto vero: {e.foto.oggetto})")

    m = misure_foto(esiti)
    print(f"\n## Misure su {m['foto']} foto")
    print(f"  risposte corrette partendo dalla foto:        {m['corrette_dalla_foto']}%")
    print(f"  contenitore corretto (nessuna destinazione sbagliata): {m['contenitore_corretto']}%")
    if m["corrette_dall_oggetto_vero"] is not None:
        differenza = round(m["corrette_dall_oggetto_vero"] - m["corrette_dalla_foto"], 1)
        print(f"  risposte corrette partendo dall'oggetto vero: {m['corrette_dall_oggetto_vero']}%")
        print(f"  costo del riconoscimento:                     {differenza} punti "
              f"({m['perse_dalla_visione']} foto perse solo per la visione)")

    print("\n## Tempi su questa macchina (secondi)")
    print(f"  riconoscimento   p50 {m['riconoscimento_p50']}   p90 {m['riconoscimento_p90']}")
    print(f"  recupero+scelta  p50 {m['risposta_p50']}   p90 {m['risposta_p90']}")
    print(f"  totale per foto  p50 {m['totale_p50']}")
    print(f"  esecuzione completa: {m['secondi_complessivi']} s")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Valutazione end-to-end sulle foto: correttezza, costo della visione, tempi.")
    ap.add_argument("--solo-reale", action="store_true",
                    help="salta il giro con l'oggetto dichiarato (niente scomposizione)")
    ap.add_argument("--etichette", type=Path, default=ETICHETTE)
    ap.add_argument("--immagini", type=Path, default=IMMAGINI)
    ap.add_argument("--salva", type=Path, help="scrive l'esito in JSON")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--senza-mlflow", action="store_true")
    args = ap.parse_args()

    foto = leggi_etichette(args.etichette)
    if not foto:
        raise SystemExit(f"Nessuna foto etichettata in {args.etichette}")

    from ecoscan.agente.modelli import ModelloOllama
    from ecoscan.agente.recupero import RecuperoQdrant
    from ecoscan.db.vettorizza import VettorizzatoreOllama, apri_qdrant

    agente = Agente(RecuperoQdrant(apri_qdrant(), VettorizzatoreOllama()),
                    ModelloOllama(), k=args.k)
    print(f"{len(foto)} foto · su CPU conta qualche minuto l'una")

    esiti = []
    for numero, una in enumerate(foto, start=1):
        print(f"  [{numero}/{len(foto)}] {una.file}", flush=True)
        esiti.append(valuta_foto(agente, una, con_ideale=not args.solo_reale, cartella=args.immagini))

    riepiloga(esiti)

    esecuzione = {"data": datetime.now().isoformat(timespec="minutes"), "k": args.k,
                  "modalita": "foto", "casi": {"foto": len(foto)},
                  "configurazione": agente.configurazione()}
    if args.salva:
        args.salva.parent.mkdir(parents=True, exist_ok=True)
        args.salva.write_text(json.dumps(
            {"esecuzione": esecuzione, "misure": misure_foto(esiti),
             "esiti": {e.foto.file: {"riconosciuto": e.riconosciuto,
                                     "destinazioni": e.reale.destinazioni,
                                     "corretta": e.reale.perfetta,
                                     "colpa_della_visione": e.colpa_della_visione,
                                     "secondi": e.secondi_totali} for e in esiti}},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nEsito salvato in {args.salva}")

    if not args.senza_mlflow:
        from ecoscan.osservabilita.valutazione_registrata import registra
        registra(esecuzione, misure_foto(esiti))


if __name__ == "__main__":
    main()
