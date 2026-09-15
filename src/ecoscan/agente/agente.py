"""L'agente: dalla foto alla risposta.

Quattro passaggi, nell'ordine deciso in D6, D9 e D10:

1. **riconoscimento** — il modello guarda la foto e descrive l'oggetto (non sa dove va);
2. **recupero** — ricerca ibrida nel comune, prima fra le voci (livello 1), poi fra le
   regole di categoria (livello 2);
3. **scelta vincolata** — il modello sceglie fra candidati reali, oppure dice "nessuno";
4. **risposta** — la destinazione si legge da SQLite, mai dal modello.

Se nessun livello produce una scelta, la risposta è di livello 3: "il comune non dice nulla
su questo oggetto". Non si prendono in prestito le regole di un altro comune (D7).

L'agente non dipende da FastAPI: la valutazione e i test lo chiamano direttamente.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict

from ecoscan import prompt as prompt_
from ecoscan.agente.modelli import ModelloVisione
from ecoscan.agente.recupero import candidati as recupera
from ecoscan.agente.recupero import condizioni_in_gioco
from ecoscan.agente.tipi import TIPI_NON_VALIDI, Candidato, Riconoscimento, Risposta, Scelta

CONFIDENZA_MINIMA = 0.2   # sotto, il riconoscimento non è affidabile abbastanza per cercare


class Agente:
    def __init__(self, db: sqlite3.Connection, qdrant, vettorizzatore, modello: ModelloVisione,
                 k: int = 10):
        self.db, self.qdrant, self.vettorizzatore = db, qdrant, vettorizzatore
        self.modello, self.k = modello, k

    # ------------------------------------------------------------------ passaggi

    def _scegli_nel_livello(self, riconoscimento: Riconoscimento, comune: str, livello: int,
                            testo_utente: str | None) -> tuple[list[Candidato], Scelta]:
        trovati = recupera(self.db, self.qdrant, self.vettorizzatore,
                           riconoscimento.formulazioni(), comune, livello=livello, k=self.k)
        if not trovati:
            return [], Scelta(scheda_id=None, motivo=f"nessun candidato al livello {livello}")
        scelta = self.modello.scegli(riconoscimento, trovati, testo_utente)
        if scelta.tipo_corrispondenza in TIPI_NON_VALIDI:
            # il modello ha indicato una voce ma ha dichiarato che non corrisponde davvero:
            # la politica la scarta, qualunque modello l'abbia prodotta
            return trovati, Scelta(scheda_id=None, tipo_corrispondenza=scelta.tipo_corrispondenza,
                                   motivo=scelta.motivo or f"scartata: {scelta.tipo_corrispondenza}")
        return trovati, scelta

    def _componi(self, scelto: Candidato, riconoscimento: Riconoscimento, scelta: Scelta,
                 comune: str, candidati: list[Candidato]) -> Risposta:
        # se fra i candidati ci sono omonimi con destinazioni diverse, la condizione va chiesta
        chiarimento = scelta.chiarimento
        if not chiarimento and (condizioni := condizioni_in_gioco(candidati)):
            chiarimento = ("Per esserne certo devo sapere se l'oggetto è: "
                           + " oppure ".join(condizioni) + "?")
        return Risposta(
            livello_evidenza=scelto.livello, comune=comune, oggetto=riconoscimento.oggetto,
            destinazioni=scelto.destinazioni, polarita=scelto.polarita,
            condizioni=scelto.condizioni, avvertenza=scelto.avvertenza,
            fonte=scelto.fonte, riferimento=scelto.riferimento,
            chiarimento=chiarimento, motivo=scelta.motivo,
            tipo_corrispondenza=scelta.tipo_corrispondenza,
            candidati=candidati, riconoscimento=riconoscimento,
        )

    # ------------------------------------------------------------------ ingresso

    def analizza(self, immagine: bytes, comune: str, testo_utente: str | None = None,
                 contesto: dict | None = None) -> Risposta:
        riconoscimento = self.modello.riconosci(immagine, testo_utente)
        return self.rispondi(riconoscimento, comune, testo_utente, contesto)

    def rispondi(self, riconoscimento: Riconoscimento, comune: str,
                 testo_utente: str | None = None, contesto: dict | None = None) -> Risposta:
        """Dal riconoscimento alla risposta. Separato da `analizza` per poter valutare il
        retrieval e la scelta senza rieseguire il modello di visione su ogni foto."""
        base = {"comune": comune, "riconoscimento": riconoscimento,
                "contesto": self._contesto(riconoscimento, comune, testo_utente)}

        if not riconoscimento.riuscito or riconoscimento.confidenza < CONFIDENZA_MINIMA:
            return Risposta(livello_evidenza=3, oggetto=riconoscimento.oggetto or None,
                            motivo="oggetto non riconosciuto con sufficiente sicurezza",
                            chiarimento="Puoi rifare la foto più da vicino, o dirmi di che oggetto si tratta?",
                            **base)

        tutti: list[Candidato] = []
        for livello in (1, 2):
            trovati, scelta = self._scegli_nel_livello(riconoscimento, comune, livello, testo_utente)
            tutti.extend(trovati)
            if scelta.scheda_id is not None:
                scelto = next(c for c in trovati if c.scheda_id == scelta.scheda_id)
                risposta = self._componi(scelto, riconoscimento, scelta, comune, trovati)
                # si mostrano i candidati di TUTTI i livelli provati: se la scelta è caduta
                # sul livello 2, vedere cosa era stato scartato al livello 1 spiega il perché
                risposta.candidati = tutti
                risposta.contesto = base["contesto"]
                return risposta

        return Risposta(livello_evidenza=3, oggetto=riconoscimento.oggetto,
                        motivo=f"nessuna regola di {comune} copre questo oggetto",
                        chiarimento=None, candidati=tutti, **base)

    def _contesto(self, riconoscimento: Riconoscimento, comune: str,
                  testo_utente: str | None) -> dict:
        """Il backend resta senza stato: il contesto torna al client, che lo rimanda con la
        risposta al chiarimento."""
        return {"riconoscimento": asdict(riconoscimento), "comune": comune,
                "testo_utente": testo_utente,
                "prompt": [prompt_.carica(n).etichetta for n in ("riconoscimento", "scelta")],
                "modello_visione": self.modello.nome}

    def continua(self, contesto: dict, risposta_utente: str) -> Risposta:
        """Secondo giro dopo un chiarimento: si riparte dal riconoscimento già fatto,
        aggiungendo ciò che l'utente ha detto. Nessuna nuova lettura della foto."""
        riconoscimento = Riconoscimento(**contesto["riconoscimento"])
        testo = " ".join(filter(None, [contesto.get("testo_utente"), risposta_utente]))
        arricchito = Riconoscimento(**{**contesto["riconoscimento"],
                                       "stato": risposta_utente or riconoscimento.stato})
        return self.rispondi(arricchito, contesto["comune"], testo)
