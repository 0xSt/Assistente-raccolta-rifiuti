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

Il tracciamento passa per un oggetto sostituibile (`tracciatore`): ogni turno è una traccia,
ogni recupero uno span RETRIEVER, ogni chiamata al modello uno span LLM. Senza tracciatore
l'agente funziona uguale e non importa MLflow.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import partial

from ecoscan import condizioni as condizioni_
from ecoscan import configurazione as conf
from ecoscan import prompt as prompt_
from ecoscan.agente.modelli import ModelloVisione
from ecoscan.agente.recupero import Recupero, nomina_l_oggetto, scegli_variante
from ecoscan.agente.tipi import TIPI_NON_VALIDI, Candidato, Riconoscimento, Risposta, Scelta
from ecoscan.osservabilita.tracciamento import (
    LLM, RETRIEVER, TracciatoreNullo, documento, impronta, nuova_conversazione,
)

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


@dataclass(frozen=True)
class Richiesta:
    """Cosa si sta cercando, in un oggetto solo.

    Riconoscimento, comune, parole dell'utente e "ho già chiesto" viaggiano insieme in ogni
    passaggio: passarli uno per uno faceva firme da sei e sette parametri, in cui l'ordine
    contava più del significato.
    """

    riconoscimento: Riconoscimento
    comune: str
    testo_utente: str | None = None
    gia_chiesto: bool = False

    @property
    def domande(self) -> list[str]:
        return domande(self.riconoscimento, self.testo_utente)

    @property
    def affidabile(self) -> bool:
        """Sotto la soglia non si cerca: cercare a partire da un riconoscimento incerto
        produce risposte sicure di sé e sbagliate."""
        return (self.riconoscimento.riuscito
                and self.riconoscimento.confidenza >= CONFIDENZA_MINIMA)


class Agente:
    def __init__(self, recupero: Recupero, modello: ModelloVisione, k: int = 8,
                 tracciatore=None):
        self.recupero, self.modello, self.k = recupero, modello, k
        self.tracciatore = tracciatore or TracciatoreNullo()
        self.tracciatore.configura(self.configurazione())

    def configurazione(self) -> dict[str, str]:
        """I parametri che, se cambiano, cambiano il comportamento dell'agente. Formano la
        versione dell'applicazione a cui ogni traccia viene collegata."""
        return {
            "modello_visione": self.modello.nome,
            "recupero": self.recupero.nome,
            "k": str(self.k),
            "confidenza_minima": str(CONFIDENZA_MINIMA),
            "lato_max_immagine": str(getattr(self.modello, "lato_max", conf.LATO_MAX_IMMAGINE)),
            "prefissi_embedding": "si" if conf.PREFISSI_EMBEDDING else "no",
            "keep_alive": conf.OLLAMA_KEEP_ALIVE,
            **{f"prompt_{n}": prompt_.carica(n).etichetta for n in ("riconoscimento", "scelta")},
        }

    # ------------------------------------------------------------------ passaggi

    def _recupera(self, richiesta: Richiesta, livello: int) -> list[Candidato]:
        """La ricerca semantica a un livello di evidenza, tracciata come span RETRIEVER."""
        poste = richiesta.domande
        with self.tracciatore.span(f"recupero_livello{livello}", RETRIEVER,
                                   {"domande": poste, "comune": richiesta.comune,
                                    "livello": livello, "k": self.k}) as span:
            trovati = self.recupero.candidati(poste, richiesta.comune, livello=livello,
                                              k=self.k)
            span.uscita([documento(c) for c in trovati])
        return trovati

    def _scegli(self, richiesta: Richiesta, trovati: list[Candidato], livello: int) -> Scelta:
        """La scelta vincolata del modello fra i documenti trovati.

        Se il modello indica un documento ma dichiara che non corrisponde davvero
        (`solo_materiale`, `nessuna`), la politica lo scarta: vale per qualunque modello,
        quindi sta qui e non nel prompt.
        """
        with self.tracciatore.span(f"scelta_livello{livello}", LLM, {
                "prompt": prompt_.carica("scelta").etichetta, "modello": self.modello.nome,
                "riconoscimento": richiesta.riconoscimento,
                "testo_utente": richiesta.testo_utente,
                "candidati": [{"numero": i, "id": c.id, "testo": c.testo}
                              for i, c in enumerate(trovati, start=1)]}) as span:
            scelta = self.modello.scegli(richiesta.riconoscimento, trovati,
                                         richiesta.testo_utente)
            scartata = scelta.tipo_corrispondenza in TIPI_NON_VALIDI
            span.uscita({**asdict(scelta), "scartata_dall_agente": scartata})
        if not scartata:
            return scelta
        return Scelta(scheda_id=None, tipo_corrispondenza=scelta.tipo_corrispondenza,
                      motivo=scelta.motivo or f"scartata: {scelta.tipo_corrispondenza}")

    def _prova_livello(self, richiesta: Richiesta,
                       livello: int) -> tuple[list[Candidato], Scelta]:
        trovati = self._recupera(richiesta, livello)
        if not trovati:
            return [], Scelta(scheda_id=None, motivo=f"nessun candidato al livello {livello}")
        return trovati, self._scegli(richiesta, trovati, livello)

    @staticmethod
    def _piu_specifico(scelto: Candidato, candidati: list[Candidato],
                       richiesta: Richiesta) -> tuple[Candidato, str]:
        """Il documento che nomina proprio l'oggetto batte quello generico.

        Il modello preferisce il generico: davanti a un cartone della pizza ha scelto
        "Cartone da imballaggio" mentre "Cartone per pizze" era il primo risultato.
        Restituisce il documento e la nota da aggiungere al motivo.
        """
        nomina = partial(nomina_l_oggetto, riconoscimento=richiesta.riconoscimento,
                         testo_utente=richiesta.testo_utente)
        if nomina(scelto):
            return scelto, ""
        specifici = [c for c in candidati if nomina(c)]
        return (specifici[0], "scelto il documento che nomina l'oggetto") if specifici else (scelto, "")

    @staticmethod
    def _chiarimento(da_chiarire: list[str], scelta: Scelta,
                     gia_chiesto: bool) -> tuple[str | None, list[str]]:
        """La domanda da fare e le risposte possibili.

        Le condizioni diventano i pulsanti dell'interfaccia, e la domanda cambia con la loro
        natura: "com'è" per lo stato, "quanto ne hai" per le quantità, "chi lo conferisce"
        per le utenze. Dopo una domanda già fatta non se ne fa un'altra: l'utente ha
        risposto, e ripetergliela lo lascerebbe in un giro senza uscita.
        """
        if gia_chiesto:
            return None, []
        if da_chiarire:
            return condizioni_.domanda(da_chiarire), list(da_chiarire)
        return scelta.chiarimento, []

    def _componi(self, scelto: Candidato, scelta: Scelta, candidati: list[Candidato],
                 richiesta: Richiesta) -> Risposta:
        """Dal documento scelto alla risposta: variante, chiarimento e provenienza."""
        scelto, nota = self._piu_specifico(scelto, candidati, richiesta)
        motivo = " · ".join(p for p in (scelta.motivo, nota) if p)

        variante, da_chiarire = scegli_variante(
            scelto, [richiesta.testo_utente, richiesta.riconoscimento.stato])
        chiarimento, opzioni = self._chiarimento(da_chiarire, scelta, richiesta.gia_chiesto)

        return Risposta(
            livello_evidenza=scelto.livello, comune=richiesta.comune,
            oggetto=richiesta.riconoscimento.oggetto,
            destinazioni=variante.destinazioni if variante else scelto.destinazioni,
            polarita=scelto.polarita,
            condizioni=variante.condizioni if variante else [],
            avvertenza=variante.avvertenza if variante else None,
            fonte=scelto.fonte, riferimento=scelto.riferimento,
            chiarimento=chiarimento, opzioni=opzioni, scelto_id=scelto.id,
            tipo_corrispondenza=scelta.tipo_corrispondenza, motivo=motivo,
            candidati=candidati, riconoscimento=richiesta.riconoscimento,
            contraddizione=scelto.contraddizione,
        )

    # ------------------------------------------------------------------ ingresso

    def analizza(self, immagine: bytes, comune: str, testo_utente: str | None = None,
                 contesto: dict | None = None) -> Risposta:
        """Primo turno di una conversazione: dalla foto alla risposta."""
        conversazione = (contesto or {}).get("id_conversazione") or nuova_conversazione()
        foto = self.tracciatore.allegato(immagine)
        ingressi = {"comune": comune, "testo_utente": testo_utente, "foto": foto,
                    "impronta_foto": impronta(immagine)}

        with self.tracciatore.turno("analizza", conversazione, ingressi) as radice:
            with self.tracciatore.span("riconoscimento", LLM, {
                    "prompt": prompt_.carica("riconoscimento").etichetta,
                    "modello": self.modello.nome, "foto": foto,
                    "testo_utente": testo_utente}) as span:
                riconoscimento = self.modello.riconosci(immagine, testo_utente)
                span.uscita(riconoscimento)
            risposta = self.rispondi(riconoscimento, comune, testo_utente, contesto,
                                     conversazione=conversazione)
            self.tracciatore.chiudi_turno(radice, risposta)
        return risposta

    def rispondi(self, riconoscimento: Riconoscimento, comune: str,
                 testo_utente: str | None = None, contesto: dict | None = None,
                 gia_chiesto: bool = False, conversazione: str | None = None) -> Risposta:
        """Dal riconoscimento alla risposta. Separato da `analizza` per poter valutare
        recupero e scelta senza rieseguire il modello di visione su ogni foto.

        Chiamato da solo non apre una traccia: gli span si registrano solo dentro un turno.
        """
        conversazione = conversazione or (contesto or {}).get("id_conversazione")
        richiesta = Richiesta(riconoscimento, comune, testo_utente, gia_chiesto)
        base = {"comune": comune, "riconoscimento": riconoscimento,
                "contesto": self._contesto(riconoscimento, comune, testo_utente, conversazione)}

        if not richiesta.affidabile:
            return Risposta(livello_evidenza=3, oggetto=riconoscimento.oggetto or None,
                            motivo="oggetto non riconosciuto con sufficiente sicurezza",
                            chiarimento="Puoi rifare la foto più da vicino, o dirmi di che "
                                        "oggetto si tratta?",
                            **base)

        risposta, tutti = self._cascata(richiesta)
        if risposta is None:
            return Risposta(livello_evidenza=3, oggetto=riconoscimento.oggetto,
                            motivo=f"nessuna regola di {comune} copre questo oggetto",
                            candidati=tutti, **base)
        risposta.candidati = tutti
        risposta.contesto = base["contesto"]
        return risposta

    def _cascata(self, richiesta: Richiesta) -> tuple[Risposta | None, list[Candidato]]:
        """Prima il dizionario degli oggetti, poi le regole di categoria.

        L'ordine è la garanzia del livello di evidenza: una voce che nomina l'oggetto vale
        più di una regola generale, e si scende al livello 2 solo se il livello 1 tace.
        """
        tutti: list[Candidato] = []
        for livello in (1, 2):
            trovati, scelta = self._prova_livello(richiesta, livello)
            tutti.extend(trovati)
            if scelta.scheda_id is not None:
                scelto = next(c for c in trovati if c.id == scelta.scheda_id)
                return self._componi(scelto, scelta, trovati, richiesta), tutti
        return None, tutti

    def _contesto(self, riconoscimento: Riconoscimento, comune: str,
                  testo_utente: str | None, conversazione: str | None = None) -> dict:
        """Il backend resta senza stato: il contesto torna al client, che lo rimanda.
        Porta anche l'identificativo della conversazione, che raggruppa i turni nelle tracce."""
        return {"riconoscimento": asdict(riconoscimento), "comune": comune,
                "testo_utente": testo_utente,
                "prompt": [prompt_.carica(n).etichetta for n in ("riconoscimento", "scelta")],
                "modello_visione": self.modello.nome,
                "id_conversazione": conversazione}

    def correggi(self, contesto: dict, oggetto: str) -> Risposta:
        """L'utente dice che l'oggetto riconosciuto è sbagliato: si riparte dal suo.

        Non si rilegge la foto, che è il passaggio lento, e soprattutto non la si fa
        riguardare a un modello che ha già sbagliato: la parola dell'utente vale più di
        quella del modello di visione, quindi la confidenza è massima.
        """
        conversazione = contesto.get("id_conversazione") or nuova_conversazione()
        precedente = contesto.get("riconoscimento") or {}
        corretto = Riconoscimento(oggetto=oggetto.strip(), confidenza=1.0,
                                  stato=precedente.get("stato"),
                                  note="corretto dall'utente")
        ingressi = {"comune": contesto["comune"], "oggetto_corretto": oggetto,
                    "riconoscimento_precedente": precedente}

        with self.tracciatore.turno("correggi", conversazione, ingressi) as radice:
            risposta = self.rispondi(corretto, contesto["comune"], contesto.get("testo_utente"),
                                     conversazione=conversazione)
            self.tracciatore.chiudi_turno(radice, risposta)
        return risposta

    def continua(self, contesto: dict, risposta_utente: str) -> Risposta:
        """Secondo giro dopo un chiarimento: si riparte dal riconoscimento già fatto.

        `gia_chiesto` impedisce di riproporre la stessa domanda: l'utente ha risposto, e
        ripetergliela lo lascerebbe in un giro senza uscita.
        """
        # un contesto di un client precedente a questa versione non ha l'identificativo:
        # il turno diventa l'inizio di una conversazione nuova, invece di fallire
        conversazione = contesto.get("id_conversazione") or nuova_conversazione()
        testo = " ".join(filter(None, [contesto.get("testo_utente"), risposta_utente]))
        arricchito = Riconoscimento(**{**contesto["riconoscimento"],
                                       "stato": risposta_utente or None})
        ingressi = {"comune": contesto["comune"], "risposta_utente": risposta_utente,
                    "testo_utente": testo, "riconoscimento": contesto["riconoscimento"]}

        with self.tracciatore.turno("continua", conversazione, ingressi) as radice:
            risposta = self.rispondi(arricchito, contesto["comune"], testo, gia_chiesto=True,
                                     conversazione=conversazione)
            self.tracciatore.chiudi_turno(radice, risposta)
        return risposta
