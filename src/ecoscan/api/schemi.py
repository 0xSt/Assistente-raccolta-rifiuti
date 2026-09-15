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
    def da(cls, r: Riconoscimento) -> "RiconoscimentoUscita":
        return cls(oggetto=r.oggetto, sinonimi=r.sinonimi, categoria=r.categoria,
                   materiali=r.materiali, stato=r.stato, confidenza=r.confidenza)


class CandidatoUscita(BaseModel):
    scheda_id: int
    livello: int = Field(description="1 voce di dizionario, 2 regola di categoria")
    testo: str
    nome: str | None = None
    condizioni: list[str] = []
    destinazioni: list[str] = []
    polarita: str | None = None
    trovato_da: dict[str, int] = Field(default_factory=dict,
                                       description="metodo di ricerca -> posizione")

    @classmethod
    def da(cls, c: Candidato) -> "CandidatoUscita":
        return cls(scheda_id=c.scheda_id, livello=c.livello, testo=c.testo, nome=c.nome,
                   condizioni=c.condizioni, destinazioni=c.destinazioni, polarita=c.polarita,
                   trovato_da=c.posizioni)


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
    definitiva: bool
    tipo_corrispondenza: str = ""
    motivo: str = ""
    riconoscimento: RiconoscimentoUscita | None = None
    candidati: list[CandidatoUscita] = []
    contesto: dict = Field(
        default_factory=dict,
        description="da rimandare a /continua: il servizio non conserva stato fra le chiamate")

    @classmethod
    def da(cls, r: Risposta) -> "RispostaUscita":
        return cls(
            livello_evidenza=r.livello_evidenza, comune=r.comune, oggetto=r.oggetto,
            destinazioni=r.destinazioni, polarita=r.polarita, condizioni=r.condizioni,
            avvertenza=r.avvertenza, fonte=r.fonte, riferimento=r.riferimento,
            chiarimento=r.chiarimento, definitiva=r.definitiva,
            tipo_corrispondenza=r.tipo_corrispondenza, motivo=r.motivo,
            riconoscimento=RiconoscimentoUscita.da(r.riconoscimento) if r.riconoscimento else None,
            candidati=[CandidatoUscita.da(c) for c in r.candidati], contesto=r.contesto)


class Continuazione(BaseModel):
    """Secondo giro dopo un chiarimento: il contesto torna com'era stato consegnato."""

    contesto: dict
    risposta: str = Field(description="ciò che l'utente ha risposto alla domanda")


class Ricerca(BaseModel):
    domanda: str
    comune: str
    livello: int | None = Field(default=None, description="1 o 2; assente cerca in entrambi")
    k: int = 8


class Riscontro(BaseModel):
    """Giudizio dell'utente su una risposta. Ogni riscontro è una riga del futuro set di
    valutazione: è il modo meno costoso per costruirlo."""

    comune: str
    corretta: bool
    oggetto: str | None = None
    destinazione_attesa: str | None = None
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
