"""Le API del backend.

Il backend è **senza stato**: dopo un chiarimento il client rimanda il `contesto` ricevuto,
e non esistono sessioni da creare, far scadere o perdere (decisione presa per il prototipo).

È anche di **sola lettura** sui dati: l'ETL resta una serie di comandi separati, così il
servizio che risponde alle richieste non può corrompere ciò che serve a rispondere.

Uso:
  uv run ecoscan-api                    # http://localhost:8000/docs
"""
from __future__ import annotations

import argparse
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile

from ecoscan.agente.recupero import candidati as recupera
from ecoscan.api.risorse import Risorse
from ecoscan.api.schemi import (
    CandidatoUscita, Comune, Continuazione, Ricerca, Riscontro, RispostaUscita, Salute,
)
from ecoscan.percorsi import DATI

RISCONTRI = DATI / "riscontri.jsonl"
PREFISSO = "/api/v1"


def crea_app(risorse: Risorse | None = None, riscontri: Path = RISCONTRI) -> FastAPI:
    """Costruisce l'applicazione. `risorse` si passa nei test; in produzione si apre da sé."""
    stato: dict[str, Risorse | None] = {"risorse": risorse}

    @asynccontextmanager
    async def ciclo(app: FastAPI):
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

    def controlla_comune(r: Risorse, comune: str) -> None:
        noti = [c["nome"] for c in r.comuni()]
        if comune not in noti:
            raise HTTPException(status_code=404,
                                detail=f"comune sconosciuto: {comune}. Disponibili: {', '.join(noti)}")

    # ------------------------------------------------------------------ stato

    @app.get(f"{PREFISSO}/salute", response_model=Salute, tags=["stato"])
    def salute(r: Risorse = Depends(risorse_correnti)) -> Salute:
        """Dice quali servizi rispondono: utile prima di accusare il modello."""
        return Salute(**r.salute())

    @app.get(f"{PREFISSO}/comuni", response_model=list[Comune], tags=["stato"])
    def comuni(r: Risorse = Depends(risorse_correnti)) -> list[Comune]:
        return [Comune(**c) for c in r.comuni()]

    # ------------------------------------------------------------------ agente

    @app.post(f"{PREFISSO}/analizza", response_model=RispostaUscita, tags=["agente"])
    async def analizza(comune: str = Form(...), foto: UploadFile = File(...),
                       testo: str | None = Form(default=None),
                       r: Risorse = Depends(risorse_correnti)) -> RispostaUscita:
        """Dalla foto alla risposta. Il testo è facoltativo e aiuta nei casi dubbi."""
        controlla_comune(r, comune)
        immagine = await foto.read()
        if not immagine:
            raise HTTPException(status_code=400, detail="la foto è vuota")
        return RispostaUscita.da(r.agente.analizza(immagine, comune, testo))

    @app.post(f"{PREFISSO}/continua", response_model=RispostaUscita, tags=["agente"])
    def continua(dati: Continuazione, r: Risorse = Depends(risorse_correnti)) -> RispostaUscita:
        """Risposta a un chiarimento: riparte dal riconoscimento già fatto, senza rileggere
        la foto, che sarebbe il passaggio più lento."""
        if "riconoscimento" not in dati.contesto or "comune" not in dati.contesto:
            raise HTTPException(status_code=400,
                                detail="contesto non valido: rimanda quello ricevuto da /analizza")
        return RispostaUscita.da(r.agente.continua(dati.contesto, dati.risposta))

    # ------------------------------------------------------------------ ricerca

    @app.post(f"{PREFISSO}/cerca", response_model=list[CandidatoUscita], tags=["ricerca"])
    def cerca(dati: Ricerca, r: Risorse = Depends(risorse_correnti)) -> list[CandidatoUscita]:
        """Solo testo, senza modello di visione: serve alla valutazione del recupero e a
        capire cosa l'agente ha visto prima di scegliere."""
        controlla_comune(r, dati.comune)
        trovati = []
        for livello in ([dati.livello] if dati.livello else [1, 2]):
            trovati.extend(recupera(r.qdrant, r.vettorizzatore, [dati.domanda],
                                    dati.comune, livello=livello, k=dati.k))
        return [CandidatoUscita.da(c) for c in trovati]

    # ------------------------------------------------------------------ riscontro

    @app.post(f"{PREFISSO}/riscontro", status_code=201, tags=["riscontro"])
    def riscontro(dati: Riscontro, r: Risorse = Depends(risorse_correnti)) -> dict:
        """Registra il giudizio dell'utente su una risposta.

        Ogni riga è un esempio etichettato da una persona: è il modo meno costoso di
        costruire il set di valutazione, che oggi non esiste.
        """
        controlla_comune(r, dati.comune)
        riga = {**dati.model_dump(), "quando": datetime.now(timezone.utc).isoformat()}
        riscontri.parent.mkdir(parents=True, exist_ok=True)
        with open(riscontri, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(riga, ensure_ascii=False) + "\n")
        return {"registrato": True}

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
