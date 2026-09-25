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
from ecoscan import materiali as materiali_
from ecoscan import prompt as prompt_
from ecoscan.agente.modelli import ModelloVisione
from ecoscan.agente.recupero import (
    Recupero, nomina_l_oggetto, scegli_variante, stessa_cosa,
)
from ecoscan.agente.tipi import (
    STESSO_OGGETTO, TIPI_NON_VALIDI, Candidato, Riconoscimento, Risposta, Scelta,
)
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
            "arricchimento": "si" if conf.ARRICCHIMENTO else "no",
            "keep_alive": conf.OLLAMA_KEEP_ALIVE,
            **{f"prompt_{n}": prompt_.carica(n).etichetta for n in ("riconoscimento", "scelta")},
        }

    # ------------------------------------------------------------------ passaggi

    @staticmethod
    def _senza_materiali_estranei(trovati: list[Candidato],
                                  richiesta: Richiesta) -> tuple[list[Candidato], list[str]]:
        """Toglie i documenti che dichiarano un materiale diverso da quello dell'oggetto.

        Davanti a una forchetta d'acciaio il modello ha scelto "Forchetta in plastica", pur
        avendo riconosciuto l'acciaio: il nome somigliava, e nessuno gli impediva di
        ignorare il materiale. Togliere quei documenti prima della scelta è più sicuro che
        sperare che il prompt basti, e vale per qualunque modello.

        Se lo scarto svuoterebbe l'elenco non si scarta nulla: un riconoscimento sbagliato
        sul materiale renderebbe muto il sistema, e una risposta imperfetta è più utile di
        nessuna risposta.
        """
        materiali = richiesta.riconoscimento.materiali
        # si guarda il NOME del documento, non tutto il testo: il testo dice anche dove va
        # ("Va in Plastica e Metalli"), e quello è il contenitore, non il materiale
        # dell'oggetto. Le regole di categoria non hanno un nome: lì vale il testo.
        tenuti = [c for c in trovati
                  if not materiali_.incompatibili(c.nome or c.testo, materiali)]
        if not tenuti or len(tenuti) == len(trovati):
            return trovati, []
        scartati = [c.nome or c.id for c in trovati if c not in tenuti]
        return tenuti, scartati

    def recupera(self, richiesta: Richiesta, livello: int) -> list[Candidato]:
        """La ricerca a un livello di evidenza, tracciata come span RETRIEVER.

        È pubblico perché la valutazione lo chiama per misurare il tetto senza eseguire la
        scelta: un metodo privato usato da fuori è una dipendenza che nessuno dichiara, e
        al primo refactoring si rompe in silenzio.
        """
        poste = richiesta.domande
        with self.tracciatore.span(f"recupero_livello{livello}", RETRIEVER,
                                   {"domande": poste, "comune": richiesta.comune,
                                    "livello": livello, "k": self.k}) as span:
            trovati = self.recupero.candidati(poste, richiesta.comune, livello=livello,
                                              k=self.k)
            trovati, scartati = self._senza_materiali_estranei(trovati, richiesta)
            span.uscita([documento(c) for c in trovati])
            if scartati:
                span.attributi(scartati_per_materiale=scartati)
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
        trovati = self.recupera(richiesta, livello)
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
    def _corrispondenza_verificata(scelto: Candidato, dichiarato: str,
                                   richiesta: Richiesta) -> str:
        """Che tipo di corrispondenza è, secondo il codice e non secondo il modello.

        Il modello dichiara il tipo (D83) ma lo sbaglia in entrambe le direzioni, e da
        quando la presentazione lo mostra all'utente (D163) un'etichetta sbagliata è una
        frase falsa:

        - per un **divano** a Napoli il documento scelto era proprio "Divano", e il modello
          ha dichiarato "categoria" motivandolo con "il divano rientra nella categoria
          mobile". Il messaggio diceva "il comune non elenca proprio questo oggetto" mentre
          il comune lo elencava, con tanto di pagina dedicata nella fonte citata;
        - per un **microonde** il documento era un fratello e il tipo dichiarato era ancora
          "categoria", stavolta troppo generoso.

        Il primo caso il codice lo può decidere da solo: se il nome del documento nomina
        l'oggetto, è quell'oggetto, comunque il modello abbia voluto chiamare la relazione.
        Il secondo no — stabilire se una voce *contiene* l'oggetto richiede il senso delle
        parole — e resta affidato al prompt.

        È lo stesso principio di D83, applicato all'etichetta invece che alla scelta: ciò
        che il codice può verificare, il codice lo verifica.
        """
        if dichiarato == STESSO_OGGETTO:
            return dichiarato
        nomina = nomina_l_oggetto(scelto, richiesta.riconoscimento, richiesta.testo_utente)
        return STESSO_OGGETTO if nomina else dichiarato

    @staticmethod
    def _materiali_da_chiarire(scelto: Candidato, candidati: list[Candidato],
                               richiesta: Richiesta) -> list[str]:
        """I materiali che distinguono documenti omonimi, quando non sappiamo quale sia.

        È il difetto che restava scoperto: il chiarimento nasceva solo dalle **condizioni**
        di una voce (D73), quindi "bicchiere" — che a Napoli può essere di vetro (Non
        Riciclabile) o di plastica (Plastica e Metalli) — non produceva nessuna domanda. Il
        modello ne sceglieva uno e basta, e l'utente non aveva modo di sapere che la
        risposta dipendeva da un'informazione che non aveva dato.

        Si chiede solo quando la domanda **cambierebbe la risposta**: due materiali almeno,
        che portano in contenitori diversi, fra documenti che nominano davvero l'oggetto. Se
        il riconoscimento il materiale l'ha già dichiarato, non c'è niente da chiedere: a
        quel punto tocca al filtro dei materiali togliere i documenti incompatibili.
        """
        if richiesta.riconoscimento.materiali:
            return []
        # la famiglia si ancora al documento **scelto**: senza, un candidato qualunque di un
        # altro materiale farebbe nascere una domanda che non c'entra con la risposta
        omonimi = [(c.nome or "", tuple(c.destinazioni)) for c in candidati
                   if c is scelto or stessa_cosa(c.nome or "", scelto.nome or "")]
        return materiali_.distinzione(omonimi)

    @staticmethod
    def _chiarimento(da_chiarire: list[str], materiali: list[str], scelta: Scelta,
                     gia_chiesto: bool) -> tuple[str | None, list[str]]:
        """La domanda da fare e le risposte possibili.

        Le condizioni diventano i pulsanti dell'interfaccia, e la domanda cambia con la loro
        natura: "com'è" per lo stato, "quanto ne hai" per le quantità, "chi lo conferisce"
        per le utenze, "di che materiale è" per le voci omonime. Dopo una domanda già fatta
        non se ne fa un'altra: l'utente ha risposto, e ripetergliela lo lascerebbe in un giro
        senza uscita.

        L'ordine è una precedenza: la condizione della voce scelta è più specifica del
        materiale, perché riguarda proprio quel documento; il chiarimento suggerito dal
        modello viene per ultimo, perché è l'unico che non nasce dai dati.
        """
        if gia_chiesto:
            return None, []
        if da_chiarire:
            return condizioni_.domanda(da_chiarire), list(da_chiarire)
        if materiali:
            return condizioni_.domanda(materiali, condizioni_.MATERIALE), list(materiali)
        return scelta.chiarimento, []

    def _componi(self, scelto: Candidato, scelta: Scelta, candidati: list[Candidato],
                 richiesta: Richiesta) -> Risposta:
        """Dal documento scelto alla risposta: variante, chiarimento e provenienza."""
        scelto, nota = self._piu_specifico(scelto, candidati, richiesta)
        motivo = " · ".join(p for p in (scelta.motivo, nota) if p)

        variante, da_chiarire = scegli_variante(
            scelto, [richiesta.testo_utente, richiesta.riconoscimento.stato])
        materiali = self._materiali_da_chiarire(scelto, candidati, richiesta)
        chiarimento, opzioni = self._chiarimento(da_chiarire, materiali, scelta,
                                                 richiesta.gia_chiesto)

        return Risposta(
            livello_evidenza=scelto.livello, comune=richiesta.comune,
            oggetto=richiesta.riconoscimento.oggetto,
            destinazioni=variante.destinazioni if variante else scelto.destinazioni,
            polarita=scelto.polarita,
            condizioni=variante.condizioni if variante else [],
            avvertenza=variante.avvertenza if variante else None,
            fonte=scelto.fonte, riferimento=scelto.riferimento,
            chiarimento=chiarimento, opzioni=opzioni, scelto_id=scelto.id,
            tipo_corrispondenza=self._corrispondenza_verificata(
                scelto, scelta.tipo_corrispondenza, richiesta),
            motivo=motivo,
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

    @staticmethod
    def _con_la_risposta(riconoscimento: dict, risposta_utente: str) -> Riconoscimento:
        """Il riconoscimento aggiornato con ciò che l'utente ha appena detto.

        Dove finisce la risposta dipende da cosa è: una condizione va nello **stato**, un
        materiale nei **materiali**. Metterlo sempre nello stato era giusto finché si
        chiedevano solo le condizioni; da quando si chiede anche il materiale, lo stato
        "vetro" non servirebbe a niente — il filtro dei materiali guarda `materiali`, e le
        formulazioni cercano "oggetto + materiale" (D164). La domanda cambierebbe la
        risposta solo per caso.
        """
        campi = dict(riconoscimento)
        if materiali_.dichiarato(risposta_utente or ""):
            campi["materiali"] = [*(campi.get("materiali") or []), risposta_utente]
        else:
            campi["stato"] = risposta_utente or None
        return Riconoscimento(**campi)

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

    def domanda(self, comune: str, oggetto: str, testo: str | None = None) -> Risposta:
        """L'utente scrive il nome dell'oggetto invece di fotografarlo.

        Salta il modello di visione, che è il passaggio lento, e parte dall'oggetto detto
        dall'utente come se l'avesse riconosciuto lui: stessa cascata, stessa scelta, stesse
        tracce. Serve a chi sa già come si chiama la cosa, e a chi non ha la foto sottomano.

        La confidenza è massima per lo stesso motivo di `correggi`: qui non c'è un'ipotesi
        di un modello da soppesare, c'è quello che l'utente ha scritto.
        """
        conversazione = nuova_conversazione()
        riconoscimento = Riconoscimento(oggetto=oggetto.strip(), confidenza=1.0,
                                        note="scritto dall'utente")
        ingressi = {"comune": comune, "oggetto": oggetto, "testo_utente": testo}

        with self.tracciatore.turno("domanda", conversazione, ingressi) as radice:
            risposta = self.rispondi(riconoscimento, comune, testo, conversazione=conversazione)
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
        arricchito = self._con_la_risposta(contesto["riconoscimento"], risposta_utente)
        ingressi = {"comune": contesto["comune"], "risposta_utente": risposta_utente,
                    "testo_utente": testo, "riconoscimento": contesto["riconoscimento"]}

        with self.tracciatore.turno("continua", conversazione, ingressi) as radice:
            risposta = self.rispondi(arricchito, contesto["comune"], testo, gia_chiesto=True,
                                     conversazione=conversazione)
            self.tracciatore.chiudi_turno(radice, risposta)
        return risposta
