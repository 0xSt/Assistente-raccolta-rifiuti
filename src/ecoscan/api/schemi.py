"""Schemi di ingresso e uscita delle API.

Sono la forma pubblica del sistema: i tipi interni dell'agente (`Risposta`, `Candidato`)
restano dataclass, qui vengono tradotti. La separazione serve a poter cambiare i tipi
interni senza rompere il contratto con il frontend, e viceversa.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ecoscan.agente.tipi import Candidato, Riconoscimento, Risposta


class RiconoscimentoUscita(BaseModel):
    oggetto: str
    sinonimi: list[str] = []
    categoria: str | None = None
    materiali: list[str] = []
    stato: str | None = None
    confidenza: float = 0.0

    @classmethod
    def da(cls, r: Riconoscimento) -> RiconoscimentoUscita:
        return cls(oggetto=r.oggetto, sinonimi=r.sinonimi, categoria=r.categoria,
                   materiali=r.materiali, stato=r.stato, confidenza=r.confidenza)


class VarianteUscita(BaseModel):
    condizione: str | None = None
    destinazioni: list[str] = []
    avvertenza: str | None = None


class CandidatoUscita(BaseModel):
    id: str
    livello: int = Field(description="1 oggetto di dizionario, 2 regola di categoria")
    testo: str
    nome: str | None = None
    varianti: list[VarianteUscita] = []
    destinazioni: list[str] = []
    polarita: str | None = None
    punteggio: float = 0.0

    @classmethod
    def da(cls, c: Candidato) -> CandidatoUscita:
        return cls(id=c.id, livello=c.livello, testo=c.testo, nome=c.nome,
                   varianti=[VarianteUscita(condizione=v.condizione, destinazioni=v.destinazioni,
                                            avvertenza=v.avvertenza) for v in c.varianti],
                   destinazioni=c.destinazioni, polarita=c.polarita, punteggio=c.punteggio)


class RispostaUscita(BaseModel):
    livello_evidenza: int = Field(
        description="1 voce di dizionario, 2 regola di categoria, 3 il comune non copre l'oggetto")
    comune: str
    oggetto: str | None = None
    destinazioni: list[str] = []
    polarita: str | None = None
    condizioni: list[str] = []
    avvertenza: str | None = None
    fonte: str | None = None
    riferimento: str | None = None
    chiarimento: str | None = Field(
        default=None, description="domanda da porre prima di considerare la risposta definitiva")
    opzioni: list[str] = Field(
        default=[], description="risposte possibili al chiarimento: l'interfaccia ne fa pulsanti")
    scelto_id: str | None = Field(
        default=None, description="il candidato da cui viene la risposta, per poterlo citare")
    definitiva: bool
    tipo_corrispondenza: str = ""
    motivo: str = ""
    contraddizione: bool = False
    riconoscimento: RiconoscimentoUscita | None = None
    candidati: list[CandidatoUscita] = []
    contesto: dict = Field(
        default_factory=dict,
        description="da rimandare a /continua: il servizio non conserva stato fra le chiamate")

    @classmethod
    def da(cls, r: Risposta) -> RispostaUscita:
        return cls(
            livello_evidenza=r.livello_evidenza, comune=r.comune, oggetto=r.oggetto,
            destinazioni=r.destinazioni, polarita=r.polarita, condizioni=r.condizioni,
            avvertenza=r.avvertenza, fonte=r.fonte, riferimento=r.riferimento,
            chiarimento=r.chiarimento, opzioni=r.opzioni, scelto_id=r.scelto_id,
            definitiva=r.definitiva,
            tipo_corrispondenza=r.tipo_corrispondenza, motivo=r.motivo,
            contraddizione=r.contraddizione,
            riconoscimento=RiconoscimentoUscita.da(r.riconoscimento) if r.riconoscimento else None,
            candidati=[CandidatoUscita.da(c) for c in r.candidati], contesto=r.contesto)


class Continuazione(BaseModel):
    """Secondo giro dopo un chiarimento: il contesto torna com'era stato consegnato."""

    contesto: dict
    risposta: str = Field(description="ciò che l'utente ha risposto alla domanda")


class Correzione(BaseModel):
    """L'oggetto riconosciuto è sbagliato e l'utente dice qual è: si rifà solo la ricerca."""

    contesto: dict
    oggetto: str = Field(min_length=1, description="l'oggetto secondo l'utente")


class Destinazione(BaseModel):
    """Un contenitore del comune, come va mostrato all'utente."""

    nome: str = Field(description="nome interno, quello che compare nelle risposte")
    etichetta: str = Field(description="come si scrive all'utente")
    canale: str
    colore: str | None = None
    note: str | None = None


class Ricerca(BaseModel):
    domanda: str
    comune: str
    livello: int | None = Field(default=None, description="1 o 2; assente cerca in entrambi")
    k: int = 8


class Domanda(BaseModel):
    """Una domanda scritta, senza foto: l'utente sa già come si chiama l'oggetto."""

    comune: str
    oggetto: str = Field(min_length=2, description="l'oggetto secondo l'utente")
    testo: str | None = Field(default=None, description="dettaglio facoltativo: \"è unto\"")


class Riscontro(BaseModel):
    """Giudizio dell'utente su una risposta, e materia prima per la valutazione.

    Il `contesto` non è un di più: contiene il riconoscimento con cui la risposta è stata
    prodotta, ed è ciò che permette di trasformare il giudizio in un caso rieseguibile senza
    rileggere la foto. Senza, resterebbe un pollice verso senza modo di riprodurlo.
    """

    comune: str
    corretta: bool
    oggetto: str | None = None
    destinazioni_date: list[str] = Field(
        default=[], description="cosa aveva risposto il sistema")
    destinazione_attesa: str | None = Field(
        default=None, description="dove andava davvero, secondo l'utente")
    motivo: str | None = Field(
        default=None, description="oggetto_sbagliato | contenitore_sbagliato | altro")
    nota: str | None = None
    contesto: dict = {}


class Comune(BaseModel):
    nome: str
    gestore: str
    voci: int
    regole: int


class Salute(BaseModel):
    stato: str
    database: bool
    qdrant: bool
    ollama: bool
    schede_indicizzate: int | None = None
    modello_visione: str
    dettagli: dict[str, str] = {}
