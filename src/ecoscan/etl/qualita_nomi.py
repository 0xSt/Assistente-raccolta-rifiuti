"""I nomi rimasti sgrammaticati dopo la normalizzazione.

Il Transform toglie dal nome tutto ciò che non è l'oggetto: condizioni, esempi, sinonimi.
Quasi sempre il resto è un nome pulito — "Cartone da pizza pulito" diventa "Cartone da
pizza" — ma quando la condizione sta **in mezzo** al nome, il resto può essere un frammento
di sintassi invece di un oggetto:

    "Stovaglie monouso in materiale compostabile"  ->  "Stovaglie in materiale"
    "Tovaglioli di carta bagnati o unti di cibo"   ->  "Tovaglioli di carta o di cibo"

Non è un difetto estetico. Il nome finisce nel testo indicizzato e nel confronto con
l'oggetto riconosciuto: un nome rotto è un documento che il recupero non trova mai e che il
modello non può scegliere. È un problema di retrieval travestito da problema di dati.

**Come si riconoscono.** Non dalla lunghezza né da quanto si sono accorciati: togliere
metà del nome è spesso il comportamento giusto ("Barattolo in latta (scatola di pelati,
tonno, ...)" -> "Barattolo in latta"), e i nomi corti sono spesso sigle legittime (CD, PC).
Si riconoscono dalla **grammatica**: preposizioni doppie, congiunzioni orfane, un materiale
annunciato e mai detto. Sono controlli stretti, e su 902 voci ne segnalano 5: la precisione
conta più della copertura, perché un controllo che grida al lupo viene disattivato.

I difetti trovati diventano un motivo di revisione, quindi la voce compare fra quelle "da
revisionare" di `ecoscan-transform` e si corregge come tutte le altre, con una riga in
`data/revisioni/`.

Uso:
  uv run ecoscan-nomi            # elenca le voci con un nome sospetto
"""
from __future__ import annotations

import argparse
import re

CONTROLLI: dict[str, re.Pattern] = {
    # "Stovaglie in materiale": il materiale è annunciato e la parola che lo diceva è stata
    # tolta con la condizione
    "materiale annunciato e non detto": re.compile(r"\b(in|di)\s+materiale\s*$", re.I),
    # "Tovaglioli di carta o di cibo": è rimasta la congiunzione di due condizioni
    "congiunzione seguita da preposizione": re.compile(r"\s[eo]\s+(di|in|da|per|con)\s", re.I),
    "congiunzione orfana": re.compile(r"^\s*[eo]\s|\s+[eo]\s*$", re.I),
    # "Giocattolo o elettrico": il primo termine della congiunzione era una condizione
    # ("di grosse dimensioni") ed e stato tolto, lasciando un oggetto congiunto a un aggettivo
    "congiunzione seguita da aggettivo": re.compile(
        r"^\S+\s+[eo]\s+\w+(ico|ica|ale|ato|ata|ito|ita|oso|osa|ivo|iva)\b", re.I),
    "preposizioni consecutive": re.compile(r"\b(di|in|da|per|con|a)\s+(di|in|da|per|con)\b", re.I),
    "parola ripetuta": re.compile(r"\b(\w{4,})\b\s+\1\b", re.I),
    "finisce con una preposizione": re.compile(
        r"\b(in|di|da|per|con|del|della|dei|delle|al|alla|sul)\s*$", re.I),
    "spazi doppi": re.compile(r"\s{2,}"),
}


def difetti(nome: str) -> list[str]:
    """I difetti grammaticali di un nome normalizzato. Lista vuota se il nome è sano."""
    return [etichetta for etichetta, regex in CONTROLLI.items() if regex.search(nome or "")]


def motivo(nome: str) -> str | None:
    """Il difetto come motivo di revisione, nella forma usata dal Transform."""
    trovati = difetti(nome)
    if not trovati:
        return None
    return f"nome sgrammaticato dopo la normalizzazione ({', '.join(trovati)}): verificare"


def main() -> None:
    import json

    from ecoscan.percorsi import DATI

    ap = argparse.ArgumentParser(description="Elenca le voci con un nome sospetto.")
    ap.add_argument("--comune", choices=["napoli", "torino"], help="limita a un comune")
    args = ap.parse_args()

    comuni = [args.comune] if args.comune else ["napoli", "torino"]
    totale, sospette = 0, 0
    for comune in comuni:
        percorso = DATI / "normalizzato" / f"{comune}_voci.jsonl"
        if not percorso.is_file():
            print(f"{percorso} non trovato: lancia prima uv run ecoscan-transform")
            continue
        print(f"\n{'=' * 20} {comune.upper()}")
        for riga in percorso.read_text(encoding="utf-8").splitlines():
            if not riga.strip():
                continue
            voce = json.loads(riga)
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


if __name__ == "__main__":
    main()
