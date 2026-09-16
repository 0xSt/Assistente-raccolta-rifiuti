"""Strumenti condivisi fra i test: dati di prova, modelli finti e un ambiente completo.

L'ambiente costruisce un database in memoria, ne ricava i documenti e li indicizza su Qdrant
in modalità in-process. Nessun container, nessuna rete, nessun modello scaricato: i test
provano la meccanica vera (documenti, payload, filtri, varianti) e non la qualità del
modello, che si misura con le sonde.
"""
import sqlite3
from dataclasses import dataclass

import numpy as np
import pytest

from ecoscan.agente.tipi import Riconoscimento, Scelta
from ecoscan.db.carica import carica
from ecoscan.db.documenti import costruisci
from ecoscan.db.vettorizza import apri_qdrant, indicizza


class VettorizzatoreFinto:
    """Vettori deterministici dal testo: nessuna rete, risultati riproducibili."""

    nome = "finto"
    dimensione = 8

    def __init__(self):
        self.chiamate = 0

    def vettorizza(self, testi, come="documento"):
        self.chiamate += len(testi)
        vettori = []
        for t in testi:
            nudo = (t.replace("task: search result | query: ", "")
                     .replace("title: none | text: ", "").lower())
            generatore = np.random.default_rng(abs(hash(nudo)) % 2**32)
            vettori.append(generatore.normal(size=self.dimensione).tolist())
        return vettori


class ModelloFinto:
    """Modello programmabile: si decide cosa riconosce e quale candidato sceglie."""

    nome = "finto"

    def __init__(self, riconoscimento=None, indice_scelto=1, chiarimento=None):
        self.riconoscimento = riconoscimento or Riconoscimento(
            oggetto="capsula del caffè", materiali=["plastica"], confidenza=0.9)
        self.indice_scelto = indice_scelto   # 1-based; 0 significa "nessuno"
        self.chiarimento = chiarimento
        self.candidati_visti = []
        self.chiamate_scelta = 0

    def riconosci(self, immagine, testo_utente=None):
        return self.riconoscimento

    def scegli(self, riconoscimento, candidati, testo_utente=None):
        self.chiamate_scelta += 1
        self.candidati_visti.append(list(candidati))
        if not candidati or self.indice_scelto == 0 or self.indice_scelto > len(candidati):
            return Scelta(scheda_id=None, tipo_corrispondenza="nessuna",
                          motivo="nessun documento corrisponde")
        scelto = candidati[self.indice_scelto - 1]
        return Scelta(scheda_id=scelto.id, tipo_corrispondenza="stesso_oggetto",
                      motivo="somiglia", chiarimento=self.chiarimento)


class SceglieIlDocumento(ModelloFinto):
    """Sceglie il documento il cui testo contiene una parola data."""

    def __init__(self, parola: str, riconoscimento=None):
        super().__init__(riconoscimento)
        self.parola = parola.lower()

    def scegli(self, riconoscimento, candidati, testo_utente=None):
        self.chiamate_scelta += 1
        for candidato in candidati:
            if self.parola in candidato.testo.lower():
                return Scelta(scheda_id=candidato.id, tipo_corrispondenza="stesso_oggetto",
                              motivo=f"contiene {self.parola}")
        return Scelta(scheda_id=None, tipo_corrispondenza="nessuna", motivo="non trovato")


DESTINAZIONI = [
    {"comune": "Torino", "nome": "carta_e_cartone", "canale": "raccolta_ordinaria",
     "colore": "giallo", "flussi": ["carta"], "alias_di": "", "note": ""},
    {"comune": "Torino", "nome": "organico", "canale": "raccolta_ordinaria",
     "colore": "marrone", "flussi": ["organico"], "alias_di": "", "note": ""},
    {"comune": "Torino", "nome": "imballaggi_plastica", "canale": "raccolta_ordinaria",
     "colore": "grigio chiaro", "flussi": ["plastica"], "alias_di": "", "note": ""},
    {"comune": "Torino", "nome": "rifiuto_non_recuperabile", "canale": "raccolta_ordinaria",
     "colore": "grigio", "flussi": ["residuo"], "alias_di": "", "note": ""},
    {"comune": "Napoli", "nome": "Carta e Cartoncino", "canale": "raccolta_ordinaria",
     "colore": "blu", "flussi": ["carta"], "alias_di": "", "note": ""},
]


def voce(comune, slug, nome, condizioni, destinazione, alias=(), avvertenza=None, codice=None):
    return {"comune": comune, "slug": slug, "nome": nome, "nome_originale": nome,
            "condizioni": list(condizioni), "alias": list(alias), "codice_materiale": codice,
            "destinazioni": [destinazione], "avvertenza": avvertenza, "motivi": [],
            "da_revisionare": False}


VOCI = [
    voce("Torino", "pizza-pulito", "Cartone da pizza", ["pulito"], "carta_e_cartone"),
    voce("Torino", "pizza-sporco", "Cartone da pizza", ["sporco"], "organico"),
    voce("Torino", "capsule-con", "Capsule del caffè", ["con residuo"], "rifiuto_non_recuperabile"),
    voce("Torino", "capsule-senza", "Capsule del caffè", ["senza residuo"], "imballaggi_plastica"),
    voce("Torino", "giornali", "Giornali e riviste", [], "carta_e_cartone", alias=["quotidiani"]),
    voce("Torino", "bottiglia", "Bottiglia di plastica", [], "imballaggi_plastica",
         avvertenza="Schiacciala prima di buttarla"),
    voce("Torino", "simbolo-pap", "Simbolo PAP", [], "carta_e_cartone", codice="21"),
    voce("Torino", "pirofile", "Pirofile da forno", [], "rifiuto_non_recuperabile"),
    voce("Napoli", "giornale", "Giornale", [], "Carta e Cartoncino"),
]

REGOLE = [
    {"comune": "Torino", "destinazione": "carta_e_cartone", "polarita": "ammesso",
     "testo": "Giornali, riviste, libri, quaderni", "dettaglio": None, "origine": "estrazione",
     "fonte": "amiat_rifiutologo_2025", "riferimento": "pagina 8"},
    {"comune": "Torino", "destinazione": "carta_e_cartone", "polarita": "escluso",
     "testo": "carta con residui di cibo", "dettaglio": None, "origine": "estrazione",
     "fonte": "amiat_rifiutologo_2025", "riferimento": "pagina 8"},
    {"comune": "Torino", "destinazione": "organico", "polarita": "ammesso",
     "testo": "Avanzi di cucina e scarti di cibo", "dettaglio": None, "origine": "estrazione",
     "fonte": "amiat_rifiutologo_2025", "riferimento": "pagina 9"},
]


@dataclass
class Ambiente:
    db: sqlite3.Connection
    qdrant: object
    vettorizzatore: VettorizzatoreFinto
    documenti: list


@pytest.fixture
def vettorizzatore_finto():
    return VettorizzatoreFinto()


@pytest.fixture
def db():
    connessione = sqlite3.connect(":memory:", check_same_thread=False)
    carica(connessione, DESTINAZIONI, VOCI, REGOLE, {})
    yield connessione
    connessione.close()


@pytest.fixture
def ambiente(db, tmp_path):
    documenti = costruisci(db)
    qdrant = apri_qdrant(str(tmp_path / "qdrant"))
    vettorizzatore = VettorizzatoreFinto()
    indicizza(qdrant, documenti, vettorizzatore, avanzamento=lambda *_: None)
    yield Ambiente(db, qdrant, vettorizzatore, documenti)
    qdrant.close()
