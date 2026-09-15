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

    @property
    def query(self) -> str:
        """Formulazione estesa: oggetto, materiali e stato insieme."""
        return " ".join(filter(None, [self.oggetto, *self.materiali, self.stato])).strip()

    @property
    def query_oggetto(self) -> str:
        """Solo l'oggetto e il suo stato.

        Serve perché i materiali, messi nella stessa domanda, trascinano la ricerca verso
        ciò che è *fatto di* quel materiale: cercando "sandalo gomma plastica tessuto" si
        ottengono gomme da masticare e righelli di plastica, e il sandalo sparisce.
        """
        return " ".join(filter(None, [self.oggetto, self.stato])).strip()

    def formulazioni(self, massimo: int = 5) -> list[str]:
        """Le domande da porre all'indice, dalla più specifica alla più generica.

        I sinonimi sono il ponte fra il vocabolario del modello e quello della fonte: il
        modello dice "sandalo", il dizionario di ASIA scrive "Scarpe". Senza sinonimi la
        ricerca semantica su una parola sola restituisce parole che le somigliano soltanto
        nella forma ("Salse", "Sdraio", "Scaldabagno").
        """
        domande = [self.query_oggetto, *self.sinonimi]
        if self.categoria:
            domande.append(self.categoria)
        if self.materiali and self.query != self.query_oggetto:
            domande.append(self.query)
        viste, uniche = set(), []
        for d in domande:
            chiave = (d or "").strip().lower()
            if chiave and chiave not in viste:
                viste.add(chiave)
                uniche.append(d.strip())
        return uniche[:massimo]

    @property
    def riuscito(self) -> bool:
        return bool(self.oggetto.strip())


@dataclass
class Candidato:
    """Una scheda proposta dalla ricerca, arricchita con i dati del relazionale."""

    scheda_id: int
    livello: int                       # 1 voce di dizionario, 2 regola di categoria
    testo: str                         # ciò che è stato indicizzato
    nome: str | None = None            # nome della voce, se livello 1
    condizioni: list[str] = field(default_factory=list)
    destinazioni: list[str] = field(default_factory=list)
    polarita: str | None = None        # solo per le regole: ammesso | escluso
    avvertenza: str | None = None
    fonte: str | None = None
    riferimento: str | None = None
    posizioni: dict[str, int] = field(default_factory=dict)   # da quale metodo è stato trovato

    def descrizione(self) -> str:
        """Come il candidato viene presentato al modello nella scelta vincolata."""
        pezzi = [self.testo]
        if self.condizioni:
            pezzi.append(f"(condizione: {', '.join(self.condizioni)})")
        if self.livello == 2:
            pezzi.append(f"[regola di categoria: {self.polarita}]")
        return " ".join(pezzi)


# Tipi di corrispondenza che NON valgono come risposta. La regola è applicata dall'agente,
# non dall'adattatore di un singolo modello: vale per qualunque modello, anche futuro.
TIPI_NON_VALIDI = frozenset({"solo_materiale", "nessuna"})


@dataclass
class Scelta:
    """L'esito della scelta vincolata: un candidato reale, oppure nessuno."""

    scheda_id: int | None
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
    tipo_corrispondenza: str = ""
    motivo: str = ""
    candidati: list[Candidato] = field(default_factory=list)
    riconoscimento: Riconoscimento | None = None
    contesto: dict = field(default_factory=dict)   # il backend resta senza stato: lo rimanda il client

    @property
    def definitiva(self) -> bool:
        return self.livello_evidenza in (1, 2) and not self.chiarimento
