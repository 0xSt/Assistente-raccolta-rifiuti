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
        trovato = ", ".join(f"{m} #{p}" for m, p in c.posizioni.items())
        print(f"  {etichetta:12} {c.testo[:42]:42} {marcatore} "
              f"{' oppure '.join(c.destinazioni)[:34]:34} [{trovato}]")

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


def main() -> None:
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
    args = ap.parse_args()
    nome_modello = args.modello or conf.MODELLO_VISIONE

    if args.diagnostica:
        from ecoscan.agente import diagnostica
        print("Impostazioni: " + " | ".join(f"{k}={v}" for k, v in conf.riepilogo().items()))
        print(f"\nVerifico il canale immagine verso {nome_modello}...", flush=True)
        esiti = diagnostica.esegui(nome_modello, conf.OLLAMA_CHAT)
        for ok, descrizione in esiti:
            print(f"  {'OK     ' if ok else 'FALLITO'} {descrizione}")
        if all(ok for ok, _ in esiti):
            print("\nIl modello riceve e interpreta le immagini: se i riconoscimenti sono "
                  "scadenti, il problema è nei prompt o nel modello, non nel canale.")
        else:
            print("\nIl canale immagine non funziona. Finché non è risolto, ritoccare i "
                  "prompt non serve a nulla.")
        raise SystemExit(0 if all(ok for ok, _ in esiti) else 1)

    if not args.foto and not args.oggetto:
        raise SystemExit("serve --foto oppure --oggetto")
    if args.foto and not args.foto.is_file():
        raise SystemExit(f"foto non trovata: {args.foto}")
    if (args.descrivi or args.scalini) and not args.foto:
        raise SystemExit("--descrivi e --scalini richiedono --foto")
    if not args.descrivi and not args.db.is_file():
        raise SystemExit(f"Database non trovato: {args.db}\nLancia prima: uv run ecoscan-carica")

    print("Impostazioni: " + " | ".join(f"{k}={v}" for k, v in conf.riepilogo().items()))
    modello = ModelloOllama(args.modello)

    if args.scalini:
        from ecoscan.agente import diagnostica
        from ecoscan.agente.immagini import informazioni
        foto = args.foto.read_bytes()
        print(f"\nFoto originale: {informazioni(foto)}")
        print("Descrivo la stessa foto a dimensioni decrescenti...\n", flush=True)
        for lato, descrizione_immagine, risposta in diagnostica.scalini(modello.nome,
                                                                        conf.OLLAMA_CHAT, foto):
            print(f"  lato max {lato:5} ({descrizione_immagine})")
            print(f"    -> {risposta[:160]}\n", flush=True)
        print("Se le descrizioni diventano sensate solo sotto una certa misura, il problema "
              "è la dimensione dell'immagine.")
        return

    if args.descrivi:
        from ecoscan.agente.immagini import informazioni, prepara
        foto = args.foto.read_bytes()
        print(f"\nFoto originale:     {informazioni(foto)}")
        print(f"Inviata al modello: {informazioni(prepara(foto, modello.lato_max))}")
        print(f"\nChiedo a {modello.nome} di descrivere {args.foto.name}...", flush=True)
        with cronometro("descrizione"):
            descrizione = modello.descrivi(foto)
        print(f"\n## Descrizione libera\n  {descrizione.strip()}")
        print(f"\nTempo: {DURATE['descrizione']:.1f} s")
        print("\nSe la descrizione non c'entra nulla con la foto, il modello non la sta "
              "ricevendo: il problema è nel passaggio dell'immagine, non nei prompt.")
        return
    with sqlite3.connect(args.db) as db:
        comuni = [c for c, in db.execute("SELECT nome FROM comune")]
        if args.comune not in comuni:
            raise SystemExit(f"comune sconosciuto: {args.comune}. Caricati: {', '.join(comuni)}")

        qdrant = apri_qdrant()
        agente = Agente(db, qdrant, VettorizzatoreOllama(), modello, k=args.k)

        if args.oggetto:
            riconoscimento = Riconoscimento(oggetto=args.oggetto, confidenza=1.0)
            print("\n(riconoscimento saltato: oggetto fornito a mano)")
        else:
            print(f"\nLeggo {args.foto.name} con {modello.nome}... (su CPU può richiedere minuti)",
                  flush=True)
            with cronometro("riconoscimento"):
                riconoscimento = modello.riconosci(args.foto.read_bytes(), args.testo)
        stampa_riconoscimento(riconoscimento, args.testo)

        with cronometro("recupero e scelta"):
            risposta = agente.rispondi(riconoscimento, args.comune, args.testo)
        stampa_risposta(risposta)

    print("\n## Tempi")
    for fase, durata in DURATE.items():
        print(f"  {fase}: {durata:.1f} s")
    print(f"  totale: {sum(DURATE.values()):.1f} s")
    print(f"\nPrompt usati: {', '.join(risposta.contesto.get('prompt', []))}")


if __name__ == "__main__":
    main()
