"""Estrarre un campione stratificato di voci, da cui scrivere i casi di valutazione.

**Il problema che risolve.** I casi scritti a partire dagli errori osservati sono una suite
di regressione: preziosa, ma per costruzione concentrata sui punti in cui il sistema aveva
già sbagliato. Una percentuale calcolata lì misura la storia dei difetti, non il sistema.
Per dire "il recupero funziona all'88%" serve un campione estratto **dai dati**, non dalla
memoria di chi li ha guardati.

**La divisione del lavoro.** L'attesa non si scrive a mano: per una voce del dizionario la
risposta giusta *è* la fonte, e sta già nel database. Quello che una macchina non può
inventare è la **domanda**: come una persona nomina quell'oggetto. Quindi questo comando
scrive la bozza con l'attesa già piena e `oggetto` vuoto, e la parte umana si riduce a
riempire quella casella.

    {"comune": "Napoli", "oggetto": "", "voce_fonte": "Vasetto in plastica per alimenti",
     "destinazioni_attese": ["Plastica e Metalli"], "livello_atteso": 1,
     "strato": {"canale": "raccolta_ordinaria", "alternative": 1}}

**La regola d'oro nel compilare**: la domanda non deve mai essere il nome della fonte.
Cercare "Cartone per pizze" e trovare "Cartone per pizze" non misura il recupero, misura
che l'indice esiste. Se per una voce non viene in mente un modo diverso di dirla, quella
voce non è un buon caso e si cancella. Un test (`test_campiona.py`) fa fallire la suite se
una domanda coincide con la sua voce di origine.

**La stratificazione**, che è la parte tecnica. Il campione non è uniforme sulle 902 voci,
perché il sistema non si comporta allo stesso modo ovunque. Si stratifica su tre assi:

| asse | strati | perché |
|---|---|---|
| comune | Napoli, Torino | due fonti con difetti speculari: metà e metà, non in proporzione alle voci |
| canale | ordinaria, centro di raccolta, itinerante, domicilio, contenitore dedicato | è dove sono nati tutti gli errori osservati (microonde, divano) |
| alternative | una destinazione, più di una | senza voci a più destinazioni, la copertura dei canali non verrebbe mai messa alla prova |

Dentro ogni strato l'estrazione è casuale ma **riproducibile**: `--semina` fissa il
generatore, quindi chiunque rilanci lo stesso comando ottiene le stesse voci. È ciò che
permette di dire, in una relazione, di quale campione si sta parlando.

Le voci già usate da un caso esistente vengono saltate: un caso ripetuto gonfia le
percentuali senza misurare niente di nuovo.

Uso:
  uv run ecoscan-campiona                      # 50 voci in data/valutazione/bozza.jsonl
  uv run ecoscan-campiona --n 80 --semina 7
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ecoscan.percorsi import DATI
from ecoscan.valutazione.casi import CARTELLA, tutti

DB = DATI / "ecoscan.db"
BOZZA = DATI / "valutazione" / "bozza.jsonl"

INTERROGAZIONE = """
SELECT c.nome AS comune, v.nome AS voce, d.nome AS destinazione, d.canale AS canale
  FROM voce v
  JOIN comune c              ON c.id = v.comune_id
  JOIN voce_destinazione vd  ON vd.voce_id = v.id
  JOIN destinazione d        ON d.id = vd.destinazione_id
 ORDER BY c.nome, v.nome, vd.ordine
"""

# Il canale dello strato è il meno comodo fra quelli della voce: è quello che descrive il
# gesto che l'utente deve compiere davvero. Una voce che si può buttare nel sacco *oppure*
# portare al centro di raccolta appartiene, per la valutazione, al centro di raccolta.
SFORZO = {"raccolta_ordinaria": 0, "contenitore_dedicato": 1, "raccolta_itinerante": 2,
          "ritiro_domicilio": 3, "centro_raccolta": 4}


@dataclass
class Voce:
    comune: str
    nome: str
    destinazioni: list[str] = field(default_factory=list)
    canali: list[str] = field(default_factory=list)

    @property
    def canale(self) -> str:
        return max(self.canali, key=lambda c: SFORZO.get(c, 0))

    @property
    def strato(self) -> tuple[str, str, str]:
        alternative = "multipla" if len(self.destinazioni) > 1 else "singola"
        return self.comune, self.canale, alternative


def voci_dal_database(percorso: Path | None = None) -> list[Voce]:
    percorso = percorso or DB
    if not percorso.is_file():
        raise SystemExit(f"Database non trovato: {percorso}\nLancia prima: uv run ecoscan-carica")
    voci: dict[tuple[str, str], Voce] = {}
    with sqlite3.connect(f"file:{percorso}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        for riga in db.execute(INTERROGAZIONE):
            voce = voci.setdefault((riga["comune"], riga["voce"]),
                                   Voce(riga["comune"], riga["voce"]))
            if riga["destinazione"] not in voce.destinazioni:
                voce.destinazioni.append(riga["destinazione"])
                voce.canali.append(riga["canale"])
    return list(voci.values())


def quote(strati: dict, n: int) -> dict:
    """Quanti casi per strato: metà per comune, poi in proporzione dentro il comune.

    Il minimo di uno per strato è deliberato: gli strati piccoli (il ritiro a domicilio, il
    contenitore dedicato) sono proprio quelli in cui il sistema ha sbagliato, e una
    proporzione pura li cancellerebbe dal campione.
    """
    per_comune = defaultdict(list)
    for chiave in strati:
        per_comune[chiave[0]].append(chiave)

    assegnate: dict[tuple, int] = {}
    for chiavi in per_comune.values():
        disponibili = sum(len(strati[c]) for c in chiavi)
        bilancio = n // len(per_comune)
        for chiave in sorted(chiavi, key=lambda c: -len(strati[c])):
            quota = round(bilancio * len(strati[chiave]) / disponibili) if disponibili else 0
            assegnate[chiave] = max(1, min(quota, len(strati[chiave])))
    return assegnate


def campiona(voci: list[Voce], n: int, semina: int, escludi: set[str] | None = None
             ) -> list[Voce]:
    escludi = escludi or set()
    strati: dict[tuple, list[Voce]] = defaultdict(list)
    for voce in voci:
        if voce.nome not in escludi:
            strati[voce.strato].append(voce)

    generatore = random.Random(semina)
    estratte: list[Voce] = []
    for chiave, quota in quote(strati, n).items():
        gruppo = sorted(strati[chiave], key=lambda v: v.nome)   # ordine stabile prima di estrarre
        estratte.extend(generatore.sample(gruppo, min(quota, len(gruppo))))
    return sorted(estratte, key=lambda v: (v.comune, v.nome))


def come_bozza(voce: Voce) -> dict:
    return {"comune": voce.comune,
            "oggetto": "",                    # <- da riempire a mano: come lo direbbe una persona
            "voce_fonte": voce.nome,
            "destinazioni_attese": voce.destinazioni,
            "livello_atteso": 1,
            "origine": "campione",
            "nota": "",
            "strato": {"canale": voce.canale,
                       "alternative": len(voce.destinazioni)}}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Estrae un campione stratificato di voci da cui scrivere i casi.")
    ap.add_argument("--n", type=int, default=50, help="quante voci estrarre")
    ap.add_argument("--semina", type=int, default=42, help="fissa l'estrazione: stessa semina, stesso campione")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--uscita", type=Path, default=BOZZA)
    args = ap.parse_args()

    voci = voci_dal_database(args.db)
    gia_usate = {c.voce_fonte for c in tutti() if c.voce_fonte}
    estratte = campiona(voci, args.n, args.semina, escludi=gia_usate)

    args.uscita.parent.mkdir(parents=True, exist_ok=True)
    args.uscita.write_text(
        "\n".join(json.dumps(come_bozza(v), ensure_ascii=False) for v in estratte) + "\n",
        encoding="utf-8")

    print(f"{len(estratte)} voci estratte da {len(voci)} "
          f"(semina {args.semina}, {len(gia_usate)} già coperte e saltate)")
    for comune in sorted({v.comune for v in estratte}):
        gruppo = [v for v in estratte if v.comune == comune]
        canali = defaultdict(int)
        for v in gruppo:
            canali[v.canale] += 1
        print(f"  {comune}: {len(gruppo)} — " +
              ", ".join(f"{c} {q}" for c, q in sorted(canali.items())))
    print(f"\nScritto in {args.uscita}")
    print("Riempi il campo «oggetto» di ogni riga con il nome che userebbe una persona,\n"
          "MAI con il nome della voce, poi sposta le righe compilate in\n"
          f"{CARTELLA / 'campione.jsonl'}. Le righe che non sai riformulare, cancellale.")


if __name__ == "__main__":
    main()
