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


class ProceduraUscita(BaseModel):
    """Come si conferisce, non solo dove.

    Viaggia con la risposta perché il frontend non può leggerla da sé: parla solo con le
    API. Le procedure arrivano già ordinate per sforzo, dalla più comoda alla più faticosa.
    """

    canale: str
    titolo: str
    passi: list[str] = []
    nota: str = ""
    sforzo: int = Field(description="1 si fa da casa, 5 ci devi andare tu")
    da_casa: bool
    da_verificare: str = Field(
        default="", description="cosa manca ancora a questa procedura: indirizzi, orari, recapiti")

    @classmethod
    def da(cls, p) -> ProceduraUscita:
        return cls(canale=p.canale, titolo=p.titolo, passi=list(p.passi), nota=p.nota,
                   sforzo=p.sforzo, da_casa=p.da_casa, da_verificare=p.da_verificare)


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
    procedure: list[ProceduraUscita] = Field(
        default=[],
        description="come si conferisce, per i canali diversi dalla raccolta ordinaria; "
                    "ordinate dalla più comoda alla più faticosa")
    ripiego: ProceduraUscita | None = Field(
        default=None,
        description="al livello 3: dove si può chiedere, visto che il comune non dice nulla")
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
