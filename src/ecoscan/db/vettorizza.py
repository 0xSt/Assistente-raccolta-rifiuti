"""Load, passaggio 3: vettori su Qdrant.

**Divisione dei ruoli.** Qdrant trova i candidati, SQLite dà la risposta. Nel payload di
ogni punto finisce solo ciò che serve a cercare e a filtrare (comune, livello, testo);
regola finale, condizioni, avvertenze e provenienza restano nel relazionale (D9).

**Filtro per comune dentro la query.** Non si cerca mai fra comuni diversi (D7). Con Qdrant
il vincolo è strutturale: è una condizione sul payload applicata durante la ricerca, non un
filtro a posteriori che si può dimenticare.

**Client configurabile.** Le impostazioni stanno nel file `.env` (modello: `.env.example`).
`ECOSCAN_QDRANT` decide dove si punta:
  - un URL (``http://localhost:6333``) usa il server, cioè il motore vero in Rust;
  - un percorso usa la modalità in-process, che non richiede né rete né container.
La modalità locale è una reimplementazione Python pensata per prototipi e test: regge
filtri, vettori sparsi e fusione RRF, ma apre la cartella in esclusiva (un processo alla
volta) e non ha dashboard. Per l'esecuzione vera si usa il container.

Uso:
  ollama pull embeddinggemma
  uv run ecoscan-vettorizza                    # indicizza le schede su Qdrant
  uv run ecoscan-vettorizza --cerca "contenitore del latte" --comune Napoli
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Protocol, Sequence

from qdrant_client import QdrantClient, models

from ecoscan import configurazione as conf
from ecoscan.db.indicizza import cerca as cerca_lessicale
from ecoscan.percorsi import DATI

DB = DATI / "ecoscan.db"
COLLEZIONE = "schede"
NOME_VETTORE = "denso"


# --------------------------------------------------------------------------- vettorizzatore

class Vettorizzatore(Protocol):
    """Interfaccia minima: sostituibile con un finto nei test o con un altro modello."""

    nome: str
    dimensione: int

    def vettorizza(self, testi: Sequence[str], come: str) -> list[list[float]]:
        ...


class VettorizzatoreOllama:
    """EmbeddingGemma via Ollama.

    Il modello distingue i prompt di documento e di interrogazione: usarli entrambi
    correttamente migliora il recupero e non costa nulla.
    """

    def __init__(self, modello: str | None = None, url: str | None = None):
        modello, url = modello or conf.MODELLO_EMBEDDING, url or conf.OLLAMA
        self.nome, self.url = modello, url
        self._dimensione: int | None = None

    @property
    def dimensione(self) -> int:
        if self._dimensione is None:
            self._dimensione = len(self.vettorizza(["prova"], "documento")[0])
        return self._dimensione

    def _prompt(self, testo: str, come: str) -> str:
        return f"task: search result | query: {testo}" if come == "query" else f"title: none | text: {testo}"

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


# --------------------------------------------------------------------------- client

def e_locale(qdrant: QdrantClient) -> bool:
    return type(qdrant._client).__name__ == "QdrantLocal"


def apri_qdrant(destinazione: str | None = None) -> QdrantClient:
    """URL -> server; percorso -> modalità in-process. Default: `ECOSCAN_QDRANT`, poi data/qdrant."""
    destinazione = destinazione or conf.QDRANT
    if destinazione.startswith(("http://", "https://")):
        return QdrantClient(url=destinazione)
    Path(destinazione).parent.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=destinazione)


def prepara_collezione(qdrant: QdrantClient, dimensione: int, ricrea: bool = False) -> None:
    if ricrea and qdrant.collection_exists(COLLEZIONE):
        qdrant.delete_collection(COLLEZIONE)
    if not qdrant.collection_exists(COLLEZIONE):
        qdrant.create_collection(
            COLLEZIONE,
            vectors_config={NOME_VETTORE: models.VectorParams(size=dimensione,
                                                              distance=models.Distance.COSINE)},
        )
        # Indici sul payload: rendono il filtro per comune efficiente e dichiarato.
        # In modalità locale non hanno effetto (il filtro resta corretto, solo non indicizzato).
        if not e_locale(qdrant):
            qdrant.create_payload_index(COLLEZIONE, "comune",
                                        field_schema=models.PayloadSchemaType.KEYWORD)
            qdrant.create_payload_index(COLLEZIONE, "livello",
                                        field_schema=models.PayloadSchemaType.INTEGER)


def schede_da_indicizzare(db: sqlite3.Connection) -> list[dict]:
    righe = db.execute("""
        SELECT s.id, c.nome, s.livello, s.tipo, s.testo, s.voce_id, s.regola_id
        FROM scheda s JOIN comune c ON c.id = s.comune_id ORDER BY s.id""").fetchall()
    return [{"id": r[0], "comune": r[1], "livello": r[2], "tipo": r[3], "testo": r[4],
             "voce_id": r[5], "regola_id": r[6]} for r in righe]


def indicizza(qdrant: QdrantClient, schede: Iterable[dict], vettorizzatore: Vettorizzatore,
              lotto: int | None = None, avanzamento=print) -> int:
    lotto = lotto or conf.LOTTO_EMBEDDING
    schede = list(schede)
    if not schede:
        return 0
    prepara_collezione(qdrant, vettorizzatore.dimensione, ricrea=True)
    avanzamento(f"Da indicizzare: {len(schede)} schede con {vettorizzatore.nome} (lotti di {lotto})")
    inizio = time.monotonic()
    for n in range(0, len(schede), lotto):
        gruppo = schede[n:n + lotto]
        vettori = vettorizzatore.vettorizza([s["testo"] for s in gruppo], "documento")
        qdrant.upsert(COLLEZIONE, points=[
            models.PointStruct(id=s["id"], vector={NOME_VETTORE: v}, payload=s)
            for s, v in zip(gruppo, vettori)])
        fatte = min(n + lotto, len(schede))
        trascorso = time.monotonic() - inizio
        avanzamento(f"  {fatte}/{len(schede)} — stimati "
                    f"{(len(schede) - fatte) * trascorso / fatte / 60:.1f} min alla fine")
    return len(schede)


# --------------------------------------------------------------------------- ricerca

def filtro(comune: str, livello: int | None = None) -> models.Filter:
    condizioni = [models.FieldCondition(key="comune", match=models.MatchValue(value=comune))]
    if livello:
        condizioni.append(models.FieldCondition(key="livello", match=models.MatchValue(value=livello)))
    return models.Filter(must=condizioni)


def cerca_semantica(qdrant: QdrantClient, query: str, comune: str, vettorizzatore: Vettorizzatore,
                    livello: int | None = None, k: int = 5) -> list[dict]:
    vettore = vettorizzatore.vettorizza([query], "query")[0]
    punti = qdrant.query_points(COLLEZIONE, query=vettore, using=NOME_VETTORE,
                                query_filter=filtro(comune, livello), limit=k).points
    return [{**p.payload, "scheda_id": p.id, "punteggio": p.score} for p in punti]


def fondi_rrf(classifiche: dict[str, list[dict]], k: int = 5, costante: int = 60) -> list[dict]:
    """Fusione per posizione, non per punteggio: BM25 e coseno non sono confrontabili.

    Qdrant sa fonderle da sé quando entrambe vengono da lui; qui la fusione resta a carico
    nostro perché una delle due classifiche arriva da FTS5, che sta in SQLite.
    """
    punteggi: dict[int, float] = {}
    schede: dict[int, dict] = {}
    posizioni: dict[int, dict[str, int]] = {}
    for metodo, risultati in classifiche.items():
        for posizione, r in enumerate(risultati, start=1):
            sid = r["scheda_id"]
            punteggi[sid] = punteggi.get(sid, 0.0) + 1.0 / (costante + posizione)
            schede.setdefault(sid, r)
            posizioni.setdefault(sid, {})[metodo] = posizione
    migliori = sorted(punteggi, key=lambda s: -punteggi[s])[:k]
    return [{**schede[s], "punteggio_rrf": punteggi[s], "posizioni": posizioni[s]} for s in migliori]


def cerca_ibrida(db: sqlite3.Connection, qdrant: QdrantClient, query: str, comune: str,
                 vettorizzatore: Vettorizzatore, k: int = 5, k_per_metodo: int = 10) -> list[dict]:
    return fondi_rrf({
        "lessicale": cerca_lessicale(db, query, comune, k=k_per_metodo),
        "semantica": cerca_semantica(qdrant, query, comune, vettorizzatore, k=k_per_metodo),
    }, k=k)


def destinazioni(db: sqlite3.Connection, scheda_id: int) -> str | None:
    """La destinazione si legge sempre dal relazionale, mai dal payload (D9)."""
    riga = db.execute("""
        SELECT (SELECT group_concat(d.nome, ' oppure ') FROM voce_destinazione vd
                  JOIN destinazione d ON d.id = vd.destinazione_id WHERE vd.voce_id = s.voce_id),
               (SELECT d.nome FROM destinazione d JOIN regola r ON r.destinazione_id = d.id
                 WHERE r.id = s.regola_id)
        FROM scheda s WHERE s.id = ?""", (scheda_id,)).fetchone()
    return (riga[0] or riga[1]) if riga else None


# --------------------------------------------------------------------------- comando

def main() -> None:
    ap = argparse.ArgumentParser(description="Indicizza le schede su Qdrant e prova la ricerca.")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--qdrant", help="URL del server oppure percorso per la modalità locale")
    ap.add_argument("--modello", default=None, help="sovrascrive ECOSCAN_MODELLO_EMBEDDING")
    ap.add_argument("--cerca", help="esegue una ricerca invece di indicizzare")
    ap.add_argument("--comune", default="Napoli")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    if not args.db.is_file():
        raise SystemExit(f"Database non trovato: {args.db}\nLancia prima: uv run ecoscan-carica")

    impostazioni = conf.riepilogo()
    print("Impostazioni: " + " | ".join(f"{k}={v}" for k, v in impostazioni.items()))
    vettorizzatore = VettorizzatoreOllama(args.modello)
    qdrant = apri_qdrant(args.qdrant)
    with sqlite3.connect(args.db) as db:
        if args.cerca:
            classifiche = {
                "lessicale": cerca_lessicale(db, args.cerca, args.comune, k=args.k),
                "semantica": cerca_semantica(qdrant, args.cerca, args.comune, vettorizzatore, k=args.k),
            }
            for metodo, risultati in classifiche.items():
                print(f"\n## {metodo}")
                for r in risultati:
                    print(f"  {r['testo'][:48]:48} -> {destinazioni(db, r['scheda_id'])}")
                if not risultati:
                    print("  (nessun risultato)")
            print("\n## ibrida (RRF)")
            for r in fondi_rrf(classifiche, k=args.k):
                trovato = ", ".join(f"{m} #{p}" for m, p in r["posizioni"].items())
                print(f"  L{r['livello']} {r['testo'][:42]:42} -> "
                      f"{str(destinazioni(db, r['scheda_id']))[:26]:26} [{trovato}]")
            return

        n = indicizza(qdrant, schede_da_indicizzare(db), vettorizzatore)
        print(f"\nIndicizzate {n} schede nella collezione '{COLLEZIONE}'")
        for comune, in db.execute("SELECT nome FROM comune ORDER BY nome"):
            conteggio = qdrant.count(COLLEZIONE, count_filter=filtro(comune)).count
            print(f"  {comune}: {conteggio} punti")


if __name__ == "__main__":
    main()
