"""Estrattore AMIAT Torino -> livello grezzo.

Fonte: "Il Rifiutologo | Torino", edizione 2025 (PDF), pagine 16-22 "Dove lo butto? Dalla A alla Z".
Ogni voce ha uno o più marcatori circolari vettoriali (17 pt) che indicano le destinazioni alternative:
  - tinta piatta: il colore di riempimento identifica il contenitore
  - gradiente: stesso colore per sei destinazioni, distinte dall'impronta del glifo bianco interno

Uso:
  uv run ecoscan-torino [--pdf ...] [--out ...] [--diagnostica]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from collections import Counter
from pathlib import Path

import pymupdf

from ecoscan.percorsi import GREZZO, PDF_TORINO

PAGINE_DIZIONARIO = range(15, 22)  # indici 0-based delle pagine 16-22
LATO_MARCATORE = 17
VERSIONE_ESTRATTORE = "torino-0.1"

TINTE_PIATTE = {
    (0.655, 0.664, 0.674): "rifiuto_non_recuperabile",
    (0.144, 0.252, 0.559): "vetro_e_imballaggi_metallo",
    (0.646, 0.377, 0.231): "organico",
    (0.862, 0.866, 0.871): "imballaggi_plastica",
    (0.993, 0.724, 0.075): "carta_e_cartone",
}

# Voci verificate a vista: danno il nome all'impronta del glifo a gradiente che NON è il riciclo
ANCORE_GRADIENTE = {
    "Borsine in tessuto": "abiti",
    "Divani": "rifiuti_ingombranti",
    "Farmaci scaduti": "farmaci",
    "Oli vegetali esausti* (olio da cucina)": "olio_esausto",
    "Pile e batterie": "pile",
}


def _e_marcatore(rect) -> bool:
    return abs(rect.width - LATO_MARCATORE) < 1 and abs(rect.height - LATO_MARCATORE) < 1


def estrai_marcatori(pagina) -> list[dict]:
    disegni = pagina.get_drawings(extended=True)
    marcatori = []
    for g in disegni:
        if g["type"] == "f" and g.get("fill") and _e_marcatore(g["rect"]):
            chiave = tuple(round(c, 3) for c in g["fill"])
            marcatori.append({"rect": g["rect"], "tipo": "piatto",
                              "etichetta": TINTE_PIATTE.get(chiave, f"colore_ignoto{chiave}")})
        elif g["type"] == "clip" and _e_marcatore(g["scissor"]):
            marcatori.append({"rect": g["scissor"], "tipo": "gradiente", "etichetta": None})
    glifi = [g for g in disegni if g["type"] in ("f", "s", "fs") and g["rect"].width < LATO_MARCATORE - 1]
    for m in marcatori:
        if m["tipo"] == "gradiente":
            interni = [w for w in glifi if m["rect"].contains(w["rect"].tl + (w["rect"].br - w["rect"].tl) * 0.5)]
            m["impronta"] = tuple(sorted((w["type"], round(w["rect"].width), round(w["rect"].height)) for w in interni))
    return marcatori


def estrai_voci(pagina) -> list[dict]:
    """Ogni '•' apre una voce; le righe successive nella stessa colonna la continuano."""
    span = [s for b in pagina.get_text("dict")["blocks"] for riga in b.get("lines", [])
            for s in riga["spans"]
            if s["font"] == "Roboto-Light" and abs(s["size"] - 8.5) < 0.2 and s["text"].strip()]
    span.sort(key=lambda s: (int(s["bbox"][0] // 180), s["bbox"][1], s["bbox"][0]))
    voci = []
    for s in span:
        col, testo = int(s["bbox"][0] // 180), s["text"].replace("\t", " ").strip()
        if testo.startswith("•"):
            voci.append({"col": col, "y0": s["bbox"][1], "y1": s["bbox"][3], "testo": testo.lstrip("• ").strip()})
        elif voci and voci[-1]["col"] == col:
            voci[-1]["testo"] += " " + testo
            voci[-1]["y1"] = max(voci[-1]["y1"], s["bbox"][3])
    for v in voci:
        v["testo"] = " ".join(v["testo"].split())
    return voci


def assegna(voci: list[dict], marcatori: list[dict]) -> None:
    for m in marcatori:
        cy = (m["rect"].y0 + m["rect"].y1) / 2
        col = int((m["rect"].x0 - 20) // 180)
        candidate = [v for v in voci if v["col"] == col]
        min(candidate, key=lambda v: abs((v["y0"] + v["y1"]) / 2 - cy)).setdefault("marcatori", []).append(m)


def etichetta_gradienti(voci: list[dict]) -> Counter:
    conteggio = Counter(m["impronta"] for v in voci for m in v.get("marcatori", []) if m["tipo"] == "gradiente")
    riciclo = conteggio.most_common(1)[0][0]  # l'icona più frequente è il centro di raccolta
    nomi = {riciclo: "centro_di_raccolta"}
    for v in voci:
        if (etichetta := ANCORE_GRADIENTE.get(v["testo"])):
            for m in v["marcatori"]:
                if m["tipo"] == "gradiente" and m["impronta"] != riciclo:
                    nomi[m["impronta"]] = etichetta
    ignote = set(conteggio) - set(nomi)
    assert not ignote, f"impronte di glifo non etichettate: {ignote}"
    for v in voci:
        for m in v.get("marcatori", []):
            if m["tipo"] == "gradiente":
                m["etichetta"] = nomi[m["impronta"]]
    return conteggio


def estrai(pdf: Path) -> tuple[list[dict], Counter]:
    doc = pymupdf.open(pdf)
    voci = []
    for i in PAGINE_DIZIONARIO:
        vp, mp = estrai_voci(doc[i]), estrai_marcatori(doc[i])
        assegna(vp, mp)
        for v in vp:
            v["pagina"] = i + 1
        voci.extend(vp)
    conteggio = etichetta_gradienti(voci)
    righe = [{"pagina": v["pagina"], "voce_originale": v["testo"],
              "destinazioni_alternative": "|".join(m["etichetta"] for m in sorted(v["marcatori"], key=lambda m: m["rect"].x0))}
             for v in voci]
    return righe, conteggio


def valida(righe: list[dict]) -> None:
    """Falliscono se una nuova edizione del PDF cambia layout o colori."""
    assert all(r["destinazioni_alternative"] for r in righe), "voci senza marcatore"
    assert "colore_ignoto" not in "".join(r["destinazioni_alternative"] for r in righe), "colori non mappati"
    assert len(righe) > 300, f"numero di voci sospetto: {len(righe)}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Estrae le voci del Rifiutologo AMIAT (Torino) nel livello grezzo.")
    ap.add_argument("--pdf", type=Path, default=PDF_TORINO)
    ap.add_argument("--out", type=Path, default=GREZZO / "torino" / "torino_voci_raw.csv")
    ap.add_argument("--diagnostica", action="store_true")
    args = ap.parse_args()

    if not args.pdf.is_file():
        raise SystemExit(f"PDF non trovato: {args.pdf}\nScaricalo dal link in docs/fonti.md e mettilo in {PDF_TORINO.parent}")

    righe, conteggio = estrai(args.pdf)
    valida(righe)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["pagina", "voce_originale", "destinazioni_alternative"])
        w.writeheader()
        w.writerows(righe)
    sha = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    print(f"{len(righe)} voci -> {args.out} | PDF sha256 {sha[:16]}… | estrattore {VERSIONE_ESTRATTORE}")
    if args.diagnostica:
        for impronta, n in conteggio.most_common():
            print(f"  impronta con {len(impronta)} forme: {n} marcatori")


if __name__ == "__main__":
    main()
