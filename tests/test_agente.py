"""Test dell'agente: riconoscimento, cascata dei livelli, scelta vincolata, risposta.

Il modello di visione è finto e programmabile: qui interessa il **flusso**, non la qualità
di Gemma, che si misurerà con il set di valutazione. La ricerca invece è quella vera, su un
database costruito in memoria e su Qdrant in modalità in-process.
"""
import sqlite3

import pytest

from ecoscan.agente.agente import Agente
from ecoscan.agente.recupero import arricchisci, candidati, condizioni_in_gioco
from ecoscan.agente.tipi import Candidato, Riconoscimento, Scelta
from ecoscan.db.carica import carica
from ecoscan.db.indicizza import costruisci
from ecoscan.db.vettorizza import apri_qdrant, indicizza, schede_da_indicizzare
from tests.conftest import VettorizzatoreFinto

DESTINAZIONI = [
    {"comune": "Torino", "nome": "imballaggi_plastica", "canale": "raccolta_ordinaria",
     "colore": "grigio chiaro", "flussi": ["plastica"], "alias_di": "", "note": ""},
    {"comune": "Torino", "nome": "rifiuto_non_recuperabile", "canale": "raccolta_ordinaria",
     "colore": "grigio", "flussi": ["residuo"], "alias_di": "", "note": ""},
    {"comune": "Torino", "nome": "carta_e_cartone", "canale": "raccolta_ordinaria",
     "colore": "giallo", "flussi": ["carta"], "alias_di": "", "note": ""},
]


def voce(slug, nome, condizioni, destinazione, avvertenza=None):
    return {"comune": "Torino", "slug": slug, "nome": nome, "nome_originale": nome,
            "condizioni": list(condizioni), "alias": [], "codice_materiale": None,
            "destinazioni": [destinazione], "avvertenza": avvertenza, "motivi": [],
            "da_revisionare": False}


VOCI = [
    voce("capsule-con", "Capsule del caffè in plastica", ["con residuo"], "rifiuto_non_recuperabile"),
    voce("capsule-senza", "Capsule del caffè in plastica", ["senza residuo"], "imballaggi_plastica"),
    voce("giornali", "Giornali e riviste", [], "carta_e_cartone"),
    voce("pirofile", "Pirofile da forno", [], "rifiuto_non_recuperabile"),
    voce("bottiglia", "Bottiglia di plastica", [], "imballaggi_plastica", avvertenza="Schiacciala"),
    voce("sci", "Sci e scarponi", [], "rifiuto_non_recuperabile"),
]

REGOLE = [
    {"comune": "Torino", "destinazione": "carta_e_cartone", "polarita": "ammesso",
     "testo": "Opuscoli, carta da pacchi, cartone e cartoncino", "dettaglio": None,
     "origine": "estrazione", "fonte": "amiat_rifiutologo_2025", "riferimento": "pagina 8"},
    {"comune": "Torino", "destinazione": "carta_e_cartone", "polarita": "escluso",
     "testo": "carta con residui di cibo", "dettaglio": "Scontrini... NON vanno conferiti nella carta!",
     "origine": "estrazione", "fonte": "amiat_rifiutologo_2025", "riferimento": "pagina 8"},
]


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
            return Scelta(scheda_id=None, motivo="nessuna voce corrisponde")
        scelto = candidati[self.indice_scelto - 1]
        return Scelta(scheda_id=scelto.scheda_id, motivo="somiglia", chiarimento=self.chiarimento)


@pytest.fixture
def ambiente(tmp_path):
    db = sqlite3.connect(":memory:")
    carica(db, DESTINAZIONI, VOCI, REGOLE, {})
    costruisci(db)
    qdrant = apri_qdrant(str(tmp_path / "q"))
    vettorizzatore = VettorizzatoreFinto()
    indicizza(qdrant, schede_da_indicizzare(db), vettorizzatore, avanzamento=lambda *_: None)
    yield db, qdrant, vettorizzatore
    qdrant.close()
    db.close()


def crea_agente(ambiente, modello):
    return Agente(*ambiente, modello=modello)


# ------------------------------------------------------------------ recupero

def test_i_candidati_portano_i_dati_del_relazionale(ambiente):
    db, qdrant, v = ambiente
    trovati = candidati(db, qdrant, v, "Bottiglia di plastica", "Torino", livello=1)
    scelto = next(c for c in trovati if c.nome == "Bottiglia di plastica")
    assert scelto.destinazioni == ["imballaggi_plastica"] and scelto.avvertenza == "Schiacciala"


def test_le_regole_portano_polarita_e_fonte(ambiente):
    db, qdrant, v = ambiente
    trovati = candidati(db, qdrant, v, "carta con residui di cibo", "Torino", livello=2)
    escluso = next(c for c in trovati if c.polarita == "escluso")
    assert escluso.destinazioni == ["carta_e_cartone"]
    assert escluso.riferimento == "pagina 8" and escluso.fonte == "amiat_rifiutologo_2025"


def test_i_livelli_non_si_mescolano(ambiente):
    db, qdrant, v = ambiente
    assert all(c.livello == 1 for c in candidati(db, qdrant, v, "carta", "Torino", livello=1))
    assert all(c.livello == 2 for c in candidati(db, qdrant, v, "carta", "Torino", livello=2))


def test_condizioni_in_gioco_riconosce_gli_omonimi_divergenti():
    gruppo = [
        Candidato(1, 1, "Capsule con residuo", nome="Capsule", condizioni=["con residuo"],
                  destinazioni=["rifiuto_non_recuperabile"]),
        Candidato(2, 1, "Capsule senza residuo", nome="Capsule", condizioni=["senza residuo"],
                  destinazioni=["imballaggi_plastica"]),
        Candidato(3, 1, "Giornali", nome="Giornali", destinazioni=["carta_e_cartone"]),
    ]
    assert set(condizioni_in_gioco(gruppo)) == {"con residuo", "senza residuo"}


def test_omonimi_con_stessa_destinazione_non_richiedono_chiarimento():
    gruppo = [Candidato(1, 1, "a", nome="X", condizioni=["pulito"], destinazioni=["carta"]),
              Candidato(2, 1, "b", nome="X", condizioni=["sporco"], destinazioni=["carta"])]
    assert condizioni_in_gioco(gruppo) == []


# ------------------------------------------------------------------ agente

def test_risposta_di_livello_1(ambiente):
    modello = ModelloFinto(Riconoscimento(oggetto="bottiglia di plastica",
                                          materiali=["plastica"], confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    assert risposta.livello_evidenza == 1 and risposta.comune == "Torino"
    assert risposta.destinazioni and risposta.riconoscimento.oggetto == "bottiglia di plastica"


def test_oggetto_non_riconosciuto_va_al_livello_3(ambiente):
    modello = ModelloFinto(Riconoscimento(oggetto="", confidenza=0.0))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    assert risposta.livello_evidenza == 3 and risposta.chiarimento
    assert modello.chiamate_scelta == 0   # non si cerca nulla se non si è riconosciuto niente


def test_confidenza_bassa_non_produce_una_risposta_sicura(ambiente):
    modello = ModelloFinto(Riconoscimento(oggetto="qualcosa", confidenza=0.05))
    assert crea_agente(ambiente, modello).analizza(b"foto", "Torino").livello_evidenza == 3


def test_cascata_dal_livello_1_al_2(ambiente):
    """Se nessuna voce corrisponde, si passa alle regole di categoria."""
    class SoloAlSecondoGiro(ModelloFinto):
        def scegli(self, riconoscimento, candidati, testo_utente=None):
            self.chiamate_scelta += 1
            if self.chiamate_scelta == 1:
                return Scelta(scheda_id=None, motivo="nessuna voce")
            return Scelta(scheda_id=candidati[0].scheda_id, motivo="regola di categoria")

    modello = SoloAlSecondoGiro(Riconoscimento(oggetto="carta", materiali=["carta"], confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    assert risposta.livello_evidenza == 2 and modello.chiamate_scelta == 2


def test_nessun_livello_copre_l_oggetto(ambiente):
    modello = ModelloFinto(Riconoscimento(oggetto="astronave", confidenza=0.9), indice_scelto=0)
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    assert risposta.livello_evidenza == 3 and "nessuna regola di Torino" in risposta.motivo
    assert not risposta.destinazioni


def test_chiarimento_quando_la_condizione_decide(ambiente):
    """Due voci omonime con destinazioni diverse: si chiede, non si indovina."""
    modello = ModelloFinto(Riconoscimento(oggetto="capsula del caffè in plastica",
                                          materiali=["plastica"], confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    if any(c.nome == "Capsule del caffè in plastica" for c in risposta.candidati):
        assert risposta.chiarimento and not risposta.definitiva


def test_la_ricerca_resta_dentro_il_comune(ambiente):
    modello = ModelloFinto(Riconoscimento(oggetto="giornali", confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Napoli")
    assert risposta.livello_evidenza == 3   # a Napoli non è caricato nulla


def test_il_contesto_permette_di_continuare_senza_rileggere_la_foto(ambiente):
    modello = ModelloFinto(Riconoscimento(oggetto="capsula del caffè in plastica",
                                          materiali=["plastica"], confidenza=0.9))
    agente = crea_agente(ambiente, modello)
    prima = agente.analizza(b"foto", "Torino")
    assert prima.contesto["comune"] == "Torino" and prima.contesto["prompt"]

    letture = {"n": 0}
    modello.riconosci = lambda *a, **k: letture.__setitem__("n", letture["n"] + 1)
    dopo = agente.continua(prima.contesto, "è vuota, senza residui")
    assert letture["n"] == 0 and dopo.comune == "Torino"


def test_il_contesto_registra_la_versione_dei_prompt(ambiente):
    risposta = crea_agente(ambiente, ModelloFinto()).analizza(b"foto", "Torino")
    etichette = risposta.contesto["prompt"]
    assert all("@" in e and ":" in e for e in etichette)
