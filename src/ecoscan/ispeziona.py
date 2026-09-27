"""Gli strumenti di ispezione: guardare i dati a ogni livello, senza modificarli.

Stanno insieme e fuori da `etl/` e da `db/` per due motivi. Il primo e' che attraversano i
livelli — il grezzo, il normalizzato e i documenti costruiti dal relazionale — e mettere
un ispettore dentro il livello che ispeziona ha gia' fatto danni: `esegui_transform`
importava la lettura del JSONL da `ispeziona_napoli`, cioe' la produzione dipendeva da uno
strumento diagnostico per tre righe di `json.loads`. Il secondo e' che sono strumenti di
chi sviluppa, non passaggi della pipeline, e si distinguono a colpo d'occhio da quelli.

Nessuno di questi comandi scrive niente.

Uso:
  uv run ecoscan-ispeziona grezzo              # il livello grezzo di Napoli
  uv run ecoscan-ispeziona grezzo --campione 15
  uv run ecoscan-ispeziona nomi                # i nomi sgrammaticati dopo la normalizzazione
  uv run ecoscan-ispeziona documenti --cerca pizza --payload
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

from ecoscan.archivio import leggi_jsonl
from ecoscan.etl.testo import difetti, possibili_duplicati
from ecoscan.percorsi import DB, GREZZO, NORMALIZZATO


# ============================================================ il grezzo di Napoli

def riepiloga(voci: list[dict], campione: int = 0) -> None:
    print(f"Voci: {len(voci)}")

    print("\n## Destinazioni (quante voci per ciascuna)")
    for nome, n in Counter(d for v in voci for d in v["destinazioni"]).most_common():
        print(f"  {n:4d}  {nome}")

    print("\n## Quante destinazioni alternative per voce")
    for k, n in sorted(Counter(len(v["destinazioni"]) for v in voci).items()):
        print(f"  {k} destinazioni: {n} voci")

    print("\n## Combinazioni più frequenti")
    for combo, n in Counter(" + ".join(v["destinazioni"]) for v in voci).most_common(8):
        print(f"  {n:4d}  {combo}")

    problemi = Counter(p["codice"] for v in voci for p in v.get("problemi", []))
    print("\n## Problemi di qualità")
    for codice, n in problemi.most_common():
        esempio = next(v for v in voci
                       if any(p["codice"] == codice for p in v.get("problemi", [])))
        print(f"  {n:4d}  {codice:20s} es. {esempio['slug']}")

    with_avv = [v for v in voci if v.get("avvertenza")]
    print(f"\n## Avvertenze: {len(with_avv)}")
    for v in with_avv[:10]:
        print(f"  {v['nome_originale']}: {v['avvertenza'][:90]}")

    coperte = sum(1 for v in voci for p in v.get("problemi", []) if p["codice"] == "info_nello_slug_coperta")
    print(f"  di cui coperte da un'avvertenza pulita: {coperte}")

    # Indizi per il Transform: condizioni e voci composte
    tra_parentesi = [v["nome_originale"] for v in voci if "(" in v["nome_originale"]]
    con_virgola = [v["nome_originale"] for v in voci if "," in v["nome_originale"]]
    con_e = [v["nome_originale"] for v in voci if " e " in v["nome_originale"].lower()]
    print("\n## Indizi per il Transform")
    print(f"  nomi con parentesi (condizioni?): {len(tra_parentesi)} es. {tra_parentesi[:5]}")
    print(f"  nomi con virgola (voci composte?): {len(con_virgola)} es. {con_virgola[:5]}")
    print(f"  nomi con ' e ' (voci composte?): {len(con_e)} es. {con_e[:5]}")

    duplicati = possibili_duplicati([v["nome_originale"] for v in voci])
    print(f"\n## Possibili duplicati: {len(duplicati)} gruppi")
    for g in duplicati[:10]:
        print(f"  {g}")

    if campione:
        print(f"\n## Campione di {campione} voci")
        passo = max(1, len(voci) // campione)
        for v in voci[::passo][:campione]:
            print(f"  {v['nome_originale']} -> {' + '.join(v['destinazioni'])}")


# ============================================== i nomi dopo la normalizzazione
#
# Il Transform toglie dal nome tutto cio' che non e' l'oggetto. Quando la condizione stava
# in mezzo al nome, il resto puo' essere un frammento di sintassi invece di un oggetto: il
# controllo sta in `etl/testo.py`, qui c'e' solo il modo di sfogliarne gli esiti.


def nomi(args) -> None:
    comuni = [args.comune] if args.comune else ["napoli", "torino"]
    totale, sospette = 0, 0
    for comune in comuni:
        percorso = NORMALIZZATO / f"{comune}_voci.jsonl"
        if not percorso.is_file():
            print(f"{percorso} non trovato: lancia prima uv run ecoscan-transform")
            continue
        print(f"\n{'=' * 20} {comune.upper()}")
        for voce in leggi_jsonl(percorso):
            totale += 1
            if trovati := difetti(voce["nome"]):
                sospette += 1
                print(f"  {voce['nome']!r}")
                print(f"      originale: {voce['nome_originale']!r}")
                print(f"      slug:      {voce['slug']}")
                print(f"      difetti:   {', '.join(trovati)}")

    print(f"\n{sospette} voci sospette su {totale}")
    if sospette:
        print("\nSi correggono con una riga in data/revisioni/<comune>.csv, azione \"nome\":")
        print("  <slug>,nome,<il nome giusto>,\"nome mutilato dalla normalizzazione\"")
        print("poi si rigenera con: uv run ecoscan-transform && uv run ecoscan-carica")



# ============================================== i documenti costruiti dal relazionale


def documenti(args) -> None:
    """Costruisce i documenti e li mostra: servono a essere letti prima di indicizzarli."""
    from ecoscan.db.documenti import TIPI, costruisci

    if not args.db.is_file():
        raise SystemExit(f"Database non trovato: {args.db}\nLancia prima: uv run ecoscan-carica")

    with sqlite3.connect(args.db) as db:
        documenti = costruisci(db)

    scelti = [d for d in documenti
              if (not args.comune or d.comune == args.comune)
              and (not args.tipo or d.tipo == args.tipo)
              and (not args.cerca or args.cerca.lower() in d.testo.lower())]

    print(f"{len(documenti)} documenti in tutto "
          f"({', '.join(f'{t}: {sum(1 for d in documenti if d.tipo == t)}' for t in TIPI)}), "
          f"di cui {sum(1 for d in documenti if d.indicizzabile)} indicizzabili")
    lunghezze = sorted(len(d.testo) for d in documenti if d.indicizzabile)
    if lunghezze:
        print(f"lunghezza del testo indicizzato: minima {lunghezze[0]}, "
              f"mediana {lunghezze[len(lunghezze) // 2]}, massima {lunghezze[-1]} caratteri")
    print(f"\nMostro {min(args.n, len(scelti))} di {len(scelti)} documenti scelti:\n")
    for d in scelti[:args.n]:
        print(f"[{d.id}]")
        print(f"  {d.testo}")
        if args.payload:
            print(f"  payload: {json.dumps(d.payload(), ensure_ascii=False)[:400]}")
        print()




# ========================================================================= il comando


def main(argomenti: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Guarda i dati di EcoScan a ogni livello.")
    sotto = ap.add_subparsers(dest="cosa", required=True)

    g = sotto.add_parser("grezzo", help="riepiloga il livello grezzo di Napoli")
    g.add_argument("--file", type=Path, default=GREZZO / "napoli" / "napoli_voci.jsonl")
    g.add_argument("--campione", type=int, default=0)

    n = sotto.add_parser("nomi", help="elenca le voci con un nome sospetto")
    n.add_argument("--comune", choices=["napoli", "torino"], help="limita a un comune")

    d = sotto.add_parser("documenti", help="costruisce e mostra i documenti da indicizzare")
    d.add_argument("--db", type=Path, default=DB)
    d.add_argument("--comune")
    d.add_argument("--tipo", choices=["oggetto", "regola", "destinazione"])
    d.add_argument("--cerca", help="solo i documenti il cui testo contiene questa parola")
    d.add_argument("-n", type=int, default=8, help="quanti mostrarne")
    d.add_argument("--payload", action="store_true", help="mostra anche il payload")

    args = ap.parse_args(argomenti)
    if args.cosa == "grezzo":
        riepiloga(leggi_jsonl(args.file, "ecoscan-napoli"), args.campione)
    elif args.cosa == "nomi":
        nomi(args)
    else:
        documenti(args)


if __name__ == "__main__":
    main()
