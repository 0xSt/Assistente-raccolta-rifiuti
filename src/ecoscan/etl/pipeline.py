"""La catena completa, dalla fonte all'indice, in un comando solo.

**Perché esiste.** I passaggi erano otto comandi da lanciare a mano nell'ordine giusto, e
l'ordine giusto era documentato in un punto solo — con dentro un errore: la
documentazione diceva di lanciare `ecoscan-carica` **due volte**, perché le regole di
categoria si normalizzavano dopo il primo caricamento. Non era un ciclo di dipendenze:
`ecoscan-regole` verifica le proprie destinazioni contro i file **normalizzati**, non
contro il database, quindi basta eseguirlo prima. La catena è lineare, e un comando che la
esegue in ordine è il posto dove quell'ordine smette di essere un pezzo di prosa che si
può sbagliare.

**Le cinque fasi.** Ognuna produce un artefatto su disco, ed è l'ingresso della
successiva::

    estrazione   fonti           -> data/grezzo/
    normalizza   grezzo          -> data/normalizzato/*_voci.jsonl
    regole       grezzo + voci   -> data/normalizzato/regole.jsonl
    carica       normalizzato    -> data/ecoscan.db
    indicizza    ecoscan.db      -> collezione Qdrant

**Quali fasi sono davvero lente.** L'estrazione di Napoli scarica da rete con una pausa
fra le richieste, e l'indicizzazione calcola un vettore per documento: sono le due che
costano minuti. Per questo l'estrazione **non** viene eseguita per difetto — il livello
grezzo è versionato e cambia solo quando cambia la fonte — e si chiede con `--da
estrazione`.

**Ogni fase si ferma al primo errore.** Una pipeline che prosegue dopo un passaggio
fallito produce un database coerente con dati vecchi, che è peggio di nessun database:
i controlli di `ecoscan-carica` non se ne accorgerebbero, perché i file ci sono.

Uso:
  uv run ecoscan-etl                     # normalizza, regole, carica, indicizza
  uv run ecoscan-etl --da estrazione     # tutto, comprese le fonti
  uv run ecoscan-etl --a carica          # si ferma prima dell'indicizzazione
  uv run ecoscan-etl --prova             # dice cosa farebbe, senza farlo
"""
from __future__ import annotations

import argparse
import time
from collections.abc import Callable

# L'ordine e' quello vero: ogni fase legge cio' che ha scritto la precedente.
FASI: tuple[str, ...] = ("estrazione", "normalizza", "regole", "carica", "indicizza")
# L'estrazione sta fuori dal percorso abituale: e' lenta, tocca la rete, e il livello
# grezzo e' versionato — si rifa' quando cambia la fonte, non a ogni modifica del codice.
PREDEFINITA = "normalizza"


def _comando(modulo: str, argomenti: list[str]) -> Callable[[], None]:
    """Una fase e' il comando che si lancerebbe a mano, chiamato con i suoi argomenti.

    L'import e' dentro la funzione perche' le fasi costano care da importare — pymupdf per
    il PDF, il client Qdrant per l'indice — e chi ne esegue due non deve pagarle tutte e
    cinque.
    """
    def esegui_fase() -> None:
        import importlib

        importlib.import_module(modulo).main(argomenti)

    return esegui_fase


AZIONI: dict[str, Callable[[], None]] = {
    # l'estrazione e' due comandi: il PDF di Torino e il sito di Napoli
    "estrazione": lambda: (_comando("ecoscan.etl.estrai_torino", [])(),
                           _comando("ecoscan.etl.estrai_napoli", [])()),
    "normalizza": _comando("ecoscan.etl.trasforma", []),
    "regole": _comando("ecoscan.etl.regole", []),
    "carica": _comando("ecoscan.db.carica", []),
    "indicizza": _comando("ecoscan.db.vettorizza", []),
}

DESCRIZIONI = {
    "estrazione": "le fonti -> data/grezzo/ (rete e PDF: e' la fase lenta)",
    "normalizza": "il grezzo -> data/normalizzato/*_voci.jsonl",
    "regole": "le regole di categoria -> data/normalizzato/regole.jsonl",
    "carica": "il normalizzato -> data/ecoscan.db (ricostruzione totale)",
    "indicizza": "il database -> collezione Qdrant (richiede Ollama)",
}


def da_a(dalla: str, alla: str) -> list[str]:
    """Le fasi da eseguire, nell'ordine. Un intervallo al contrario e' un errore d'uso."""
    inizio, fine = FASI.index(dalla), FASI.index(alla)
    if inizio > fine:
        raise SystemExit(f"Intervallo vuoto: «{dalla}» viene dopo «{alla}». "
                         f"L'ordine e': {' -> '.join(FASI)}")
    return list(FASI[inizio:fine + 1])


def esegui(fasi: list[str], prova: bool = False) -> None:
    for numero, fase in enumerate(fasi, start=1):
        print(f"\n{'=' * 60}\n[{numero}/{len(fasi)}] {fase}: {DESCRIZIONI[fase]}\n{'=' * 60}")
        if prova:
            continue
        inizio = time.monotonic()
        AZIONI[fase]()
        print(f"-- {fase}: {time.monotonic() - inizio:.1f} s")
    if prova:
        print("\n(prova: non e' stato eseguito nulla)")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Esegue la catena ETL nell'ordine: "
                    + " -> ".join(FASI))
    ap.add_argument("--da", choices=FASI, default=PREDEFINITA,
                    help=f"prima fase da eseguire (predefinita: {PREDEFINITA})")
    ap.add_argument("--a", choices=FASI, default=FASI[-1], dest="fino_a",
                    help="ultima fase da eseguire")
    ap.add_argument("--prova", action="store_true",
                    help="elenca le fasi senza eseguirle")
    args = ap.parse_args()

    fasi = da_a(args.da, args.fino_a)
    esegui(fasi, args.prova)
    if not args.prova:
        print("\nCatena completata.")


if __name__ == "__main__":
    main()
