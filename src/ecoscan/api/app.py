"""Le API del backend.

Il backend è **senza stato**: dopo un chiarimento il client rimanda il `contesto` ricevuto,
e non esistono sessioni da creare, far scadere o perdere (decisione presa per il prototipo).

È anche di **sola lettura** sui dati: l'ETL resta una serie di comandi separati, così il
servizio che risponde alle richieste non può corrompere ciò che serve a rispondere.

Le rotte sono raggruppate per area (stato, agente, ricerca, riscontro) in funzioni separate:
`crea_app` costruisce le dipendenze e le monta, invece di essere un blocco unico in cui
ogni rotta nuova allunga la stessa funzione.

Uso:
  uv run ecoscan-api                    # http://localhost:8000/docs
"""
from __future__ import annotations

import argparse
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from collections.abc import Callable

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile

from ecoscan.api.risorse import Risorse
from ecoscan.api.schemi import (
    CandidatoUscita, Comune, Continuazione, Correzione, Destinazione, Ricerca, Riscontro,
    RispostaUscita, Salute,
)
from ecoscan.percorsi import DATI

RISCONTRI = DATI / "riscontri.jsonl"
PREFISSO = "/api/v1"
CONTESTO_NON_VALIDO = "contesto non valido: rimanda quello ricevuto da /analizza"


@dataclass(frozen=True)
class Dipendenze:
    """Ciò che ogni gruppo di rotte riceve: da dove prendere le risorse e come validare.

    Le rotte non conoscono il ciclo di vita dell'applicazione, e il ciclo di vita non
    conosce le rotte.
    """

    correnti: Callable[[], Risorse]

    def controlla_comune(self, r: Risorse, comune: str) -> None:
        noti = [c["nome"] for c in r.comuni()]
        if comune not in noti:
            raise HTTPException(
                status_code=404,
                detail=f"comune sconosciuto: {comune}. Disponibili: {', '.join(noti)}")

    def contesto_valido(self, contesto: dict, *campi: str) -> None:
        if any(campo not in contesto for campo in campi):
            raise HTTPException(status_code=400, detail=CONTESTO_NON_VALIDO)


def rotte_stato(app: FastAPI, dip: Dipendenze) -> None:
    """Cosa risponde e cosa contiene: servono a diagnosticare e a popolare l'interfaccia."""

    @app.get(f"{PREFISSO}/salute", response_model=Salute, tags=["stato"])
    def salute(r: Risorse = Depends(dip.correnti)) -> Salute:
        """Dice quali servizi rispondono: utile prima di accusare il modello."""
        return Salute(**r.salute())

    @app.get(f"{PREFISSO}/comuni", response_model=list[Comune], tags=["stato"])
    def comuni(r: Risorse = Depends(dip.correnti)) -> list[Comune]:
        return [Comune(**c) for c in r.comuni()]

    @app.get(f"{PREFISSO}/destinazioni", response_model=list[Destinazione], tags=["stato"])
    def destinazioni(comune: str, r: Risorse = Depends(dip.correnti)) -> list[Destinazione]:
        """I contenitori del comune con l'etichetta leggibile.

        Le risposte continuano a portare il nome interno ("carta_e_cartone"), che è la
        chiave dei dati; l'interfaccia lo traduce con questo elenco, che chiede una volta.
        """
        dip.controlla_comune(r, comune)
        return [Destinazione(**d) for d in r.destinazioni(comune)]


def rotte_agente(app: FastAPI, dip: Dipendenze) -> None:
    """I tre modi di parlare con l'agente: dalla foto, dopo un chiarimento, correggendolo."""

    @app.post(f"{PREFISSO}/analizza", response_model=RispostaUscita, tags=["agente"])
    async def analizza(comune: str = Form(...), foto: UploadFile = File(...),
                       testo: str | None = Form(default=None),
                       r: Risorse = Depends(dip.correnti)) -> RispostaUscita:
        """Dalla foto alla risposta. Il testo è facoltativo e aiuta nei casi dubbi."""
        dip.controlla_comune(r, comune)
        immagine = await foto.read()
        if not immagine:
            raise HTTPException(status_code=400, detail="la foto è vuota")
        return RispostaUscita.da(r.agente.analizza(immagine, comune, testo))

    @app.post(f"{PREFISSO}/continua", response_model=RispostaUscita, tags=["agente"])
    def continua(dati: Continuazione, r: Risorse = Depends(dip.correnti)) -> RispostaUscita:
        """Risposta a un chiarimento: riparte dal riconoscimento già fatto, senza rileggere
        la foto, che sarebbe il passaggio più lento."""
        dip.contesto_valido(dati.contesto, "riconoscimento", "comune")
        return RispostaUscita.da(r.agente.continua(dati.contesto, dati.risposta))

    @app.post(f"{PREFISSO}/correggi", response_model=RispostaUscita, tags=["agente"])
    def correggi(dati: Correzione, r: Risorse = Depends(dip.correnti)) -> RispostaUscita:
        """L'oggetto riconosciuto era sbagliato e l'utente dice qual è.

        Si rifanno solo ricerca e scelta: la foto non viene riletta, e il riconoscimento
        dell'utente vale più di quello del modello.
        """
        dip.contesto_valido(dati.contesto, "comune")
        dip.controlla_comune(r, dati.contesto["comune"])
        return RispostaUscita.da(r.agente.correggi(dati.contesto, dati.oggetto))


def rotte_ricerca(app: FastAPI, dip: Dipendenze) -> None:

    @app.post(f"{PREFISSO}/cerca", response_model=list[CandidatoUscita], tags=["ricerca"])
    def cerca(dati: Ricerca, r: Risorse = Depends(dip.correnti)) -> list[CandidatoUscita]:
        """Solo testo, senza modello di visione: serve alla valutazione del recupero e a
        capire cosa l'agente ha visto prima di scegliere."""
        dip.controlla_comune(r, dati.comune)
        livelli = [dati.livello] if dati.livello else [1, 2]
        trovati = [c for livello in livelli
                   for c in r.recupero.candidati([dati.domanda], dati.comune, livello=livello,
                                                 k=dati.k)]
        return [CandidatoUscita.da(c) for c in trovati]


def rotte_riscontro(app: FastAPI, dip: Dipendenze, riscontri: Path) -> None:

    @app.post(f"{PREFISSO}/riscontro", status_code=201, tags=["riscontro"])
    def riscontro(dati: Riscontro, r: Risorse = Depends(dip.correnti)) -> dict:
        """Registra il giudizio dell'utente su una risposta.

        Ogni riga è un esempio etichettato da una persona: è il modo meno costoso di
        costruire il set di valutazione, che oggi non esiste.
        """
        dip.controlla_comune(r, dati.comune)
        riga = {**dati.model_dump(), "quando": datetime.now(UTC).isoformat()}
        riscontri.parent.mkdir(parents=True, exist_ok=True)
        with open(riscontri, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(riga, ensure_ascii=False) + "\n")
        return {"registrato": True}


def crea_app(risorse: Risorse | None = None, riscontri: Path = RISCONTRI) -> FastAPI:
    """Costruisce l'applicazione. `risorse` si passa nei test; in produzione si apre da sé."""
    stato: dict[str, Risorse | None] = {"risorse": risorse}

    @asynccontextmanager
    async def ciclo(_: FastAPI):
        if stato["risorse"] is None:
            stato["risorse"] = Risorse.costruisci()
        yield
        if risorse is None and stato["risorse"]:
            stato["risorse"].chiudi()

    app = FastAPI(title="EcoScan Local", version="1", lifespan=ciclo,
                  description="Assistente per la raccolta differenziata, in locale.")

    def risorse_correnti() -> Risorse:
        if stato["risorse"] is None:
            raise HTTPException(status_code=503, detail="risorse non disponibili")
        return stato["risorse"]

    dipendenze = Dipendenze(correnti=risorse_correnti)
    rotte_stato(app, dipendenze)
    rotte_agente(app, dipendenze)
    rotte_ricerca(app, dipendenze)
    rotte_riscontro(app, dipendenze, riscontri)
    return app


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description="Avvia le API di EcoScan Local.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--ricarica", action="store_true", help="riavvia a ogni modifica del codice")
    args = ap.parse_args()
    print(f"Documentazione interattiva su http://{args.host}:{args.porta}/docs")
    uvicorn.run("ecoscan.api.app:app" if args.ricarica else crea_app(),
                host=args.host, port=args.porta, reload=args.ricarica)


app = crea_app()   # usata da uvicorn con --ricarica e dai server esterni


if __name__ == "__main__":
    main()
