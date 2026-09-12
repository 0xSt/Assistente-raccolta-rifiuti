"""Estrattore delle regole di categoria di Torino (Rifiutologo AMIAT 2025, pagine 8-12).

Ogni pagina contiene DUE schede affiancate, divise dalla metà della pagina.
Il ruolo di ogni riga è dato dal font, non dalla posizione:

    Roboto-Bold 12    titolo della frazione            "Carta e cartone"
    Roboto-Light 8    celle degli oggetti ammessi      "Giornali, riviste, libri, quaderni."
    Roboto-Bold 8     etichetta del riquadro           "I RIFIUTATI"
    Roboto-Medium 8   frase delle esclusioni           "Scontrini... NON vanno conferiti nella carta!"
    Roboto-Light 8    nota di rimando, sotto la frase  "Scopri dove gettarli nelle pagine seguenti."

Gli ESCLUSI sono una frase in prosa, non un elenco: si prende la parte prima di "NON"
e si separa su virgole e congiunzioni.

Uso:
  uv run ecoscan-torino-regole [--pdf ...] [--out ...] [--diagnostica]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict

import pymupdf

from ecoscan.etl.napoli_qualita import normalizza_spazi
from ecoscan.percorsi import GREZZO, PDF_TORINO

PAGINE_FRAZIONI = range(7, 12)  # indici 0-based delle pagine 8-12
META_PAGINA = 310.0             # x che separa la scheda di sinistra da quella di destra
VERSIONE_ESTRATTORE = "torino-regole-0.1"

TITOLO = ("Roboto-Bold", 12.0)
CELLA = ("Roboto-Light", 8.0)
ETICHETTA = ("Roboto-Bold", 8.0)
ESCLUSIONE = ("Roboto-Medium", 8.0)

# Forma a ELENCO: "Medicinali, pile, oli e indumenti NON vanno gettati nel..."
# ("NON vanno", "NON sono rifiuti organici", "NON rientrano tra i rifiuti in plastica")
ELENCO_ESCLUSI = re.compile(r"\bNON\s+(vanno|sono|rientrano)\b")
# Forma IMPERATIVA: "Non gettare pile di tipologia diversa...", "Non gettare l'olio negli scarichi".
# Non elenca oggetti esclusi: è un'avvertenza sul conferimento.
AVVERTENZA = re.compile(r"^(non|insieme)\b", re.IGNORECASE)
LARGHEZZA_CELLA = 35.0   # distanza minima fra i centri di due celle diverse
LUNGHEZZA_MAX_CELLA = 120  # oltre, è un paragrafo descrittivo, non una cella della griglia


def _righe(pagina) -> list[dict]:
    out = []
    for blocco in pagina.get_text("dict")["blocks"]:
        for linea in blocco.get("lines", []):
            testo = normalizza_spazi("".join(s["text"] for s in linea["spans"]))
            if not testo:
                continue
            span = linea["spans"][0]
            x0, y0, x1, y1 = linea["bbox"]
            out.append({"testo": testo, "font": span["font"], "size": round(span["size"], 1),
                        "x": (x0 + x1) / 2, "y": y0})
    return out


def _e(riga, stile) -> bool:
    return riga["font"] == stile[0] and abs(riga["size"] - stile[1]) < 0.2


def _celle(righe: list[dict]) -> list[str]:
    """Raggruppa le righe in celle: ogni cella è una colonnina di testo centrata."""
    gruppi: list[list[dict]] = []
    for riga in sorted(righe, key=lambda r: r["x"]):
        if gruppi and riga["x"] - gruppi[-1][-1]["x"] < LARGHEZZA_CELLA:
            gruppi[-1].append(riga)
        else:
            gruppi.append([riga])
    celle = []
    for gruppo in gruppi:
        testo = normalizza_spazi(" ".join(r["testo"] for r in sorted(gruppo, key=lambda r: r["y"])))
        if testo:
            celle.append(testo.rstrip("."))
    return celle


def classifica_frase(frase: str) -> tuple[str, list[str]]:
    """Restituisce (tipo, oggetti esclusi).

    tipo: 'elenco' se la frase elenca oggetti esclusi, 'avvertenza' se è un'istruzione,
    'assente' se non c'è frase. Una frase non riconosciuta non viene mai separata a caso.
    """
    frase = normalizza_spazi(frase)
    if not frase:
        return "assente", []
    if (m := ELENCO_ESCLUSI.search(frase)):
        soggetto = frase[:m.start()].strip(" ,")
        pezzi = [normalizza_spazi(p) for p in re.split(r",| e | o ", soggetto)]
        return "elenco", [p for p in pezzi if p]
    if AVVERTENZA.match(frase):
        return "avvertenza", []
    return "ignota", []


def estrai_pagina(pagina, numero: int) -> list[dict]:
    righe = _righe(pagina)
    schede = []
    for colonna, dentro in (("sx", lambda r: r["x"] < META_PAGINA), ("dx", lambda r: r["x"] >= META_PAGINA)):
        della_colonna = [r for r in righe if dentro(r)]
        titoli = [r for r in della_colonna if _e(r, TITOLO)]
        if not titoli:
            continue
        nome = normalizza_spazi(" ".join(r["testo"] for r in sorted(titoli, key=lambda r: r["y"])))
        y_titolo = max(r["y"] for r in titoli)

        etichette = [r for r in della_colonna if _e(r, ETICHETTA)]
        y_riquadro = min((r["y"] for r in etichette), default=float("inf"))
        nome_riquadro = min(etichette, key=lambda r: r["y"])["testo"] if etichette else None

        # le celle stanno fra il titolo e il riquadro; l'eventuale testo introduttivo
        # della scheda sta più in alto e viene escluso dallo stesso intervallo
        celle = _celle([r for r in della_colonna if _e(r, CELLA) and y_titolo + 60 < r["y"] < y_riquadro])
        # Farmaci, Oli esausti e Ingombranti non hanno la griglia: solo testo descrittivo.
        # Un blocco lungo rivela il paragrafo, e allora nessuna cella è un oggetto ammesso.
        if any(len(c) > LUNGHEZZA_MAX_CELLA for c in celle):
            descrizione, celle = " ".join(celle), []
        else:
            descrizione = None
        introduzione = _celle([r for r in della_colonna if _e(r, CELLA) and y_titolo < r["y"] <= y_titolo + 60])

        esclusione = [r for r in della_colonna if _e(r, ESCLUSIONE) and r["y"] > y_riquadro]
        frase = normalizza_spazi(" ".join(r["testo"] for r in sorted(esclusione, key=lambda r: r["y"])))
        tipo_frase, esclusi = classifica_frase(frase)
        frase_intera = frase or None
        y_frase = max((r["y"] for r in esclusione), default=y_riquadro)
        note = _celle([r for r in della_colonna if _e(r, CELLA) and r["y"] > y_frase])

        regole = [{"polarita": "ammesso", "testo": c, "dettaglio": None} for c in celle]
        regole += [{"polarita": "escluso", "testo": e, "dettaglio": frase_intera} for e in esclusi]
        if tipo_frase in ("avvertenza", "ignota"):
            regole.append({"polarita": "nota", "testo": frase_intera, "dettaglio": None})
        schede.append({"pagina": numero, "colonna": colonna, "nome_frazione": nome,
                       "introduzione": " ".join(introduzione) or None,
                       "descrizione": descrizione,
                       "nome_riquadro": nome_riquadro, "frase_esclusioni": frase_intera,
                       "tipo_frase": tipo_frase, "regole": regole, "note": note})
    return schede


def estrai(pdf) -> list[dict]:
    doc = pymupdf.open(pdf)
    schede = []
    for i in PAGINE_FRAZIONI:
        schede.extend(estrai_pagina(doc[i], i + 1))
    return schede


def valida(schede: list[dict]) -> None:
    assert len(schede) >= 8, f"trovate solo {len(schede)} schede: layout cambiato?"
    senza_ammessi = [s["nome_frazione"] for s in schede
                     if not any(r["polarita"] == "ammesso" for r in s["regole"])]
    assert len(senza_ammessi) <= 4, f"troppe schede senza ammessi: {senza_ammessi}"
    # un elenco riconosciuto deve produrre oggetti; una frase di forma ignota va guardata
    mute = [s["nome_frazione"] for s in schede if s["tipo_frase"] == "elenco"
            and not any(r["polarita"] == "escluso" for r in s["regole"])]
    assert not mute, f"elenco di esclusioni non separato in: {mute}"
    ignote = [s["nome_frazione"] for s in schede if s["tipo_frase"] == "ignota"]
    assert not ignote, f"frase di forma non riconosciuta in: {ignote}: controlla il testo"


def main() -> None:
    ap = argparse.ArgumentParser(description="Estrae le regole di categoria di Torino dal Rifiutologo.")
    ap.add_argument("--pdf", type=type(PDF_TORINO), default=PDF_TORINO)
    ap.add_argument("--out", type=type(PDF_TORINO), default=GREZZO / "torino" / "torino_regole.json")
    ap.add_argument("--diagnostica", action="store_true")
    args = ap.parse_args()

    if not args.pdf.is_file():
        raise SystemExit(f"PDF non trovato: {args.pdf}")
    schede = estrai(args.pdf)
    valida(schede)
    sha = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    for s in schede:
        s.update({"fonte": "amiat_rifiutologo_2025", "sha256": sha,
                  "versione_estrattore": VERSIONE_ESTRATTORE})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(schede, ensure_ascii=False, indent=1), encoding="utf-8")

    per_polarita = defaultdict(int)
    for s in schede:
        for r in s["regole"]:
            per_polarita[r["polarita"]] += 1
    print(f"{len(schede)} schede -> {args.out} | {per_polarita['ammesso']} ammessi, "
          f"{per_polarita['escluso']} esclusi | estrattore {VERSIONE_ESTRATTORE}")
    if args.diagnostica:
        for s in schede:
            amm = [r["testo"] for r in s["regole"] if r["polarita"] == "ammesso"]
            esc = [r["testo"] for r in s["regole"] if r["polarita"] == "escluso"]
            print(f"\n## p{s['pagina']} {s['colonna']} — {s['nome_frazione']}")
            print(f"   ammessi ({len(amm)}): {amm}")
            print(f"   esclusi ({len(esc)}): {esc}")
            if s["note"]:
                print(f"   note: {s['note']}")


if __name__ == "__main__":
    main()
