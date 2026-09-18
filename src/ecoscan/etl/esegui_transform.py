"""Esegue il Transform sul livello grezzo e scrive le voci normalizzate.

Uso:
  uv run ecoscan-transform                    # entrambi i comuni
  uv run ecoscan-transform --comune torino    # uno solo
  uv run ecoscan-transform --verbose          # elenca anche le voci da revisionare
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import csv

from ecoscan.etl.napoli_qualita import slugify_wp

from ecoscan.etl import revisioni as rev
from ecoscan.etl.ispeziona_napoli import carica
from ecoscan.etl.transform_comune import deduplica, trasforma_voce
from ecoscan.etl.transform_napoli import PROFILO_NAPOLI
from ecoscan.etl.transform_torino import PROFILO_TORINO
from ecoscan.percorsi import DATI, GREZZO

PROFILI = {"napoli": PROFILO_NAPOLI, "torino": PROFILO_TORINO}


def carica_torino(percorso: Path) -> list[dict]:
    """Il grezzo di Torino è un CSV: lo porta alla stessa forma del JSONL di Napoli.

    Lo slug è derivato dal nome, non dalla posizione: le decisioni di revisione restano
    valide anche se l'estrazione cambia l'ordine delle voci.
    """
    if not percorso.is_file():
        raise SystemExit(f"File non trovato: {percorso}\nLancia prima: uv run ecoscan-torino")
    voci, visti = [], Counter()
    with open(percorso, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            base = slugify_wp(r["voce_originale"])
            visti[base] += 1
            slug = base if visti[base] == 1 else f"{base}-{visti[base]}"
            voci.append({"slug": slug, "nome_originale": r["voce_originale"],
                         "destinazioni": r["destinazioni_alternative"].split("|"),
                         "avvertenza": None, "pagina": r["pagina"]})
    return voci


def esegui(voci_grezze: list[dict], profilo, decisioni: dict[str, list[dict]] | None = None):
    decisioni = decisioni or {}
    rev.verifica_slug(decisioni, {r["slug"] for r in voci_grezze}, profilo.comune)
    trasformate = []
    for record in voci_grezze:
        prese = decisioni.get(record["slug"], [])
        voce = trasforma_voce(record, profilo, separa=not rev.vietata_separazione(prese))
        if voce is not None and (voce := rev.applica(voce, prese)) is not None:
            trasformate.append(voce)
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

    risolte = sum(1 for v in unite if any(m.startswith("risolto a mano") for m in v.motivi))
    da_rev = [v for v in unite if v.da_revisionare]
    print(f"\n## Risolte da revisioni manuali: {risolte}")
    print(f"## Da revisionare: {len(da_rev)}")
    for motivo, n in Counter(m for v in da_rev for m in v.motivi).most_common():
        print(f"  {n:4d}  {motivo}")
    if verbose:
        for v in da_rev:
            print(f"    {v.nome_originale!r} -> {v.nome!r} cond={v.condizioni} alias={v.alias}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Normalizza il livello grezzo di un comune.")
    ap.add_argument("--comune", choices=[*PROFILI, "tutti"], default="tutti")
    ap.add_argument("--file", type=Path, help="sovrascrive il percorso del grezzo")
    ap.add_argument("--out", type=Path, help="sovrascrive il percorso di uscita")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    comuni = list(PROFILI) if args.comune == "tutti" else [args.comune]
    for comune in comuni:
        print(f"\n{'=' * 20} {comune.upper()}")
        if comune == "napoli":
            sorgente = args.file or GREZZO / "napoli" / "napoli_voci.jsonl"
            grezze = carica(sorgente)
        else:
            sorgente = args.file or GREZZO / "torino" / "torino_voci_raw.csv"
            grezze = carica_torino(sorgente)
        decisioni = rev.carica(comune)
        unite, conflitti, scartate = esegui(grezze, PROFILI[comune], decisioni)
        out = args.out or DATI / "normalizzato" / f"{comune}_voci.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            for v in unite:
                fh.write(json.dumps(asdict(v), ensure_ascii=False) + "\n")
        rapporto(grezze, unite, conflitti, scartate, args.verbose)
        print(f"Scritto: {out}")


if __name__ == "__main__":
    main()
