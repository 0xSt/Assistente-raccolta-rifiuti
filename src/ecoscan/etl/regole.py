"""Regole di categoria dal livello grezzo a quello normalizzato.

Il lavoro vero è **collegare ogni regola a una destinazione**: le fonti chiamano le schede
in un modo e le destinazioni del dizionario in un altro ("Carta e Cartone" nella pagina
frazione, "Carta e Cartoncino" nelle voci; "Imballaggi in plastica" nella scheda,
`imballaggi_plastica` nei marcatori). La corrispondenza è dichiarata qui, una volta sola,
e verificata contro le destinazioni che compaiono davvero nelle voci normalizzate.

I testi NON vengono spezzati. Una cella come "Piatti, bicchieri e bicchierini da caffè in
plastica anche sporchi" resta intera: separarla perderebbe la qualificazione che vale per
tutti i termini, lo stesso errore già corretto sulle voci composte (D27b). Per la ricerca
la cella intera funziona, perché l'embedding lavora su tutto il testo.

Uso:
  uv run ecoscan-regole            # entrambi i comuni -> data/normalizzato/regole.jsonl
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ecoscan.etl.profili import SORGENTI_REGOLE, SorgenteRegole
from ecoscan.etl.testo import normalizza_spazi
from ecoscan.percorsi import DATI, GREZZO

@dataclass
class RegolaNormalizzata:
    comune: str
    destinazione: str
    polarita: str                      # ammesso | escluso | nota
    testo: str
    dettaglio: str | None = None
    origine: str = "estrazione"        # estrazione | trascrizione_manuale
    fonte: str = ""
    riferimento: str = ""              # URL della pagina o numero di pagina del PDF
    note_frazione: list[str] = field(default_factory=list)


def _normalizza(regola: dict, comune: str, destinazione: str, fonte: str, riferimento: str,
                note: list[str]) -> RegolaNormalizzata:
    return RegolaNormalizzata(
        comune=comune, destinazione=destinazione, polarita=regola["polarita"],
        testo=normalizza_spazi(regola["testo"]),
        dettaglio=normalizza_spazi(regola["dettaglio"]) if regola.get("dettaglio") else None,
        origine=regola.get("origine", "estrazione"), fonte=fonte, riferimento=riferimento,
        note_frazione=note,
    )


def normalizza(schede: list[dict], sorgente: SorgenteRegole) -> list[RegolaNormalizzata]:
    """Le regole di una fonte, agganciate alle destinazioni del suo comune.

    Era due funzioni quasi identiche, una per comune. L'unica differenza vera erano la
    mappa delle destinazioni, la fonte e come si scrive il riferimento: tutte e tre cose
    che ora stanno nel profilo, cosi' una fonte nuova e' una riga di dati e non una
    funzione in piu'.
    """
    fuori = [s["nome_frazione"] for s in schede if s["nome_frazione"] not in sorgente.destinazioni]
    if fuori:
        raise SystemExit(f"Sezioni senza corrispondenza con una destinazione: {fuori}. "
                         f"Aggiorna DESTINAZIONE_{sorgente.comune.upper()} in etl/profili.py")
    regole = []
    for scheda in schede:
        destinazione = sorgente.destinazioni[scheda["nome_frazione"]]
        if destinazione is None:                      # sezione di servizio, non un contenitore
            continue
        note = list(scheda.get("note", []))
        if scheda.get("descrizione"):                 # solo Torino ne ha una
            note.append(scheda["descrizione"])
        riferimento = sorgente.riferimento(scheda)
        for r in scheda["regole"]:
            if not r.get("testo"):
                continue
            regole.append(_normalizza(r, sorgente.comune, destinazione, sorgente.fonte,
                                      riferimento, note))
    return regole


def verifica_destinazioni(regole: list[RegolaNormalizzata], voci_per_comune: dict[str, set[str]]) -> None:
    """Ogni destinazione citata da una regola deve esistere fra quelle usate dalle voci.

    È il controllo che smaschera una corrispondenza sbagliata: una regola agganciata a un
    contenitore inesistente non verrebbe mai raggiunta dalla ricerca a cascata.
    """
    mancanti = sorted({(r.comune, r.destinazione) for r in regole
                       if r.destinazione not in voci_per_comune.get(r.comune, set())})
    if mancanti:
        raise SystemExit("Destinazioni citate dalle regole ma assenti dalle voci: "
                         + ", ".join(f"{c}/{d}" for c, d in mancanti))


def destinazioni_delle_voci(percorso: Path) -> set[str]:
    if not percorso.is_file():
        return set()
    return {d for riga in percorso.read_text(encoding="utf-8").splitlines() if riga.strip()
            for d in json.loads(riga)["destinazioni"]}


def main(argomenti: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Normalizza le regole di categoria dei due comuni.")
    ap.add_argument("--napoli", type=Path, default=GREZZO / "napoli" / "napoli_frazioni.json")
    ap.add_argument("--torino", type=Path, default=GREZZO / "torino" / "torino_regole.json")
    ap.add_argument("--voci", type=Path, default=DATI / "normalizzato")
    ap.add_argument("--out", type=Path, default=DATI / "normalizzato" / "regole.jsonl")
    args = ap.parse_args(argomenti)

    regole: list[RegolaNormalizzata] = []
    comandi = {"Napoli": ("ecoscan-napoli", args.napoli), "Torino": ("ecoscan-torino regole", args.torino)}
    for comune, (comando, percorso) in comandi.items():
        if not percorso.is_file():
            print(f"NOTA: {percorso} non presente, salto {comune} (lancia prima {comando})")
            continue
        regole += normalizza(json.loads(percorso.read_text(encoding="utf-8")),
                             SORGENTI_REGOLE[comune])

    voci = {c: destinazioni_delle_voci(args.voci / f"{c.lower()}_voci.jsonl") for c in ("Napoli", "Torino")}
    if all(voci.values()):
        verifica_destinazioni(regole, voci)
    else:
        print("NOTA: voci normalizzate assenti, salto la verifica delle destinazioni "
              "(lancia prima ecoscan-transform)")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in regole:
            fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    print(f"\n{len(regole)} regole -> {args.out}")
    for comune in ("Napoli", "Torino"):
        del_comune = [r for r in regole if r.comune == comune]
        if not del_comune:
            continue
        per_pol = Counter(r.polarita for r in del_comune)
        manuali = sum(1 for r in del_comune if r.origine == "trascrizione_manuale")
        print(f"\n## {comune}: {len(del_comune)} regole su {len({r.destinazione for r in del_comune})} destinazioni"
              + (f", di cui {manuali} da trascrizione manuale" if manuali else ""))
        for pol in ("ammesso", "escluso", "nota"):
            if per_pol[pol]:
                print(f"   {pol}: {per_pol[pol]}")
        for dest in sorted({r.destinazione for r in del_comune}):
            conteggi = Counter(r.polarita for r in del_comune if r.destinazione == dest)
            print(f"     {dest}: {conteggi['ammesso']} ammessi, {conteggi['escluso']} esclusi")


if __name__ == "__main__":
    main()
