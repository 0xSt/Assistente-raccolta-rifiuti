"""Estrazione dal Rifiutologo AMIAT 2025: un solo PDF, due letture.

Erano due moduli che aprivano lo stesso file con lo stesso scheletro — `_righe`, `estrai`,
`valida`, `main`, la stessa impronta sha256, le stesse tre opzioni — e differivano
nell'intervallo di pagine e in che cosa cercavano. Stanno insieme perche' sono la stessa
estrazione, e perche' quando il PDF cambia edizione cambiano tutte e due.

**Le voci** (pagine 16-22) si leggono dai testi in `Roboto-Light 8.5`; la destinazione e'
data dal marcatore colorato di 17 punti che le sta accanto: tinta piatta -> mappa dei
colori, gradiente -> impronta del glifo bianco interno, ancorata a cinque voci verificate
a vista.

**Le regole di categoria** (pagine 8-12) stanno in due schede per pagina, divise a x=310;
il ruolo di ogni riga lo decide il font. Gli ammessi sono celle di una griglia, gli esclusi
una frase in prosa che si separa solo quando ha la forma "... NON vanno/sono/rientrano".

Uso:
  uv run ecoscan-torino              # entrambe le letture
  uv run ecoscan-torino voci         # solo il dizionario A-Z
  uv run ecoscan-torino regole       # solo le regole di categoria
  uv run ecoscan-torino --diagnostica
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

from ecoscan.etl.testo import normalizza_spazi
from ecoscan.percorsi import GREZZO, PDF_TORINO

USCITA_VOCI = GREZZO / "torino" / "torino_voci_raw.csv"
USCITA_REGOLE = GREZZO / "torino" / "torino_regole.json"


def impronta(pdf: Path) -> str:
    """L'impronta del PDF accompagna ogni estrazione: dice su quale edizione vale."""
    return hashlib.sha256(pdf.read_bytes()).hexdigest()


def apri(pdf: Path):
    if not pdf.is_file():
        raise SystemExit(f"PDF non trovato: {pdf}\n"
                         f"Scaricalo dal link in docs/fonti.md e mettilo in {PDF_TORINO.parent}")
    return pymupdf.open(pdf)


# =========================================================== il dizionario A-Z (pagine 16-22)

PAGINE_DIZIONARIO = range(15, 22)  # indici 0-based delle pagine 16-22
LATO_MARCATORE = 17
VERSIONE_VOCI = "torino-0.1"

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


def estrai_dizionario(pdf: Path) -> tuple[list[dict], Counter]:
    doc = apri(pdf)
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


def valida_dizionario(righe: list[dict]) -> None:
    """Falliscono se una nuova edizione del PDF cambia layout o colori."""
    assert all(r["destinazioni_alternative"] for r in righe), "voci senza marcatore"
    assert "colore_ignoto" not in "".join(r["destinazioni_alternative"] for r in righe), "colori non mappati"
    assert len(righe) > 300, f"numero di voci sospetto: {len(righe)}"


# ================================================ le regole di categoria (pagine 8-12)

PAGINE_FRAZIONI = range(7, 12)  # indici 0-based delle pagine 8-12
META_PAGINA = 310.0             # x che separa la scheda di sinistra da quella di destra
VERSIONE_REGOLE = "torino-regole-0.1"

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


def _righe_regole(pagina) -> list[dict]:
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
    righe = _righe_regole(pagina)
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


def estrai_regole(pdf) -> list[dict]:
    doc = apri(pdf)
    schede = []
    for i in PAGINE_FRAZIONI:
        schede.extend(estrai_pagina(doc[i], i + 1))
    return schede


def valida_regole(schede: list[dict]) -> None:
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


# =========================================================================== i due comandi


def scrivi_voci(pdf: Path, out: Path, diagnostica: bool = False) -> int:
    righe, conteggio = estrai_dizionario(pdf)
    valida_dizionario(righe)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["pagina", "voce_originale", "destinazioni_alternative"])
        w.writeheader()
        w.writerows(righe)
    print(f"{len(righe)} voci -> {out} | PDF sha256 {impronta(pdf)[:16]}… "
          f"| estrattore {VERSIONE_VOCI}")
    if diagnostica:
        for imp, n in conteggio.most_common():
            print(f"  impronta con {len(imp)} forme: {n} marcatori")
    return len(righe)


def scrivi_regole(pdf: Path, out: Path, diagnostica: bool = False) -> int:
    schede = estrai_regole(pdf)
    valida_regole(schede)
    sha = impronta(pdf)
    for s in schede:
        s.update({"fonte": "amiat_rifiutologo_2025", "sha256": sha,
                  "versione_estrattore": VERSIONE_REGOLE})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schede, ensure_ascii=False, indent=1), encoding="utf-8")

    per_polarita: dict[str, int] = defaultdict(int)
    for s in schede:
        for r in s["regole"]:
            per_polarita[r["polarita"]] += 1
    print(f"{len(schede)} schede -> {out} | {per_polarita['ammesso']} ammessi, "
          f"{per_polarita['escluso']} esclusi | estrattore {VERSIONE_REGOLE}")
    if diagnostica:
        for s in schede:
            amm = [r["testo"] for r in s["regole"] if r["polarita"] == "ammesso"]
            esc = [r["testo"] for r in s["regole"] if r["polarita"] == "escluso"]
            print(f"\n## p{s['pagina']} {s['colonna']} — {s['nome_frazione']}")
            print(f"   ammessi ({len(amm)}): {amm}")
            print(f"   esclusi ({len(esc)}): {esc}")
            if s["note"]:
                print(f"   note: {s['note']}")
    return len(schede)


def main(argomenti: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Estrae dal Rifiutologo AMIAT 2025 le voci del dizionario e le regole "
                    "di categoria.")
    ap.add_argument("cosa", nargs="?", choices=["voci", "regole"],
                    help="senza argomento estrae entrambe")
    ap.add_argument("--pdf", type=Path, default=PDF_TORINO)
    ap.add_argument("--out-voci", type=Path, default=USCITA_VOCI)
    ap.add_argument("--out-regole", type=Path, default=USCITA_REGOLE)
    ap.add_argument("--diagnostica", action="store_true")
    args = ap.parse_args(argomenti)

    if args.cosa in (None, "voci"):
        scrivi_voci(args.pdf, args.out_voci, args.diagnostica)
    if args.cosa in (None, "regole"):
        scrivi_regole(args.pdf, args.out_regole, args.diagnostica)


if __name__ == "__main__":
    main()
