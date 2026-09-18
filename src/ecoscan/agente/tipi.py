"""Tipi che attraversano l'agente, dalla foto alla risposta.

Sono dataclass semplici e non dipendono né da FastAPI né da Ollama: la valutazione e i test
usano l'agente direttamente, senza alzare un server.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Riconoscimento:
    """Cosa il modello di visione dice di vedere. Non contiene destinazioni: non le conosce."""

    oggetto: str
    sinonimi: list[str] = field(default_factory=list)
    categoria: str | None = None
    materiali: list[str] = field(default_factory=list)
    stato: str | None = None
    componenti: list[str] = field(default_factory=list)
    confidenza: float = 0.0
    note: str | None = None

    MATERIALI_NELLA_QUERY = 2

    @property
    def query(self) -> str:
        """Formulazione estesa: oggetto, materiali e stato insieme.

        I materiali si fermano a due. Il modello di visione ne elenca volentieri quattro
        ("acciaio inossidabile, vetro, plastica, metallo" per un microonde) e una domanda
        così lunga parla più di *di cosa è fatto* che di *cos'è*: l'oggetto diventa una
        parola su cinque e la ricerca si sposta sui materiali. Due bastano a dare il
        contesto senza annegarlo.
        """
        materiali = self.materiali[:self.MATERIALI_NELLA_QUERY]
        return " ".join(filter(None, [self.oggetto, *materiali, self.stato])).strip()

    @property
    def query_oggetto(self) -> str:
        """Solo l'oggetto e il suo stato.

        Serve perché i materiali, messi nella stessa domanda, trascinano la ricerca verso
        ciò che è *fatto di* quel materiale: cercando "sandalo gomma plastica tessuto" si
        ottengono gomme da masticare e righelli di plastica, e il sandalo sparisce.
        """
        return " ".join(filter(None, [self.oggetto, self.stato])).strip()

    def formulazioni(self, massimo: int = 7) -> list[str]:
        """Le domande da porre all'indice.

        Sono divise in due gruppi, e la divisione è il punto: le **essenziali** entrano
        sempre, le **aggiuntive** riempiono i posti che restano. Un elenco unico ordinato
        per specificità sembrava ragionevole e si è rotto due volte allo stesso modo — una
        domanda che serviva stava in fondo e il tetto la tagliava proprio nei casi in cui
        serviva:

        - la **forchetta d'acciaio** (v0.37.0): la domanda con il materiale era in coda,
          e "Stoviglie in metallo" non veniva mai raggiunta da "forchetta" da sola;
        - il **microonde** (v0.40.2): la domanda con la sola categoria era in coda dopo i
          sinonimi, e "Elettrodomestici" non usciva mai.

        Le quattro essenziali coprono i quattro modi in cui il dizionario nomina le cose:
        per oggetto, per oggetto con contesto, per materiale, per categoria. I dizionari
        comunali contengono voci generiche ("Elettrodomestici", "Stoviglie in metallo") che
        solo la domanda astratta raggiunge: senza, restano invisibili alla ricerca.

        I sinonimi restano aggiuntivi ma abbondanti: sono il ponte fra il vocabolario del
        modello e quello della fonte — il modello dice "sandalo", ASIA scrive "Scarpe" — e
        senza di loro la ricerca su una parola sola restituisce parole che le somigliano
        soltanto nella forma ("Salse", "Sdraio", "Scaldabagno").
        """
        essenziali = [self.query_oggetto]
        if self.categoria:
            # "sandalo" da solo è ambiguo e recupera rumore ("Salse", "Sdraio"); "sandalo
            # calzatura" dà al modello di embedding il contesto che gli manca
            essenziali.append(f"{self.oggetto} {self.categoria}")
            # la categoria DA SOLA: è l'unica domanda che raggiunge le voci generiche del
            # dizionario, quelle che non nominano nessun oggetto in particolare
            essenziali.append(self.categoria)
        if self.materiali:
            # un materiale solo: nel dizionario le voci sono scritte "Stoviglie in metallo",
            # e "forchetta" da sola non le raggiunge
            essenziali.append(f"{self.oggetto} {self.materiali[0]}")

        aggiuntive = [*self.sinonimi]
        if self.materiali and self.query != self.query_oggetto:
            aggiuntive.append(self.query)

        scelte = [*self.pulisci(essenziali)]
        for domanda in self.pulisci(aggiuntive):
            if len(scelte) >= massimo:
                break
            if domanda.lower() not in {s.lower() for s in scelte}:
                scelte.append(domanda)
        return scelte

    @staticmethod
    def pulisci(domande: list[str]) -> list[str]:
        """Toglie vuoti e doppioni, conservando l'ordine."""
        viste, uniche = set(), []
        for d in domande:
            chiave = (d or "").strip().lower()
            if chiave and chiave not in viste:
                viste.add(chiave)
                uniche.append(d.strip())
        return uniche

    @property
    def riuscito(self) -> bool:
        return bool(self.oggetto.strip())


@dataclass
class Variante:
    """Un modo di essere dell'oggetto e dove va di conseguenza."""

    condizioni: list[str] = field(default_factory=list)
    destinazioni: list[str] = field(default_factory=list)
    avvertenza: str | None = None

    @property
    def condizione(self) -> str | None:
        return " e ".join(self.condizioni) if self.condizioni else None


@dataclass
class Candidato:
    """Un documento proposto dalla ricerca: un oggetto con le sue varianti, o una regola.

    Tutto ciò che serve a rispondere è qui, perché viene dal payload del documento: non si
    legge più nulla dal relazionale a tempo di risposta.
    """

    id: str
    livello: int                       # 1 oggetto di dizionario, 2 regola di categoria
    testo: str
    tipo: str = "oggetto"
    nome: str | None = None
    varianti: list[Variante] = field(default_factory=list)
    alias: list[str] = field(default_factory=list)
    codice_materiale: str | None = None
    polarita: str | None = None        # solo per le regole
    destinazione: str | None = None
    fonte: str | None = None
    riferimento: str | None = None
    contraddizione: bool = False
    punteggio: float = 0.0
    per_codice: str | None = None      # trovato agganciando un codice materiale

    @classmethod
    def da_payload(cls, payload: dict) -> Candidato:
        varianti = [Variante(condizioni=v.get("condizioni") or [],
                             destinazioni=v.get("destinazioni") or [],
                             avvertenza=v.get("avvertenza"))
                    for v in payload.get("varianti") or []]
        return cls(
            id=payload["id"], livello=payload.get("livello") or 1, testo=payload["testo"],
            tipo=payload.get("tipo", "oggetto"), nome=payload.get("nome"), varianti=varianti,
            alias=payload.get("alias") or [], codice_materiale=payload.get("codice_materiale"),
            polarita=payload.get("polarita"), destinazione=payload.get("destinazione"),
            fonte=payload.get("fonte"), riferimento=payload.get("riferimento"),
            contraddizione=bool(payload.get("contraddizione")),
            punteggio=payload.get("punteggio", 0.0), per_codice=payload.get("per_codice"))

    @property
    def destinazioni(self) -> list[str]:
        """Tutte le destinazioni possibili, senza scegliere fra le varianti."""
        viste: list[str] = []
        for v in self.varianti:
            viste.extend(d for d in v.destinazioni if d not in viste)
        return viste

    def descrizione(self) -> str:
        """Come il candidato viene presentato al modello: il testo del documento, che è già
        scritto per essere letto."""
        return self.testo


# Tipi di corrispondenza che NON valgono come risposta. La regola è applicata dall'agente,
# non dall'adattatore di un singolo modello: vale per qualunque modello, anche futuro.
TIPI_NON_VALIDI = frozenset({"solo_materiale", "nessuna"})


@dataclass
class Scelta:
    """L'esito della scelta vincolata: un candidato reale, oppure nessuno."""

    scheda_id: str | None          # id del documento scelto
    tipo_corrispondenza: str = ""   # stesso_oggetto | sinonimo | categoria | solo_materiale | nessuna
    motivo: str = ""
    chiarimento: str | None = None

    @property
    def valida(self) -> bool:
        return self.scheda_id is not None and self.tipo_corrispondenza not in TIPI_NON_VALIDI


@dataclass
class Risposta:
    """Ciò che l'agente restituisce. `livello_evidenza` dice quanto è fondata."""

    livello_evidenza: int              # 1, 2 oppure 3 (nessuna regola del comune)
    comune: str
    oggetto: str | None = None
    destinazioni: list[str] = field(default_factory=list)
    polarita: str | None = None
    condizioni: list[str] = field(default_factory=list)
    avvertenza: str | None = None
    fonte: str | None = None
    riferimento: str | None = None
    chiarimento: str | None = None     # domanda da fare prima di considerarla definitiva
    opzioni: list[str] = field(default_factory=list)  # risposte possibili alla domanda
    scelto_id: str | None = None       # il documento da cui viene la risposta, fra i candidati
    tipo_corrispondenza: str = ""
    motivo: str = ""
    contraddizione: bool = False
    candidati: list[Candidato] = field(default_factory=list)
    riconoscimento: Riconoscimento | None = None
    contesto: dict = field(default_factory=dict)   # il backend resta senza stato: lo rimanda il client

    @property
    def definitiva(self) -> bool:
        return self.livello_evidenza in (1, 2) and not self.chiarimento
