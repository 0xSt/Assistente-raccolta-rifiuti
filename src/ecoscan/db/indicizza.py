"""Load, passaggio 2: indice lessicale.

Costruisce le **schede**, cioè le unità che la ricerca restituisce, e le indicizza con FTS5.

Una scheda è una voce (livello di evidenza 1) o una regola di categoria (livello 2). Una
voce produce PIÙ schede: una per il nome con le sue condizioni, una per ciascun alias. Sono
testi diversi che puntano alla stessa voce, e servono perché chi cerca "tetrapak" non deve
sperare che assomigli a "Cartone per bevande" (D37).

La destinazione NON entra mai nel testo indicizzato: farebbe trovare gli oggetti per
contenitore invece che per oggetto, e allontanerebbe fra loro oggetti quasi identici con
destinazioni diverse, che è proprio il caso in cui l'agente deve chiedere all'utente.

Tokenizer a trigrammi: FTS5 non ha uno stemmer italiano, quindi "bottiglia" e "bottiglie"
non coinciderebbero. I trigrammi tollerano plurali e refusi, di cui le fonti sono piene.

Uso:
  uv run ecoscan-indicizza                       # costruisce l'indice su data/ecoscan.db
  uv run ecoscan-indicizza --cerca "bicchiere di vetro" --comune Napoli
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import unicodedata
from pathlib import Path

from ecoscan.percorsi import DATI

DB = DATI / "ecoscan.db"
LUNGHEZZA_MINIMA_TERMINE = 3  # sotto i 3 caratteri il tokenizer a trigrammi non produce nulla
# Preposizioni e articoli: non aiutano a distinguere una scheda e in AND fanno danno.
# "cartone della pizza unto" falliva perché "dell" compare in "Polvere dell'aspirapolvere"
# e non in "Cartone per pizze unto": la ricerca trovava qualcosa, quindi non ripiegava su OR.
# "non" resta: distingue "Scarpe utilizzabile" da "Scarpe non utilizzabile".
PAROLE_DI_SERVIZIO = {"del", "dello", "della", "dei", "degli", "delle", "dal", "dalla",
                      "nel", "nella", "sul", "sulla", "con", "per", "tra", "fra", "una",
                      "uno", "gli", "che", "cui", "suo", "sua", "loro", "questo", "questa"}

SCHEMA_SERVING = """
DROP TABLE IF EXISTS scheda_fts;
DROP TABLE IF EXISTS scheda;

-- Unità restituita dalla ricerca. `livello` è il livello di evidenza: 1 voce, 2 regola.
CREATE TABLE scheda (
    id            INTEGER PRIMARY KEY,
    comune_id     INTEGER NOT NULL REFERENCES comune(id),
    livello       INTEGER NOT NULL CHECK (livello IN (1, 2)),
    tipo          TEXT NOT NULL CHECK (tipo IN ('voce', 'alias', 'regola')),
    voce_id       INTEGER REFERENCES voce(id),
    regola_id     INTEGER REFERENCES regola(id),
    testo         TEXT NOT NULL,
    CHECK ((voce_id IS NULL) <> (regola_id IS NULL))
);

CREATE INDEX idx_scheda_comune ON scheda(comune_id, livello);

-- L'indice è "external content": il testo vive in `scheda`, qui solo le posizioni.
CREATE VIRTUAL TABLE scheda_fts USING fts5(
    testo, content='scheda', content_rowid='id', tokenize='trigram'
);
"""


def testo_voce(nome: str, condizioni: list[str], codice: str | None = None) -> str:
    """Nome, condizioni e codice materiale insieme, come un'unica frase da cercare.

    Il codice serve per due ragioni: è la sigla che l'utente legge sull'imballaggio
    ("PAP 21"), e senza di esso "Simbolo GL o GLS" sarebbe identico per i codici 70, 71 e 72,
    rendendo le tre voci indistinguibili nella ricerca.
    """
    return " ".join([nome, *condizioni, codice or ""]).strip()


def costruisci(db: sqlite3.Connection) -> dict[str, int]:
    db.executescript(SCHEMA_SERVING)
    q = db.execute

    condizioni: dict[int, list[str]] = {}
    for voce_id, condizione in q("SELECT voce_id, condizione FROM voce_condizione ORDER BY condizione"):
        condizioni.setdefault(voce_id, []).append(condizione)

    for voce_id, comune_id, nome, codice in q(
            "SELECT id, comune_id, nome, codice_materiale FROM voce").fetchall():
        q("INSERT INTO scheda (comune_id, livello, tipo, voce_id, testo) VALUES (?, 1, 'voce', ?, ?)",
          (comune_id, voce_id, testo_voce(nome, condizioni.get(voce_id, []), codice)))

    for voce_id, comune_id, alias in q("""SELECT va.voce_id, v.comune_id, va.alias
                                          FROM voce_alias va JOIN voce v ON v.id = va.voce_id""").fetchall():
        q("INSERT INTO scheda (comune_id, livello, tipo, voce_id, testo) VALUES (?, 1, 'alias', ?, ?)",
          (comune_id, voce_id, testo_voce(alias, condizioni.get(voce_id, []))))

    # Solo le regole che descrivono cosa sta in un contenitore: le note non sono oggetti.
    # Si indicizza `testo`, non `dettaglio`: per gli esclusi di Torino il dettaglio è la frase
    # intera ("Medicinali, pile, oli... NON vanno..."), e indicizzarla renderebbe ogni oggetto
    # escluso raggiungibile con le parole di tutti gli altri. Il dettaglio si mostra, non si cerca.
    for regola_id, comune_id, testo in q("""
            SELECT r.id, d.comune_id, r.testo FROM regola r
            JOIN destinazione d ON d.id = r.destinazione_id
            WHERE r.polarita IN ('ammesso', 'escluso')""").fetchall():
        q("INSERT INTO scheda (comune_id, livello, tipo, regola_id, testo) VALUES (?, 2, 'regola', ?, ?)",
          (comune_id, regola_id, testo))

    q("INSERT INTO scheda_fts(rowid, testo) SELECT id, testo FROM scheda")
    db.commit()
    return {tipo: n for tipo, n in q("SELECT tipo, count(*) FROM scheda GROUP BY tipo")}


# --------------------------------------------------------------------------- ricerca

def radice(parola: str) -> str:
    """Toglie la vocale finale alle parole lunghe: con i trigrammi il termine deve essere una
    SOTTOSTRINGA, quindi "bicchiere" non troverebbe "Bicchieri". "bicchier" trova entrambi.

    È l'alternativa allo stemming, che FTS5 non offre per l'italiano."""
    return parola[:-1] if len(parola) >= 5 and parola[-1] in "aeio" else parola


def termini(query: str) -> list[str]:
    """Spezza la domanda in termini cercabili: senza accenti, senza parole corte, alla radice."""
    piatto = "".join(c for c in unicodedata.normalize("NFD", query.lower())
                     if unicodedata.category(c) != "Mn")
    parole = re.findall(r"[a-z0-9]+", piatto)
    utili = [p for p in parole
             if len(p) >= LUNGHEZZA_MINIMA_TERMINE and p not in PAROLE_DI_SERVIZIO]
    return [radice(p) for p in utili] or [radice(p) for p in parole
                                          if len(p) >= LUNGHEZZA_MINIMA_TERMINE]


def espressione_fts(query: str, operatore: str = "AND") -> str | None:
    if not (parole := termini(query)):
        return None
    return f" {operatore} ".join(f'"{p}"' for p in parole)


def cerca(db: sqlite3.Connection, query: str, comune: str, livello: int | None = None,
          k: int = 5) -> list[dict]:
    """Ricerca lessicale dentro un solo comune. Mai fra comuni diversi (D7).

    Prima in AND, per precisione. Se non trova nulla ripiega su OR: meglio candidati
    imperfetti da far scegliere al modello che nessun candidato.
    """
    for operatore in ("AND", "OR"):
        if (espressione := espressione_fts(query, operatore)) is None:
            return []
        if (risultati := _interroga(db, espressione, comune, livello, k)):
            for r in risultati:
                r["strategia"] = operatore.lower()
            return risultati
    return []


def _interroga(db: sqlite3.Connection, espressione: str, comune: str,
               livello: int | None, k: int) -> list[dict]:
    filtro_livello = "AND s.livello = ?" if livello else ""
    parametri = [espressione, comune] + ([livello] if livello else []) + [k]
    righe = db.execute(f"""
        SELECT s.id, s.livello, s.tipo, s.testo, bm25(scheda_fts) AS punteggio,
               v.nome, v.slug, r.polarita,
               (SELECT group_concat(d.nome, ' oppure ') FROM voce_destinazione vd
                  JOIN destinazione d ON d.id = vd.destinazione_id
                 WHERE vd.voce_id = s.voce_id) AS destinazioni_voce,
               (SELECT d.nome FROM destinazione d WHERE d.id = r.destinazione_id) AS destinazione_regola
        FROM scheda_fts JOIN scheda s ON s.id = scheda_fts.rowid
        JOIN comune c ON c.id = s.comune_id
        LEFT JOIN voce v ON v.id = s.voce_id
        LEFT JOIN regola r ON r.id = s.regola_id
        WHERE scheda_fts MATCH ? AND c.nome = ? {filtro_livello}
        ORDER BY punteggio LIMIT ?""", parametri).fetchall()
    return [{"scheda_id": r[0], "livello": r[1], "tipo": r[2], "testo": r[3], "punteggio": r[4],
             "nome": r[5], "slug": r[6], "polarita": r[7],
             "destinazione": r[8] or r[9]} for r in righe]


# --------------------------------------------------------------------------- comando

def main() -> None:
    ap = argparse.ArgumentParser(description="Costruisce l'indice lessicale e permette di provarlo.")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--cerca", help="esegue una ricerca invece di ricostruire l'indice")
    ap.add_argument("--comune", default="Napoli")
    ap.add_argument("--livello", type=int, choices=(1, 2))
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    if not args.db.is_file():
        raise SystemExit(f"Database non trovato: {args.db}\nLancia prima: uv run ecoscan-carica")

    with sqlite3.connect(args.db) as db:
        if args.cerca:
            risultati = cerca(db, args.cerca, args.comune, args.livello, args.k)
            print(f"'{args.cerca}' a {args.comune}: {len(risultati)} risultati")
            for r in risultati:
                etichetta = "voce" if r["livello"] == 1 else f"regola ({r['polarita']})"
                print(f"  [L{r['livello']} {etichetta:17}] {r['testo'][:55]:55} -> {r['destinazione']}")
            return
        conteggi = costruisci(db)
        totale = sum(conteggi.values())
        print(f"Indice costruito: {totale} schede ({', '.join(f'{k}: {v}' for k, v in conteggi.items())})")
        for comune, livello, n in db.execute("""
                SELECT c.nome, s.livello, count(*) FROM scheda s JOIN comune c ON c.id = s.comune_id
                GROUP BY 1, 2 ORDER BY 1, 2"""):
            print(f"  {comune} livello {livello}: {n} schede")


if __name__ == "__main__":
    main()
