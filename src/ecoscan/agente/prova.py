"""Prova dell'agente su una foto vera, dalla riga di comando.

Serve a due cose che nessun test può dire: se Gemma riconosce davvero gli oggetti in
italiano, e quanto ci mette su questo computer. I tempi per fase sono stampati apposta: su
CPU il riconoscimento domina tutto il resto, e sapere di quanto orienta le scelte successive.

Uso:
  uv run ecoscan-analizza --foto foto/bottiglia.jpg --comune Napoli
  uv run ecoscan-analizza --foto f.jpg --comune Torino --testo "è vuota"
  uv run ecoscan-analizza --oggetto "bottiglia di vetro" --comune Torino   # salta la foto
  uv run ecoscan-analizza --foto f.jpg --descrivi     # descrizione libera della foto
  uv run ecoscan-analizza --diagnostica               # il canale immagine funziona?
  uv run ecoscan-analizza --foto f.jpg --scalini      # la stessa foto a misure decrescenti
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from ecoscan import configurazione as conf
from ecoscan.agente.agente import Agente
from ecoscan.agente.modelli import ModelloOllama
from ecoscan.agente.tipi import Riconoscimento, Risposta
from ecoscan.db.vettorizza import DB, VettorizzatoreOllama, apri_qdrant

DURATE: dict[str, float] = {}


@contextmanager
def cronometro(nome: str):
    inizio = time.monotonic()
    try:
        yield
    finally:
        DURATE[nome] = time.monotonic() - inizio


def stampa_riconoscimento(r: Riconoscimento, testo_utente: str | None = None) -> None:
    print("\n## Riconoscimento")
    print(f"  oggetto:     {r.oggetto or '(non riconosciuto)'}")
    print(f"  sinonimi:    {', '.join(r.sinonimi) or '-'}")
    print(f"  categoria:   {r.categoria or '-'}")
    print(f"  materiali:   {', '.join(r.materiali) or '-'}")
    print(f"  stato:       {r.stato or '-'}")
    if r.componenti:
        print(f"  componenti:  {', '.join(r.componenti)}")
    print(f"  confidenza:  {r.confidenza:.2f}")
    if r.note:
        print(f"  note:        {r.note}")
    from ecoscan.agente.agente import domande
    print(f"  domande poste all'indice: "
          f"{', '.join(repr(q) for q in domande(r, testo_utente))}")


def stampa_risposta(risposta: Risposta) -> None:
    print(f"\n## Candidati valutati ({len(risposta.candidati)})")
    for c in risposta.candidati:
        marcatore = "->" if c.destinazioni else "  "
        etichetta = f"L{c.livello}" + (f" {c.polarita}" if c.polarita else "")
        origine = f"codice {c.per_codice}" if c.per_codice else f"{c.punteggio:.3f}"
        print(f"  {etichetta:12} {c.testo[:52]:52} {marcatore} "
              f"{' oppure '.join(c.destinazioni)[:26]:26} [{origine}]")

    print(f"\n## Risposta (livello di evidenza {risposta.livello_evidenza})")
    if risposta.destinazioni:
        verbo = {"escluso": "NON va in", "ammesso": "va in"}.get(risposta.polarita, "va in")
        print(f"  {verbo}: {' oppure '.join(risposta.destinazioni)}")
    else:
        print("  nessuna destinazione: il comune non copre questo oggetto")
    if risposta.condizioni:
        print(f"  condizione:  {', '.join(risposta.condizioni)}")
    if risposta.avvertenza:
        print(f"  avvertenza:  {risposta.avvertenza}")
    if risposta.fonte:
        print(f"  fonte:       {risposta.fonte} ({risposta.riferimento})")
    if risposta.chiarimento:
        print(f"  DA CHIEDERE: {risposta.chiarimento}")
    if risposta.tipo_corrispondenza:
        print(f"  corrisponde: {risposta.tipo_corrispondenza}")
    print(f"  motivo:      {risposta.motivo}")
    print(f"  definitiva:  {'sì' if risposta.definitiva else 'no'}")


def _argomenti() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Prova l'agente su una foto o su un oggetto descritto.")
    ap.add_argument("--foto", type=Path, help="immagine da analizzare")
    ap.add_argument("--oggetto", help="salta la foto e parte da questa descrizione")
    ap.add_argument("--comune", default="Napoli")
    ap.add_argument("--testo", help="informazione aggiuntiva dell'utente")
    ap.add_argument("--modello", help="sovrascrive ECOSCAN_MODELLO_VISIONE, per confrontare modelli")
    ap.add_argument("--diagnostica", action="store_true",
                    help="verifica il canale immagine con un'immagine dal contenuto noto")
    ap.add_argument("--scalini", action="store_true",
                    help="descrive la stessa foto a dimensioni decrescenti, per capire se "
                         "il problema è la dimensione dell'immagine")
    ap.add_argument("--descrivi", action="store_true",
                    help="chiede solo una descrizione libera della foto, per capire se il "
                         "modello la riceve davvero")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("-k", type=int, default=10, help="quanti candidati per livello")
    return ap.parse_args()


def _controlla(args: argparse.Namespace) -> None:
    """Le condizioni che rendono la prova possibile, verificate prima di avviare il modello:
    caricarlo per poi fallire su un percorso sbagliato costa minuti."""
    if not args.foto and not args.oggetto:
        raise SystemExit("serve --foto oppure --oggetto")
    if args.foto and not args.foto.is_file():
        raise SystemExit(f"foto non trovata: {args.foto}")
    if (args.descrivi or args.scalini) and not args.foto:
        raise SystemExit("--descrivi e --scalini richiedono --foto")
    if not args.descrivi and not args.db.is_file():
        raise SystemExit(f"Database non trovato: {args.db}\nLancia prima: uv run ecoscan-carica")


def _stampa_impostazioni() -> None:
    print("Impostazioni: " + " | ".join(f"{k}={v}" for k, v in conf.riepilogo().items()))


def prova_canale_immagine(nome_modello: str) -> int:
    """Il canale immagine funziona? Finché non è chiaro, ritoccare i prompt non serve."""
    from ecoscan.agente import diagnostica

    _stampa_impostazioni()
    print(f"\nVerifico il canale immagine verso {nome_modello}...", flush=True)
    esiti = diagnostica.esegui(nome_modello, conf.OLLAMA_CHAT)
    for ok, descrizione in esiti:
        print(f"  {'OK     ' if ok else 'FALLITO'} {descrizione}")
    if all(ok for ok, _ in esiti):
        print("\nIl modello riceve e interpreta le immagini: se i riconoscimenti sono "
              "scadenti, il problema è nei prompt o nel modello, non nel canale.")
        return 0
    print("\nIl canale immagine non funziona. Finché non è risolto, ritoccare i "
          "prompt non serve a nulla.")
    return 1


def prova_scalini(modello: ModelloOllama, percorso: Path) -> None:
    """La stessa foto a dimensioni decrescenti: isola i casi in cui il problema è la misura."""
    from ecoscan.agente import diagnostica
    from ecoscan.agente.immagini import informazioni

    foto = percorso.read_bytes()
    print(f"\nFoto originale: {informazioni(foto)}")
    print("Descrivo la stessa foto a dimensioni decrescenti...\n", flush=True)
    for lato, descrizione_immagine, risposta in diagnostica.scalini(modello.nome,
                                                                    conf.OLLAMA_CHAT, foto):
        print(f"  lato max {lato:5} ({descrizione_immagine})")
        print(f"    -> {risposta[:160]}\n", flush=True)
    print("Se le descrizioni diventano sensate solo sotto una certa misura, il problema "
          "è la dimensione dell'immagine.")


def prova_descrizione(modello: ModelloOllama, percorso: Path) -> None:
    """Descrizione libera: se non c'entra nulla con la foto, il modello non la sta ricevendo."""
    from ecoscan.agente.immagini import informazioni, prepara

    foto = percorso.read_bytes()
    print(f"\nFoto originale:     {informazioni(foto)}")
    print(f"Inviata al modello: {informazioni(prepara(foto, modello.lato_max))}")
    print(f"\nChiedo a {modello.nome} di descrivere {percorso.name}...", flush=True)
    with cronometro("descrizione"):
        descrizione = modello.descrivi(foto)
    print(f"\n## Descrizione libera\n  {descrizione.strip()}")
    print(f"\nTempo: {DURATE['descrizione']:.1f} s")
    print("\nSe la descrizione non c'entra nulla con la foto, il modello non la sta "
          "ricevendo: il problema è nel passaggio dell'immagine, non nei prompt.")


def _riconosci(modello: ModelloOllama, args: argparse.Namespace) -> Riconoscimento:
    if args.oggetto:
        print("\n(riconoscimento saltato: oggetto fornito a mano)")
        return Riconoscimento(oggetto=args.oggetto, confidenza=1.0)
    print(f"\nLeggo {args.foto.name} con {modello.nome}... (su CPU può richiedere minuti)",
          flush=True)
    with cronometro("riconoscimento"):
        return modello.riconosci(args.foto.read_bytes(), args.testo)


def prova_risposta(modello: ModelloOllama, args: argparse.Namespace) -> None:
    """Il percorso completo: riconoscimento, recupero, scelta, risposta e tempi."""
    with sqlite3.connect(args.db) as db:
        comuni = [c for c, in db.execute("SELECT nome FROM comune")]
        if args.comune not in comuni:
            raise SystemExit(f"comune sconosciuto: {args.comune}. Caricati: {', '.join(comuni)}")

        agente = Agente(apri_qdrant(), VettorizzatoreOllama(), modello, k=args.k)
        riconoscimento = _riconosci(modello, args)
        stampa_riconoscimento(riconoscimento, args.testo)

        with cronometro("recupero e scelta"):
            risposta = agente.rispondi(riconoscimento, args.comune, args.testo)
        stampa_risposta(risposta)

    print("\n## Tempi")
    for fase, durata in DURATE.items():
        print(f"  {fase}: {durata:.1f} s")
    print(f"  totale: {sum(DURATE.values()):.1f} s")
    print(f"\nPrompt usati: {', '.join(risposta.contesto.get('prompt', []))}")


def main() -> None:
    args = _argomenti()
    if args.diagnostica:
        raise SystemExit(prova_canale_immagine(args.modello or conf.MODELLO_VISIONE))

    _controlla(args)
    _stampa_impostazioni()
    modello = ModelloOllama(args.modello)

    if args.scalini:
        prova_scalini(modello, args.foto)
    elif args.descrivi:
        prova_descrizione(modello, args.foto)
    else:
        prova_risposta(modello, args)


if __name__ == "__main__":
    main()
