"""Indicizzazione dei documenti su Qdrant e ricerca semantica.

**Una sola strategia.** La ricerca è semantica e basta: le sonde avevano mostrato che
affiancarle la ricerca lessicale non cambiava il risultato (14 su 16 in entrambi i casi,
con un caso migliorato e uno peggiorato). Restano quindi un solo indice, una sola query e
nessuna fusione da tarare.

L'unico punto in cui il lessicale era imbattibile sono i **codici materiale** ("PAP 21"):
ma un codice non è un testo da cercare, è un identificatore, e si aggancia in modo esatto.

**Divisione dei ruoli.** Qdrant contiene i documenti con il loro payload e risponde alla
domanda "quali oggetti somigliano a questo?". SQLite resta il punto di arrivo dell'ETL, da
cui i documenti si costruiscono, con i suoi vincoli di integrità.

Uso:
  uv run ecoscan-vettorizza                    # indicizza i documenti
  uv run ecoscan-vettorizza --verifica
  uv run ecoscan-vettorizza --cerca "cartone della pizza unto" --comune Napoli
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol
from collections.abc import Iterable, Sequence

from qdrant_client import QdrantClient, models

from ecoscan import configurazione as conf
from ecoscan.db.documenti import Documento, costruisci
from ecoscan.percorsi import DATI

DB = DATI / "ecoscan.db"
QDRANT_LOCALE = DATI / "qdrant"
COLLEZIONE = "documenti"
NOME_VETTORE = "denso"
# Un codice materiale è una sigla più due cifre: PAP 21, ALU 41, C/PAP 81.
CODICE_MATERIALE = re.compile(r"\b([A-Z]{1,5}(?:/[A-Z]{1,5})?)\s*[-/ ]?\s*(\d{1,2})\b", re.IGNORECASE)


# --------------------------------------------------------------------------- vettorizzatore

class Vettorizzatore(Protocol):
    nome: str
    dimensione: int

    def vettorizza(self, testi: Sequence[str], come: str) -> list[list[float]]: ...


class VettorizzatoreOllama:
    """EmbeddingGemma via Ollama."""

    def __init__(self, modello: str | None = None, url: str | None = None):
        self.nome = modello or conf.MODELLO_EMBEDDING
        self.url = url or conf.OLLAMA
        self._dimensione: int | None = None

    @property
    def dimensione(self) -> int:
        if self._dimensione is None:
            self._dimensione = len(self.vettorizza(["prova"], "documento")[0])
        return self._dimensione

    def _prompt(self, testo: str, come: str) -> str:
        """I prefissi previsti da EmbeddingGemma: misurati, migliorano il recupero
        (10 sonde su 14 con, 9 senza). Si possono spegnere con ECOSCAN_PREFISSI_EMBEDDING."""
        if not conf.PREFISSI_EMBEDDING:
            return testo
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
            raise SystemExit(f"Ollama non raggiungibile su {self.url} ({errore}).\n"
                             f"Avvialo e scarica il modello: ollama pull {self.nome}") from errore


# --------------------------------------------------------------------------- client

def e_locale(qdrant: QdrantClient) -> bool:
    return type(qdrant._client).__name__ == "QdrantLocal"


def apri_qdrant(destinazione: str | None = None) -> QdrantClient:
    """URL -> server; percorso -> modalità in-process, usata dai test."""
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
                                                              distance=models.Distance.COSINE)})
        if not e_locale(qdrant):
            for campo, tipo in (("comune", models.PayloadSchemaType.KEYWORD),
                                ("livello", models.PayloadSchemaType.INTEGER),
                                ("tipo", models.PayloadSchemaType.KEYWORD),
                                ("codice_materiale", models.PayloadSchemaType.KEYWORD)):
                qdrant.create_payload_index(COLLEZIONE, campo, field_schema=tipo)


# --------------------------------------------------------------------------- indicizzazione

def indicizza(qdrant: QdrantClient, documenti: Iterable[Documento], vettorizzatore: Vettorizzatore,
              lotto: int | None = None, avanzamento=print) -> int:
    """Indicizza i documenti indicizzabili. Ricostruzione totale: la collezione si rifà."""
    lotto = lotto or conf.LOTTO_EMBEDDING
    da_fare = [d for d in documenti if d.indicizzabile]
    if not da_fare:
        return 0
    prepara_collezione(qdrant, vettorizzatore.dimensione, ricrea=True)
    avanzamento(f"Da indicizzare: {len(da_fare)} documenti con {vettorizzatore.nome} "
                f"(lotti di {lotto})")
    inizio = time.monotonic()
    for n in range(0, len(da_fare), lotto):
        gruppo = da_fare[n:n + lotto]
        vettori = vettorizzatore.vettorizza([d.testo for d in gruppo], "documento")
        qdrant.upsert(COLLEZIONE, points=[
            models.PointStruct(id=numero, vector={NOME_VETTORE: vettore}, payload=documento.payload())
            for numero, (documento, vettore) in enumerate(zip(gruppo, vettori, strict=True), start=n + 1)])
        fatti = min(n + lotto, len(da_fare))
        trascorso = time.monotonic() - inizio
        avanzamento(f"  {fatti}/{len(da_fare)} — stimati "
                    f"{(len(da_fare) - fatti) * trascorso / fatti / 60:.1f} min alla fine")
    return len(da_fare)


def documenti_dal_database(percorso: Path | None = None) -> list[Documento]:
    percorso = percorso or DB
    if not percorso.is_file():
        raise SystemExit(f"Database non trovato: {percorso}\nLancia prima: uv run ecoscan-carica")
    with sqlite3.connect(percorso) as db:
        return costruisci(db)


# --------------------------------------------------------------------------- ricerca

def filtro(comune: str, livello: int | None = None) -> models.Filter:
    condizioni = [models.FieldCondition(key="comune", match=models.MatchValue(value=comune))]
    if livello:
        condizioni.append(models.FieldCondition(key="livello", match=models.MatchValue(value=livello)))
    return models.Filter(must=condizioni)


def cerca(qdrant: QdrantClient, query: str, comune: str, vettorizzatore: Vettorizzatore,
          livello: int | None = None, k: int = 8) -> list[dict]:
    """Ricerca semantica dentro un solo comune (D7). Nessuna fusione: una sola classifica."""
    if not query.strip():
        return []
    vettore = vettorizzatore.vettorizza([query], "query")[0]
    punti = qdrant.query_points(COLLEZIONE, query=vettore, using=NOME_VETTORE,
                                query_filter=filtro(comune, livello), limit=k).points
    return [{**p.payload, "punteggio": p.score} for p in punti]


def codici_nella_domanda(domanda: str) -> list[str]:
    """I codici stampati sugli imballaggi: "PAP 21", "ALU 41", "C/PAP 81".

    Un codice è un identificatore, non un testo da cercare: si aggancia in modo esatto.
    È l'unico caso in cui la vecchia ricerca lessicale batteva quella semantica.
    """
    return [f"{sigla.upper()} {numero}" for sigla, numero in CODICE_MATERIALE.findall(domanda)]


def cerca_per_codice(qdrant: QdrantClient, domanda: str, comune: str, k: int = 4) -> list[dict]:
    trovati: list[dict] = []
    for codice in codici_nella_domanda(domanda):
        numero = codice.split()[-1]
        punti = qdrant.scroll(COLLEZIONE, scroll_filter=filtro(comune), limit=500,
                              with_payload=True)[0]
        for p in punti:
            codici = (p.payload.get("codice_materiale") or "")
            if numero in [c.strip() for c in codici.split(",")] and p.payload not in trovati:
                trovati.append({**p.payload, "punteggio": 1.0, "per_codice": codice})
    return trovati[:k]


# --------------------------------------------------------------------------- verifica

def verifica(documenti: list[Documento], qdrant: QdrantClient, vettorizzatore: Vettorizzatore,
             campione: int = 30) -> list[tuple[bool, str]]:
    esiti: list[tuple[bool, str]] = []
    attesi = [d for d in documenti if d.indicizzabile]
    if not qdrant.collection_exists(COLLEZIONE):
        return [(False, f"la collezione '{COLLEZIONE}' non esiste: lancia ecoscan-vettorizza")]

    totale = qdrant.count(COLLEZIONE).count
    esiti.append((totale == len(attesi), f"punti in Qdrant {totale} = documenti indicizzabili {len(attesi)}"))

    for comune in sorted({d.comune for d in attesi}):
        for livello in (1, 2):
            attesi_qui = sum(1 for d in attesi if d.comune == comune and d.livello == livello)
            trovati = qdrant.count(COLLEZIONE, count_filter=filtro(comune, livello)).count
            esiti.append((attesi_qui == trovati,
                          f"{comune} livello {livello}: {trovati} punti (attesi {attesi_qui})"))

    primo = qdrant.scroll(COLLEZIONE, limit=1, with_vectors=True, with_payload=True)[0][0]
    dimensione = len(primo.vector[NOME_VETTORE])
    esiti.append((dimensione == vettorizzatore.dimensione,
                  f"dimensione dei vettori {dimensione} = quella del modello {vettorizzatore.dimensione}"))
    esiti.append((set(primo.payload) >= {"comune", "tipo", "testo", "varianti"},
                  f"payload con i campi attesi: {sorted(primo.payload)[:6]}…"))

    # Autorecupero: il testo di un documento deve ritrovare sé stesso. Si accettano le prime
    # tre posizioni perché le fonti contengono quasi sinonimi che si contendono la testa.
    passo = max(1, len(attesi) // campione)
    provini = attesi[::passo][:campione]
    centrati, mancati = 0, []
    for documento in provini:
        trovati = cerca(qdrant, documento.testo, documento.comune, vettorizzatore, k=3)
        if any(t["id"] == documento.id or t["testo"] == documento.testo for t in trovati):
            centrati += 1
        else:
            ottenuti = ", ".join(repr(t["testo"][:40]) for t in trovati) or "(nessun risultato)"
            mancati.append(f"{documento.id} -> ha trovato {ottenuti}")
    esiti.append((centrati == len(provini),
                  f"autorecupero: {centrati}/{len(provini)} documenti fra i primi 3 del proprio testo"
                  + (f" — mancati: {'; '.join(mancati[:3])}" if mancati else "")))
    return esiti


# --------------------------------------------------------------------------- comando

def main() -> None:
    ap = argparse.ArgumentParser(description="Indicizza i documenti su Qdrant e prova la ricerca.")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--qdrant", help="URL del server oppure percorso per la modalità locale")
    ap.add_argument("--modello", default=None)
    ap.add_argument("--cerca", help="esegue una ricerca invece di indicizzare")
    ap.add_argument("--comune", default="Napoli")
    ap.add_argument("--verifica", action="store_true")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    print("Impostazioni: " + " | ".join(f"{k}={v}" for k, v in conf.riepilogo().items()))
    vettorizzatore = VettorizzatoreOllama(args.modello)
    qdrant = apri_qdrant(args.qdrant)

    if args.cerca:
        for r in cerca_per_codice(qdrant, args.cerca, args.comune, k=args.k):
            print(f"  [codice {r['per_codice']}] {r['testo'][:80]}")
        print(f"\n'{args.cerca}' a {args.comune}:")
        for r in cerca(qdrant, args.cerca, args.comune, vettorizzatore, k=args.k):
            print(f"  L{r.get('livello')} {r['punteggio']:.3f}  {r['testo'][:90]}")
        return

    documenti = documenti_dal_database(args.db)
    if args.verifica:
        esiti = verifica(documenti, qdrant, vettorizzatore)
        for ok, descrizione in esiti:
            print(f"  {'OK     ' if ok else 'FALLITO'} {descrizione}")
        falliti = [d for ok, d in esiti if not ok]
        print(f"\n{len(esiti) - len(falliti)}/{len(esiti)} controlli superati")
        raise SystemExit(1 if falliti else 0)

    n = indicizza(qdrant, documenti, vettorizzatore)
    print(f"\nIndicizzati {n} documenti nella collezione '{COLLEZIONE}'")
    for comune in sorted({d.comune for d in documenti}):
        print(f"  {comune}: {qdrant.count(COLLEZIONE, count_filter=filtro(comune)).count} punti")


if __name__ == "__main__":
    main()
