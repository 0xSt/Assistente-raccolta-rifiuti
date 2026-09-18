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
from datetime import datetime, UTC
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

def _inserisci_comuni(db: sqlite3.Connection, voci: list[dict]) -> dict[str, int]:
    return {nome: db.execute("INSERT INTO comune (nome, gestore) VALUES (?, ?)",
                             (nome, GESTORI.get(nome, "?"))).lastrowid
            for nome in sorted({v["comune"] for v in voci})}


def _inserisci_destinazioni(db: sqlite3.Connection, destinazioni: list[dict],
                            comuni: dict[str, int]) -> dict[tuple[str, str], int]:
    """Destinazioni e loro alias, con la mappa (comune, nome) -> id che serve a tutto il resto.

    Gli alias si inseriscono dopo, perché puntano a una destinazione che deve già esistere,
    e nella mappa portano all'id del bersaglio: una voce che usa l'alias finisce nel posto
    giusto senza saperlo.
    """
    db.executemany("INSERT INTO flusso VALUES (?)",
                   [(f,) for f in sorted({f for d in destinazioni for f in d["flussi"]})])

    dest_id: dict[tuple[str, str], int] = {}
    for d in (x for x in destinazioni if not x["alias_di"]):
        chiave = (d["comune"], d["nome"])
        dest_id[chiave] = db.execute(
            """INSERT INTO destinazione (comune_id, nome, canale, colore, etichetta, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (comuni[d["comune"]], d["nome"], d["canale"], d["colore"] or None,
             d.get("etichetta") or d["nome"], d["note"] or None)).lastrowid
        db.executemany("INSERT INTO destinazione_flusso VALUES (?, ?)",
                       [(dest_id[chiave], f) for f in d["flussi"]])

    for d in (x for x in destinazioni if x["alias_di"]):
        bersaglio = dest_id[(d["comune"], d["alias_di"])]
        db.execute("INSERT INTO destinazione_alias VALUES (?, ?)", (bersaglio, d["nome"]))
        dest_id[(d["comune"], d["nome"])] = bersaglio
    return dest_id


def _inserisci_voci(db: sqlite3.Connection, voci: list[dict], comuni: dict[str, int],
                    dest_id: dict[tuple[str, str], int]) -> None:
    for v in voci:
        revisionata = int(any(m.startswith("risolto a mano") for m in v.get("motivi", [])))
        voce_id = db.execute(
            """INSERT INTO voce (comune_id, slug, nome, nome_originale, codice_materiale,
                                 avvertenza, fonte, riferimento, revisione_manuale)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (comuni[v["comune"]], v["slug"], v["nome"], v["nome_originale"],
             v["codice_materiale"], v["avvertenza"], v.get("fonte"), v.get("riferimento"),
             revisionata)).lastrowid
        db.executemany("INSERT INTO voce_condizione VALUES (?, ?)",
                       [(voce_id, c) for c in v["condizioni"]])
        db.executemany("INSERT OR IGNORE INTO voce_alias VALUES (?, ?)",
                       [(voce_id, a) for a in v["alias"]])
        db.executemany("INSERT OR IGNORE INTO voce_destinazione VALUES (?, ?, ?)",
                       [(voce_id, dest_id[(v["comune"], d)], i)
                        for i, d in enumerate(v["destinazioni"])])


def _inserisci_regole(db: sqlite3.Connection, regole: list[dict],
                      dest_id: dict[tuple[str, str], int]) -> None:
    db.executemany(
        """INSERT INTO regola (destinazione_id, polarita, testo, dettaglio, origine, fonte,
                               riferimento)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(dest_id[(r["comune"], r["destinazione"])], r["polarita"], r["testo"], r["dettaglio"],
          r["origine"], r["fonte"], r["riferimento"]) for r in regole])


def _inserisci_decisioni(db: sqlite3.Connection, decisioni: dict[str, dict[str, list[dict]]],
                         comuni: dict[str, int]) -> int:
    righe = [(comuni[comune], slug, d["azione"], d["valore"], d["nota"])
             for comune, per_slug in decisioni.items()
             for slug, lista in per_slug.items() for d in lista]
    db.executemany("INSERT INTO decisione_revisione (comune_id, slug, azione, valore, nota) "
                   "VALUES (?, ?, ?, ?, ?)", righe)
    return len(righe)


def carica(db: sqlite3.Connection, destinazioni: list[dict], voci: list[dict],
           regole: list[dict], decisioni: dict[str, dict[str, list[dict]]]) -> dict[str, int]:
    """Costruisce il database dal livello normalizzato, tabella per tabella.

    L'ordine non è arbitrario: comuni, poi destinazioni (che li referenziano), poi voci e
    regole (che referenziano le destinazioni). Le decisioni di revisione si conservano
    perché il database dica anche cosa è stato deciso a mano, non solo il risultato.
    """
    db.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))

    comuni = _inserisci_comuni(db, voci)
    presenti = {v["comune"] for v in voci}
    dest_id = _inserisci_destinazioni(
        db, [d for d in destinazioni if d["comune"] in presenti], comuni)
    _inserisci_voci(db, voci, comuni, dest_id)
    _inserisci_regole(db, regole, dest_id)
    quante_decisioni = _inserisci_decisioni(db, decisioni, comuni)

    db.commit()
    return {"comuni": len(comuni), "destinazioni": len(set(dest_id.values())),
            "voci": len(voci), "regole": len(regole), "decisioni": quante_decisioni}


def registra_caricamento(db: sqlite3.Connection, sorgenti: dict[str, int]) -> None:
    adesso = datetime.now(UTC).isoformat()
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
