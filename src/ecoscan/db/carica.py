"""Load, passaggio 1: caricamento relazionale.

Ricostruzione totale: il database viene cancellato e ricreato a ogni esecuzione. La verità
sta nei file di `data/normalizzato/` e `data/riferimento/`; il database è derivato, quindi
non serve nessuna logica di aggiornamento e il risultato è sempre lo stesso a parità di file.

I controlli che contano sono due, e falliscono invece di caricare dati zoppi:
- ogni destinazione citata da una voce o da una regola deve esistere nel file di riferimento;
- ogni destinazione dichiarata nel riferimento deve essere usata da qualcosa.

Uso:
  uv run ecoscan-carica            # ricostruisce data/ecoscan.db
  uv run ecoscan-carica --verifica # solo i controlli, senza scrivere
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ecoscan.etl import revisioni as rev
from ecoscan.percorsi import DATI, RADICE, SCHEMA_SQL

DB = DATI / "ecoscan.db"
NORMALIZZATO = DATI / "normalizzato"
DESTINAZIONI_CSV = DATI / "riferimento" / "destinazioni.csv"
GESTORI = {"Napoli": "ASIA Napoli", "Torino": "AMIAT"}
VERSIONE_CARICAMENTO = "carica-0.1"


# --------------------------------------------------------------------------- lettura

def leggi_jsonl(percorso: Path) -> list[dict]:
    if not percorso.is_file():
        return []
    return [json.loads(r) for r in percorso.read_text(encoding="utf-8").splitlines() if r.strip()]


def leggi_destinazioni(percorso: Path = DESTINAZIONI_CSV) -> list[dict]:
    if not percorso.is_file():
        raise SystemExit(f"File di riferimento mancante: {percorso}")
    with open(percorso, encoding="utf-8-sig") as fh:
        righe = [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]
    for r in righe:
        r["flussi"] = [f for f in r["flussi"].split("|") if f]
    return righe


# --------------------------------------------------------------------------- verifica

def verifica(destinazioni: list[dict], voci: list[dict], regole: list[dict]) -> None:
    """Controlla la corrispondenza fra destinazioni dichiarate e destinazioni usate."""
    # si controllano solo i comuni davvero presenti nei dati: caricarne uno solo è legittimo
    presenti = {v["comune"] for v in voci}
    dichiarate = {(d["comune"], d["nome"]) for d in destinazioni if d["comune"] in presenti}
    alias = {(d["comune"], d["nome"]): d["alias_di"] for d in destinazioni
             if d["alias_di"] and d["comune"] in presenti}

    usate = {(v["comune"], d) for v in voci for d in v["destinazioni"]}
    usate |= {(r["comune"], r["destinazione"]) for r in regole if r["comune"] in presenti}

    if (ignote := sorted(usate - dichiarate)):
        raise SystemExit(
            "Destinazioni usate dai dati ma assenti da data/riferimento/destinazioni.csv: "
            + ", ".join(f"{c}/{d}" for c, d in ignote))

    # un alias deve puntare a una destinazione che esiste davvero
    for (comune, nome), bersaglio in alias.items():
        if (comune, bersaglio) not in dichiarate:
            raise SystemExit(f"L'alias {comune}/{nome} punta a {bersaglio!r}, che non esiste")

    if (inutilizzate := sorted(dichiarate - usate - set(alias))):
        raise SystemExit(
            "Destinazioni dichiarate ma mai usate (riferimento non allineato ai dati): "
            + ", ".join(f"{c}/{d}" for c, d in inutilizzate))


# --------------------------------------------------------------------------- caricamento

def carica(db: sqlite3.Connection, destinazioni: list[dict], voci: list[dict],
           regole: list[dict], decisioni: dict[str, dict[str, list[dict]]]) -> dict[str, int]:
    q = db.execute
    db.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))

    comuni = {}
    for nome in sorted({v["comune"] for v in voci}):
        comuni[nome] = q("INSERT INTO comune (nome, gestore) VALUES (?, ?)",
                         (nome, GESTORI.get(nome, "?"))).lastrowid

    db.executemany("INSERT INTO flusso VALUES (?)",
                   [(f,) for f in sorted({f for d in destinazioni for f in d["flussi"]})])

    dest_id: dict[tuple[str, str], int] = {}
    presenti = {v["comune"] for v in voci}
    destinazioni = [d for d in destinazioni if d["comune"] in presenti]
    for d in (x for x in destinazioni if not x["alias_di"]):
        chiave = (d["comune"], d["nome"])
        dest_id[chiave] = q(
            "INSERT INTO destinazione (comune_id, nome, canale, colore, note) VALUES (?, ?, ?, ?, ?)",
            (comuni[d["comune"]], d["nome"], d["canale"], d["colore"] or None, d["note"] or None)
        ).lastrowid
        db.executemany("INSERT INTO destinazione_flusso VALUES (?, ?)",
                       [(dest_id[chiave], f) for f in d["flussi"]])
    for d in (x for x in destinazioni if x["alias_di"]):
        bersaglio = dest_id[(d["comune"], d["alias_di"])]
        q("INSERT INTO destinazione_alias VALUES (?, ?)", (bersaglio, d["nome"]))
        dest_id[(d["comune"], d["nome"])] = bersaglio  # le voci che usano l'alias puntano qui

    for v in voci:
        voce_id = q("""INSERT INTO voce (comune_id, slug, nome, nome_originale, codice_materiale,
                                         avvertenza, revisione_manuale)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (comuni[v["comune"]], v["slug"], v["nome"], v["nome_originale"],
                     v["codice_materiale"], v["avvertenza"],
                     int(any(m.startswith("risolto a mano") for m in v.get("motivi", []))))).lastrowid
        db.executemany("INSERT INTO voce_condizione VALUES (?, ?)",
                       [(voce_id, c) for c in v["condizioni"]])
        db.executemany("INSERT OR IGNORE INTO voce_alias VALUES (?, ?)",
                       [(voce_id, a) for a in v["alias"]])
        db.executemany("INSERT OR IGNORE INTO voce_destinazione VALUES (?, ?, ?)",
                       [(voce_id, dest_id[(v["comune"], d)], i) for i, d in enumerate(v["destinazioni"])])

    for r in regole:
        q("""INSERT INTO regola (destinazione_id, polarita, testo, dettaglio, origine, fonte, riferimento)
             VALUES (?, ?, ?, ?, ?, ?, ?)""",
          (dest_id[(r["comune"], r["destinazione"])], r["polarita"], r["testo"], r["dettaglio"],
           r["origine"], r["fonte"], r["riferimento"]))

    for comune, per_slug in decisioni.items():
        for slug, lista in per_slug.items():
            for d in lista:
                q("INSERT INTO decisione_revisione (comune_id, slug, azione, valore, nota) "
                  "VALUES (?, ?, ?, ?, ?)", (comuni[comune], slug, d["azione"], d["valore"], d["nota"]))

    db.commit()
    return {"comuni": len(comuni), "destinazioni": len({v for v in dest_id.values()}),
            "voci": len(voci), "regole": len(regole),
            "decisioni": sum(len(l) for p in decisioni.values() for l in p.values())}


def registra_caricamento(db: sqlite3.Connection, sorgenti: dict[str, int]) -> None:
    adesso = datetime.now(timezone.utc).isoformat()
    db.executemany("INSERT INTO caricamento VALUES (?, ?, ?, ?)",
                   [(adesso, VERSIONE_CARICAMENTO, nome, righe) for nome, righe in sorgenti.items()])
    db.commit()


# --------------------------------------------------------------------------- comando

def main() -> None:
    ap = argparse.ArgumentParser(description="Costruisce il database relazionale dai file normalizzati.")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--normalizzato", type=Path, default=NORMALIZZATO)
    ap.add_argument("--verifica", action="store_true", help="esegue solo i controlli, senza scrivere")
    args = ap.parse_args()

    destinazioni = leggi_destinazioni()
    voci = [v for comune in ("napoli", "torino")
            for v in leggi_jsonl(args.normalizzato / f"{comune}_voci.jsonl")]
    regole = leggi_jsonl(args.normalizzato / "regole.jsonl")
    if not voci:
        raise SystemExit(f"Nessuna voce in {args.normalizzato}: lancia prima uv run ecoscan-transform")

    verifica(destinazioni, voci, regole)
    if args.verifica:
        print(f"Verifica superata: {len(voci)} voci, {len(regole)} regole, "
              f"{len(destinazioni)} destinazioni dichiarate.")
        return

    presenti = {v["comune"] for v in voci}
    decisioni = {c.capitalize(): rev.carica(c) for c in ("napoli", "torino")
                 if c.capitalize() in presenti}
    args.db.parent.mkdir(parents=True, exist_ok=True)
    args.db.unlink(missing_ok=True)  # ricostruzione totale
    with sqlite3.connect(args.db) as db:
        conteggi = carica(db, destinazioni, voci, regole, decisioni)
        registra_caricamento(db, {"voci": len(voci), "regole": len(regole),
                                  "destinazioni": len(destinazioni)})
        riepilogo(db, args.db, conteggi)


def riepilogo(db: sqlite3.Connection, percorso: Path, conteggi: dict[str, int]) -> None:
    print(f"Database ricostruito: {percorso.relative_to(RADICE) if percorso.is_relative_to(RADICE) else percorso}")
    print("  " + " | ".join(f"{k}: {v}" for k, v in conteggi.items()))
    print("\n## Voci e regole per comune")
    for comune, voci, regole in db.execute("""
            SELECT c.nome,
                   (SELECT count(*) FROM voce v WHERE v.comune_id = c.id),
                   (SELECT count(*) FROM regola r JOIN destinazione d ON d.id = r.destinazione_id
                     WHERE d.comune_id = c.id)
            FROM comune c ORDER BY c.nome"""):
        print(f"  {comune}: {voci} voci, {regole} regole")

    print("\n## Destinazioni per canale")
    for canale, n in db.execute("SELECT canale, count(*) FROM destinazione GROUP BY canale ORDER BY 2 DESC"):
        print(f"  {canale}: {n}")

    print("\n## Confronto fra comuni: dove va ciascun flusso nella raccolta ordinaria")
    per_flusso = defaultdict(list)
    for flusso, comune, nome in db.execute("""
            SELECT df.flusso_codice, c.nome, d.nome FROM destinazione_flusso df
            JOIN destinazione d ON d.id = df.destinazione_id JOIN comune c ON c.id = d.comune_id
            WHERE d.canale = 'raccolta_ordinaria' ORDER BY 1, 2"""):
        per_flusso[flusso].append(f"{comune}: {nome}")
    for flusso, posti in sorted(per_flusso.items()):
        print(f"  {flusso} -> {' | '.join(posti)}")


if __name__ == "__main__":
    main()
