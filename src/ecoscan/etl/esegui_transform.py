"""Esegue il Transform sul livello grezzo di Napoli e scrive le voci normalizzate.

Uso:
  uv run ecoscan-transform              # scrive data/normalizzato/napoli_voci.jsonl e stampa il rapporto
  uv run ecoscan-transform --verbose    # elenca anche tutte le voci da revisionare
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from ecoscan.etl.ispeziona_napoli import carica
from ecoscan.etl.transform_napoli import deduplica, trasforma_voce
from ecoscan.percorsi import DATI, GREZZO


def esegui(voci_grezze: list[dict]):
    trasformate = [v for v in (trasforma_voce(r) for r in voci_grezze) if v is not None]
    scartate = len(voci_grezze) - len(trasformate)
    unite, conflitti = deduplica(trasformate)
    return unite, conflitti, scartate


def rapporto(grezze: list[dict], unite, conflitti, scartate: int, verbose: bool = False) -> None:
    print(f"Voci grezze: {len(grezze)} | scartate: {scartate} | normalizzate: {len(unite)}")
    fuse = sum(len(v.slug_uniti) for v in unite)
    print(f"Voci fuse nella deduplicazione: {fuse}")

    print("\n## Condizioni estratte")
    for cond, n in Counter(c for v in unite for c in v.condizioni).most_common():
        print(f"  {n:4d}  {cond}")
    print(f"  voci con almeno una condizione: {sum(1 for v in unite if v.condizioni)}")

    print(f"\n## Alias: {sum(len(v.alias) for v in unite)} su {sum(1 for v in unite if v.alias)} voci")
    print(f"## Codici materiale: {sum(1 for v in unite if v.codice_materiale)}")

    print(f"\n## Conflitti (stesso nome e condizioni, destinazioni diverse): {len(conflitti)}")
    for gruppo in conflitti:
        print(f"  {gruppo[0].nome} {gruppo[0].condizioni or ''}")
        for v in gruppo:
            print(f"      {v.slug}: {' + '.join(v.destinazioni)}")

    da_rev = [v for v in unite if v.da_revisionare]
    print(f"\n## Da revisionare: {len(da_rev)}")
    for motivo, n in Counter(m for v in da_rev for m in v.motivi).most_common():
        print(f"  {n:4d}  {motivo}")
    if verbose:
        for v in da_rev:
            print(f"    {v.nome_originale!r} -> {v.nome!r} cond={v.condizioni} alias={v.alias}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Normalizza il livello grezzo di Napoli.")
    ap.add_argument("--file", type=Path, default=GREZZO / "napoli" / "napoli_voci.jsonl")
    ap.add_argument("--out", type=Path, default=DATI / "normalizzato" / "napoli_voci.jsonl")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    grezze = carica(args.file)
    unite, conflitti, scartate = esegui(grezze)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for v in unite:
            fh.write(json.dumps(asdict(v), ensure_ascii=False) + "\n")
    rapporto(grezze, unite, conflitti, scartate, args.verbose)
    print(f"\nScritto: {args.out}")


if __name__ == "__main__":
    main()
