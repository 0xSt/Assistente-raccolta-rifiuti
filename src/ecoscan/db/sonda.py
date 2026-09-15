"""Sonde: misura *dove finisce* la scheda giusta, invece di guardare i primi cinque risultati.

Nasce da un problema concreto: cercando "calzatura" a Napoli il primo risultato è "Laccio per
scarpe" e "Scarpe utilizzabile" non compare. Guardando solo la cima della classifica non si
capisce se la scheda giusta sia seconda, ventesima o assente, e senza quel dato ogni modifica
al retrieval è un tentativo alla cieca.

Ogni sonda è una riga di `data/riferimento/sonde.csv`: comune, domanda, e un pezzo di testo
che deve comparire nella scheda attesa. Il comando riporta la posizione raggiunta da ciascun
metodo (lessicale, semantico, ibrido).

È il primo mattone della valutazione, ma sul solo retrieval: niente foto, niente modello di
visione, quindi gira in pochi secondi e si può ripetere a ogni modifica.

Uso:
  uv run ecoscan-sonda
  uv run ecoscan-sonda --k 30          # quanto in profondità cercare la scheda attesa
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ecoscan import configurazione as conf
from ecoscan.db.indicizza import cerca as cerca_lessicale
from ecoscan.db.vettorizza import DB, VettorizzatoreOllama, apri_qdrant, cerca_semantica, fondi_rrf
from ecoscan.percorsi import DATI

SONDE = DATI / "riferimento" / "sonde.csv"


@dataclass
class Sonda:
    comune: str
    domanda: str
    atteso: str        # pezzo di testo che deve comparire nella scheda giusta
    nota: str = ""


@dataclass
class Esito:
    sonda: Sonda
    posizioni: dict[str, int | None]   # metodo -> posizione (1 = primo), None = non trovata
    trovato: str = ""                  # testo della scheda che ha soddisfatto l'attesa
    primo: str = ""                    # testo del primo risultato ibrido, trovato o no

    @property
    def migliore(self) -> int | None:
        trovate = [p for p in self.posizioni.values() if p]
        return min(trovate) if trovate else None


def carica_sonde(percorso: Path = SONDE) -> list[Sonda]:
    if not percorso.is_file():
        raise SystemExit(f"File delle sonde mancante: {percorso}")
    with open(percorso, encoding="utf-8-sig") as fh:
        return [Sonda(r["comune"].strip(), r["domanda"].strip(), r["atteso"].strip(),
                      (r.get("nota") or "").strip())
                for r in csv.DictReader(fh) if r["domanda"].strip()]


def _posizione(risultati: list[dict], atteso: str) -> tuple[int | None, str]:
    """Posizione e testo della prima scheda che soddisfa l'attesa.

    Restituire anche il testo non è un di più: cercando "Scarpe" come sottostringa si
    accetta "Laccio per scarpe", che è un altro oggetto. Un falso positivo va visto, non
    dedotto confrontando due output diversi.
    """
    bersaglio = atteso.lower()
    for posizione, r in enumerate(risultati, start=1):
        if bersaglio in (r.get("testo") or "").lower():
            return posizione, r.get("testo") or ""
    return None, ""


def esegui(db: sqlite3.Connection, qdrant, vettorizzatore, sonde: list[Sonda],
           k: int = 20) -> list[Esito]:
    esiti = []
    for sonda in sonde:
        lessicale = cerca_lessicale(db, sonda.domanda, sonda.comune, k=k)
        semantica = cerca_semantica(qdrant, sonda.domanda, sonda.comune, vettorizzatore, k=k)
        ibrida = fondi_rrf({"lessicale": lessicale, "semantica": semantica}, k=k)
        posizioni, trovato = {}, ""
        for metodo, risultati in (("lessicale", lessicale), ("semantica", semantica),
                                  ("ibrida", ibrida)):
            posizioni[metodo], testo = _posizione(risultati, sonda.atteso)
            trovato = trovato or testo
        esiti.append(Esito(sonda, posizioni, trovato=trovato,
                           primo=(ibrida[0].get("testo") or "") if ibrida else ""))
    return esiti


def riepilogo(esiti: list[Esito], k: int) -> None:
    print(f"{'domanda':30} {'attesa':26} {'less.':>6} {'sem.':>6} {'ibr.':>6}  trovato / primo")
    print("-" * 112)
    for e in esiti:
        def mostra(metodo: str) -> str:
            p = e.posizioni[metodo]
            return f"#{p}" if p else "-"
        # il testo trovato smaschera i falsi positivi; senza, "Scarpe" sembra trovato
        # anche quando la scheda è "Laccio per scarpe"
        dettaglio = e.trovato or (f"(primo: {e.primo})" if e.primo else "")
        print(f"{e.sonda.domanda[:29]:30} {e.sonda.atteso[:25]:26} "
              f"{mostra('lessicale'):>6} {mostra('semantica'):>6} {mostra('ibrida'):>6}  {dettaglio[:40]}")

    print()
    for metodo in ("lessicale", "semantica", "ibrida"):
        posizioni = [e.posizioni[metodo] for e in esiti]
        trovate = [p for p in posizioni if p]
        primi = sum(1 for p in trovate if p == 1)
        entro3 = sum(1 for p in trovate if p <= 3)
        print(f"  {metodo:10} trovate {len(trovate)}/{len(esiti)} | "
              f"al primo posto {primi} | fra i primi 3 {entro3}")
    mai = [e.sonda.domanda for e in esiti if e.migliore is None]
    if mai:
        print(f"\nMai trovate entro i primi {k} risultati con nessun metodo: {', '.join(mai)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Misura dove finisce la scheda attesa per domande note.")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--sonde", type=Path, default=SONDE)
    ap.add_argument("--k", type=int, default=20)
    args = ap.parse_args()

    if not args.db.is_file():
        raise SystemExit(f"Database non trovato: {args.db}\nLancia prima: uv run ecoscan-carica")
    print("Impostazioni: " + " | ".join(f"{k}={v}" for k, v in conf.riepilogo().items()))

    sonde = carica_sonde(args.sonde)
    qdrant = apri_qdrant()
    with sqlite3.connect(args.db) as db:
        print(f"\n{len(sonde)} sonde, cerco la scheda attesa fra i primi {args.k} risultati\n")
        riepilogo(esegui(db, qdrant, VettorizzatoreOllama(), sonde, args.k), args.k)


if __name__ == "__main__":
    main()
