"""Riepilogo del livello grezzo di Napoli, letto dal JSONL già estratto.

Non scarica nulla: serve a decidere il Transform guardando i dati veri.

Uso:
  uv run ecoscan-ispeziona                 # riepilogo
  uv run ecoscan-ispeziona --campione 15   # anche un campione di voci
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ecoscan.etl.napoli_qualita import possibili_duplicati
from ecoscan.percorsi import GREZZO


def carica(percorso: Path) -> list[dict]:
    if not percorso.is_file():
        raise SystemExit(f"File non trovato: {percorso}\nLancia prima: uv run ecoscan-napoli")
    return [json.loads(r) for r in percorso.read_text(encoding="utf-8").splitlines() if r.strip()]


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
        esempio = next(v for v in voci if any(p["codice"] == codice for p in v["problemi"]))
        print(f"  {n:4d}  {codice:20s} es. {esempio['slug']}")

    with_avv = [v for v in voci if v.get("avvertenza")]
    print(f"\n## Avvertenze: {len(with_avv)}")
    for v in with_avv[:10]:
        print(f"  {v['nome_originale']}: {v['avvertenza'][:90]}")

    print("\n## Descrizioni delle destinazioni presenti")
    print(f"  voci con almeno una descrizione: {sum(1 for v in voci if v.get('descrizioni_destinazioni'))}")

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


def main() -> None:
    ap = argparse.ArgumentParser(description="Riepiloga il livello grezzo di Napoli già estratto.")
    ap.add_argument("--file", type=Path, default=GREZZO / "napoli" / "napoli_voci.jsonl")
    ap.add_argument("--campione", type=int, default=0)
    args = ap.parse_args()
    riepiloga(carica(args.file), args.campione)


if __name__ == "__main__":
    main()
