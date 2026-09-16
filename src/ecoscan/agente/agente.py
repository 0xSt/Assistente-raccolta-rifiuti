"""L'agente: dalla foto alla risposta.

Quattro passaggi:

1. **riconoscimento** — il modello guarda la foto e descrive l'oggetto (non sa dove va);
2. **recupero** — ricerca semantica nel comune, prima fra gli oggetti (livello 1), poi fra
   le regole di categoria (livello 2);
3. **scelta vincolata** — il modello sceglie fra documenti reali, oppure dice "nessuno";
4. **variante e risposta** — se l'oggetto ha più varianti, quella giusta la determina la
   condizione dichiarata dall'utente; se non è dichiarata, si chiede.

La divisione dei compiti è il punto: il modello riconosce e sceglie l'**oggetto**, il codice
decide la **variante**, perché è lì che si gioca la differenza fra organico e carta.
"""
from __future__ import annotations

from dataclasses import asdict

from ecoscan import prompt as prompt_
from ecoscan.agente.modelli import ModelloVisione
from ecoscan.agente.recupero import candidati as recupera
from ecoscan.agente.recupero import nomina_l_oggetto, scegli_variante
from ecoscan.agente.tipi import TIPI_NON_VALIDI, Candidato, Riconoscimento, Risposta, Scelta

CONFIDENZA_MINIMA = 0.2   # sotto, il riconoscimento non è affidabile abbastanza per cercare


def domande(riconoscimento: Riconoscimento, testo_utente: str | None = None) -> list[str]:
    """Le domande da porre all'indice.

    Le parole dell'utente sono una prova, non un contorno: chi scrive "cartone della pizza
    unto" ha appena detto cosa cercare.
    """
    poste = list(riconoscimento.formulazioni())
    testo = (testo_utente or "").strip()
    if testo:
        for formulazione in (testo, f"{riconoscimento.oggetto} {testo}".strip()):
            if formulazione and formulazione.lower() not in {d.lower() for d in poste}:
                poste.append(formulazione)
    return poste


class Agente:
    def __init__(self, qdrant, vettorizzatore, modello: ModelloVisione, k: int = 8):
        self.qdrant, self.vettorizzatore, self.modello, self.k = qdrant, vettorizzatore, modello, k

    # ------------------------------------------------------------------ passaggi

    def _scegli_nel_livello(self, riconoscimento: Riconoscimento, comune: str, livello: int,
                            testo_utente: str | None) -> tuple[list[Candidato], Scelta]:
        trovati = recupera(self.qdrant, self.vettorizzatore,
                           domande(riconoscimento, testo_utente), comune, livello=livello, k=self.k)
        if not trovati:
            return [], Scelta(scheda_id=None, motivo=f"nessun candidato al livello {livello}")
        scelta = self.modello.scegli(riconoscimento, trovati, testo_utente)
        if scelta.tipo_corrispondenza in TIPI_NON_VALIDI:
            # il modello ha indicato un documento ma ha dichiarato che non corrisponde:
            # la politica lo scarta, qualunque modello l'abbia prodotta
            return trovati, Scelta(scheda_id=None, tipo_corrispondenza=scelta.tipo_corrispondenza,
                                   motivo=scelta.motivo or f"scartata: {scelta.tipo_corrispondenza}")
        return trovati, scelta

    def _componi(self, scelto: Candidato, riconoscimento: Riconoscimento, scelta: Scelta,
                 comune: str, candidati: list[Candidato], testo_utente: str | None,
                 gia_chiesto: bool) -> Risposta:
        noti = [testo_utente, riconoscimento.stato]
        motivo = scelta.motivo

        # Il modello preferisce il documento generico a quello specifico: davanti a un
        # cartone della pizza ha scelto "Cartone da imballaggio" mentre "Cartone per pizze"
        # era il primo risultato. Se un documento nomina proprio l'oggetto, vince.
        if not nomina_l_oggetto(scelto, riconoscimento, testo_utente):
            specifici = [c for c in candidati if nomina_l_oggetto(c, riconoscimento, testo_utente)]
            if specifici:
                scelto = specifici[0]
                motivo = f"{motivo} · scelto il documento che nomina l'oggetto".strip(" ·")
        variante, da_chiarire = scegli_variante(scelto, noti)

        chiarimento = None
        if da_chiarire and not gia_chiesto:
            chiarimento = ("Per rispondere con certezza devo sapere se l'oggetto è: "
                           + " oppure ".join(da_chiarire) + "?")
        elif not gia_chiesto:
            chiarimento = scelta.chiarimento

        destinazioni = variante.destinazioni if variante else scelto.destinazioni
        condizioni = variante.condizioni if variante else []
        avvertenza = (variante.avvertenza if variante else None)

        return Risposta(
            livello_evidenza=scelto.livello, comune=comune, oggetto=riconoscimento.oggetto,
            destinazioni=destinazioni, polarita=scelto.polarita, condizioni=condizioni,
            avvertenza=avvertenza, fonte=scelto.fonte, riferimento=scelto.riferimento,
            chiarimento=chiarimento, tipo_corrispondenza=scelta.tipo_corrispondenza,
            motivo=motivo, candidati=candidati, riconoscimento=riconoscimento,
            contraddizione=scelto.contraddizione,
        )

    # ------------------------------------------------------------------ ingresso

    def analizza(self, immagine: bytes, comune: str, testo_utente: str | None = None,
                 contesto: dict | None = None) -> Risposta:
        riconoscimento = self.modello.riconosci(immagine, testo_utente)
        return self.rispondi(riconoscimento, comune, testo_utente, contesto)

    def rispondi(self, riconoscimento: Riconoscimento, comune: str,
                 testo_utente: str | None = None, contesto: dict | None = None,
                 gia_chiesto: bool = False) -> Risposta:
        """Dal riconoscimento alla risposta. Separato da `analizza` per poter valutare
        recupero e scelta senza rieseguire il modello di visione su ogni foto."""
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
                scelto = next(c for c in trovati if c.id == scelta.scheda_id)
                risposta = self._componi(scelto, riconoscimento, scelta, comune, trovati,
                                         testo_utente, gia_chiesto)
                risposta.candidati = tutti
                risposta.contesto = base["contesto"]
                return risposta

        return Risposta(livello_evidenza=3, oggetto=riconoscimento.oggetto,
                        motivo=f"nessuna regola di {comune} copre questo oggetto",
                        candidati=tutti, **base)

    def _contesto(self, riconoscimento: Riconoscimento, comune: str,
                  testo_utente: str | None) -> dict:
        """Il backend resta senza stato: il contesto torna al client, che lo rimanda."""
        return {"riconoscimento": asdict(riconoscimento), "comune": comune,
                "testo_utente": testo_utente,
                "prompt": [prompt_.carica(n).etichetta for n in ("riconoscimento", "scelta")],
                "modello_visione": self.modello.nome}

    def continua(self, contesto: dict, risposta_utente: str) -> Risposta:
        """Secondo giro dopo un chiarimento: si riparte dal riconoscimento già fatto.

        `gia_chiesto` impedisce di riproporre la stessa domanda: l'utente ha risposto, e
        ripetergliela lo lascerebbe in un giro senza uscita.
        """
        testo = " ".join(filter(None, [contesto.get("testo_utente"), risposta_utente]))
        arricchito = Riconoscimento(**{**contesto["riconoscimento"],
                                       "stato": risposta_utente or None})
        return self.rispondi(arricchito, contesto["comune"], testo, gia_chiesto=True)
