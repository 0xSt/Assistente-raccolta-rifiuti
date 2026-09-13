"""Load, passaggio 3: vettori e ricerca ibrida.

Calcola un embedding per ogni scheda e li usa insieme all'indice lessicale.

**Perché ibrida.** I due metodi sbagliano in modi opposti. Il lessicale è cieco sulle
parafrasi: a Torino "tetrapak" non trova "Tetra Pak" perché la sottostringa non combacia.
Il semantico risolve quello, ma avvicina oggetti simili con destinazioni diverse
("bottiglia di vetro" e "bicchiere di vetro" sono quasi identici e vanno in contenitori
diversi). Fondendo le due classifiche si tengono i pregi di entrambi.

**Perché RRF.** I punteggi dei due metodi non sono confrontabili (BM25 è negativo e senza
scala fissa, il coseno sta fra -1 e 1). La Reciprocal Rank Fusion usa solo la *posizione*
nelle rispettive classifiche, quindi non richiede di tarare pesi fra grandezze diverse.

**Perché niente indice approssimato.** Circa 1100 schede a 768 dimensioni sono ~3 MB: la
ricerca esaustiva costa meno di un millisecondo. Un indice approssimato serve a milioni di
vettori (D12).

Uso:
  ollama pull embeddinggemma            # una volta sola
  uv run ecoscan-vettorizza             # calcola i vettori mancanti
  uv run ecoscan-vettorizza --cerca "contenitore del latte" --comune Napoli
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol, Sequence

import numpy as np

from ecoscan.db.indicizza import cerca as cerca_lessicale
from ecoscan.percorsi import DATI

DB = DATI / "ecoscan.db"
MODELLO = "embeddinggemma"
OLLAMA = "http://localhost:11434/api/embed"
K_RRF = 60  # costante standard della Reciprocal Rank Fusion: attenua le prime posizioni

SCHEMA_EMBEDDING = """
CREATE TABLE IF NOT EXISTS scheda_embedding (
    scheda_id INTEGER PRIMARY KEY REFERENCES scheda(id),
    modello   TEXT NOT NULL,
    impronta  TEXT NOT NULL,   -- hash del testo: se non cambia, il vettore non si ricalcola
    vettore   BLOB NOT NULL    -- float32 normalizzato, così il coseno è un prodotto scalare
);
"""


class Vettorizzatore(Protocol):
    """Interfaccia minima: la si può sostituire con un finto nei test o con un altro modello."""

    nome: str

    def vettorizza(self, testi: Sequence[str], come: str) -> list[list[float]]:
        ...


class VettorizzatoreOllama:
    """EmbeddingGemma via Ollama.

    Il modello distingue i prompt di *documento* e di *interrogazione*: usarli entrambi
    correttamente migliora sensibilmente il recupero, ed è gratis.
    """

    def __init__(self, modello: str = MODELLO, url: str = OLLAMA):
        self.nome, self.url = modello, url

    def _prompt(self, testo: str, come: str) -> str:
        if come == "query":
            return f"task: search result | query: {testo}"
        return f"title: none | text: {testo}"

    def vettorizza(self, testi: Sequence[str], come: str = "documento") -> list[list[float]]:
        corpo = json.dumps({"model": self.nome,
                            "input": [self._prompt(t, come) for t in testi]}).encode()
        richiesta = urllib.request.Request(self.url, data=corpo,
                                           headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(richiesta, timeout=300) as risposta:
                return json.load(risposta)["embeddings"]
        except urllib.error.URLError as errore:
            raise SystemExit(
                f"Ollama non raggiungibile su {self.url} ({errore}).\n"
                f"Avvialo e scarica il modello: ollama pull {self.nome}") from errore


# --------------------------------------------------------------------------- calcolo

def impronta(testo: str) -> str:
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:16]


def _a_blob(vettore: Sequence[float]) -> bytes:
    v = np.asarray(vettore, dtype=np.float32)
    norma = np.linalg.norm(v)
    return (v / norma if norma else v).tobytes()


def calcola(db: sqlite3.Connection, vettorizzatore: Vettorizzatore, lotto: int = 32,
            avanzamento=print) -> dict[str, int]:
    """Calcola i vettori mancanti. Le schede già vettorizzate e non cambiate si saltano."""
    db.executescript(SCHEMA_EMBEDDING)
    da_fare = db.execute("""
        SELECT s.id, s.testo FROM scheda s
        LEFT JOIN scheda_embedding e ON e.scheda_id = s.id AND e.modello = ?
        WHERE e.scheda_id IS NULL OR e.impronta != ?""",
        (vettorizzatore.nome, "")).fetchall()
    da_fare = [(i, t) for i, t in da_fare
               if db.execute("SELECT impronta FROM scheda_embedding WHERE scheda_id = ? AND modello = ?",
                             (i, vettorizzatore.nome)).fetchone() != (impronta(t),)]

    totale = len(da_fare)
    if not totale:
        avanzamento("Tutti i vettori sono già aggiornati.")
        return {"calcolati": 0, "totale": db.execute("SELECT count(*) FROM scheda_embedding").fetchone()[0]}

    avanzamento(f"Da calcolare: {totale} vettori con {vettorizzatore.nome} (a lotti di {lotto})")
    inizio = time.monotonic()
    for n in range(0, totale, lotto):
        gruppo = da_fare[n:n + lotto]
        vettori = vettorizzatore.vettorizza([t for _, t in gruppo], "documento")
        db.executemany(
            "INSERT OR REPLACE INTO scheda_embedding (scheda_id, modello, impronta, vettore) "
            "VALUES (?, ?, ?, ?)",
            [(i, vettorizzatore.nome, impronta(t), _a_blob(v))
             for (i, t), v in zip(gruppo, vettori)])
        db.commit()
        fatti = min(n + lotto, totale)
        trascorso = time.monotonic() - inizio
        avanzamento(f"  {fatti}/{totale} — stimati {(totale - fatti) * trascorso / fatti / 60:.1f} min alla fine")
    return {"calcolati": totale,
            "totale": db.execute("SELECT count(*) FROM scheda_embedding").fetchone()[0]}


# --------------------------------------------------------------------------- ricerca

def _matrice(db: sqlite3.Connection, comune: str, modello: str) -> tuple[list[int], np.ndarray]:
    righe = db.execute("""
        SELECT e.scheda_id, e.vettore FROM scheda_embedding e
        JOIN scheda s ON s.id = e.scheda_id JOIN comune c ON c.id = s.comune_id
        WHERE c.nome = ? AND e.modello = ?""", (comune, modello)).fetchall()
    if not righe:
        return [], np.empty((0, 0), dtype=np.float32)
    ids = [r[0] for r in righe]
    return ids, np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in righe])


def cerca_semantica(db: sqlite3.Connection, query: str, comune: str,
                    vettorizzatore: Vettorizzatore, k: int = 5) -> list[dict]:
    ids, matrice = _matrice(db, comune, vettorizzatore.nome)
    if not ids:
        return []
    q = np.asarray(vettorizzatore.vettorizza([query], "query")[0], dtype=np.float32)
    norma = np.linalg.norm(q)
    somiglianze = matrice @ (q / norma if norma else q)   # vettori già normalizzati: coseno
    migliori = np.argsort(-somiglianze)[:k]
    return [_dettagli_scheda(db, ids[i], float(somiglianze[i])) for i in migliori]


def _dettagli_scheda(db: sqlite3.Connection, scheda_id: int, punteggio: float) -> dict:
    riga = db.execute("""
        SELECT s.livello, s.tipo, s.testo, v.nome, v.slug, r.polarita,
               (SELECT group_concat(d.nome, ' oppure ') FROM voce_destinazione vd
                  JOIN destinazione d ON d.id = vd.destinazione_id WHERE vd.voce_id = s.voce_id),
               (SELECT d.nome FROM destinazione d WHERE d.id = r.destinazione_id)
        FROM scheda s LEFT JOIN voce v ON v.id = s.voce_id
        LEFT JOIN regola r ON r.id = s.regola_id WHERE s.id = ?""", (scheda_id,)).fetchone()
    return {"scheda_id": scheda_id, "livello": riga[0], "tipo": riga[1], "testo": riga[2],
            "nome": riga[3], "slug": riga[4], "polarita": riga[5],
            "destinazione": riga[6] or riga[7], "punteggio": punteggio}


def fondi_rrf(classifiche: dict[str, list[dict]], k: int = 5, costante: int = K_RRF) -> list[dict]:
    """Reciprocal Rank Fusion: ogni risultato vale 1/(costante + posizione) in ciascuna classifica.

    Usa le posizioni, non i punteggi, che non sarebbero confrontabili fra BM25 e coseno.
    """
    punteggi: dict[int, float] = {}
    schede: dict[int, dict] = {}
    provenienza: dict[int, dict[str, int]] = {}
    for metodo, risultati in classifiche.items():
        for posizione, r in enumerate(risultati, start=1):
            sid = r["scheda_id"]
            punteggi[sid] = punteggi.get(sid, 0.0) + 1.0 / (costante + posizione)
            schede.setdefault(sid, r)
            provenienza.setdefault(sid, {})[metodo] = posizione
    ordinati = sorted(punteggi, key=lambda s: -punteggi[s])[:k]
    return [{**schede[s], "punteggio_rrf": punteggi[s], "posizioni": provenienza[s]} for s in ordinati]


def cerca_ibrida(db: sqlite3.Connection, query: str, comune: str, vettorizzatore: Vettorizzatore,
                 k: int = 5, k_per_metodo: int = 10) -> list[dict]:
    return fondi_rrf({
        "lessicale": cerca_lessicale(db, query, comune, k=k_per_metodo),
        "semantica": cerca_semantica(db, query, comune, vettorizzatore, k=k_per_metodo),
    }, k=k)


# --------------------------------------------------------------------------- comando

def main() -> None:
    ap = argparse.ArgumentParser(description="Calcola i vettori delle schede e prova la ricerca ibrida.")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--modello", default=MODELLO)
    ap.add_argument("--cerca", help="esegue una ricerca ibrida invece di calcolare i vettori")
    ap.add_argument("--comune", default="Napoli")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    if not args.db.is_file():
        raise SystemExit(f"Database non trovato: {args.db}\nLancia prima: uv run ecoscan-carica")
    vettorizzatore = VettorizzatoreOllama(args.modello)

    with sqlite3.connect(args.db) as db:
        if args.cerca:
            confronto = {
                "lessicale": cerca_lessicale(db, args.cerca, args.comune, k=args.k),
                "semantica": cerca_semantica(db, args.cerca, args.comune, vettorizzatore, k=args.k),
            }
            for metodo, risultati in confronto.items():
                print(f"\n## {metodo}")
                for r in risultati or [None]:
                    print(f"  {r['testo'][:50]:50} -> {r['destinazione']}" if r else "  (nessun risultato)")
            print("\n## ibrida (RRF)")
            for r in cerca_ibrida(db, args.cerca, args.comune, vettorizzatore, k=args.k):
                posizioni = ", ".join(f"{m} #{p}" for m, p in r["posizioni"].items())
                print(f"  L{r['livello']} {r['testo'][:45]:45} -> {r['destinazione']:28} [{posizioni}]")
            return

        conteggi = calcola(db, vettorizzatore)
        print(f"Vettori: {conteggi['calcolati']} calcolati, {conteggi['totale']} in totale")


if __name__ == "__main__":
    main()
