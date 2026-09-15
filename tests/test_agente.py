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
        return Scelta(scheda_id=scelto.scheda_id, tipo_corrispondenza="stesso_oggetto",
                      motivo="somiglia", chiarimento=self.chiarimento)


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


def test_la_confidenza_in_percentuale_viene_normalizzata():
    """I modelli rispondono spesso "100" invece di "1.0": senza normalizzare, ogni soglia
    su 0-1 diventerebbe inutile."""
    from ecoscan.agente.modelli import _confidenza
    assert _confidenza(100) == 1.0 and _confidenza(85) == 0.85
    assert _confidenza(0.9) == 0.9 and _confidenza(None) == 0.0 and _confidenza("boh") == 0.0


def test_i_candidati_di_tutti_i_livelli_restano_visibili(ambiente):
    """Se la risposta arriva dal livello 2, vedere cosa era stato scartato al livello 1
    spiega il perché."""
    class SoloAlSecondoGiro(ModelloFinto):
        def scegli(self, riconoscimento, candidati, testo_utente=None):
            self.chiamate_scelta += 1
            if self.chiamate_scelta == 1:
                return Scelta(scheda_id=None, motivo="nessuna voce")
            return Scelta(scheda_id=candidati[0].scheda_id, motivo="regola")

    modello = SoloAlSecondoGiro(Riconoscimento(oggetto="carta", confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    livelli = {c.livello for c in risposta.candidati}
    assert livelli == {1, 2}


def test_le_formulazioni_separano_oggetto_e_materiali():
    """I materiali nella stessa domanda trascinano la ricerca verso ciò che è *fatto di*
    quel materiale: cercando "sandalo gomma plastica" si trovano gomme da masticare."""
    r = Riconoscimento(oggetto="sandalo", materiali=["gomma", "plastica"], stato="usato")
    assert r.query_oggetto == "sandalo usato"
    assert r.formulazioni() == ["sandalo usato", "sandalo gomma plastica usato"]


def test_senza_materiali_una_sola_formulazione():
    assert Riconoscimento(oggetto="bottiglia").formulazioni() == ["bottiglia"]


def test_il_recupero_fonde_piu_formulazioni(ambiente):
    """Una voce trovata da più formulazioni deve salire in classifica."""
    db, qdrant, v = ambiente
    sola = candidati(db, qdrant, v, "Giornali e riviste", "Torino", livello=1, k=5)
    doppia = candidati(db, qdrant, v, ["Giornali e riviste", "Giornali e riviste carta"],
                       "Torino", livello=1, k=5)
    assert sola and doppia
    assert doppia[0].nome == "Giornali e riviste"


def test_formulazioni_vuote_ignorate(ambiente):
    db, qdrant, v = ambiente
    assert candidati(db, qdrant, v, ["", "   "], "Torino", livello=1) == []


def test_i_sinonimi_fanno_da_ponte_col_vocabolario_della_fonte():
    """Il modello dice "sandalo", ASIA scrive "Scarpe": senza sinonimi non si incontrano."""
    r = Riconoscimento(oggetto="sandalo", sinonimi=["ciabatta", "scarpa"], categoria="calzatura",
                       materiali=["gomma"])
    # "sandalo calzatura" viene subito dopo l'oggetto: toglie l'ambiguità alla parola sola,
    # che da sola recupera rumore ("Salse", "Sdraio")
    assert r.formulazioni() == ["sandalo", "sandalo calzatura", "ciabatta", "scarpa", "calzatura"]


def test_le_formulazioni_non_si_ripetono_e_sono_limitate():
    r = Riconoscimento(oggetto="scarpa", sinonimi=["Scarpa", "scarpa ", "calzatura"],
                       categoria="calzatura")
    assert r.formulazioni() == ["scarpa", "scarpa calzatura", "calzatura"]
    tante = Riconoscimento(oggetto="x", sinonimi=[f"s{i}" for i in range(10)])
    assert len(tante.formulazioni(massimo=3)) == 3


def test_la_corrispondenza_per_solo_materiale_viene_scartata_dal_codice(ambiente):
    """La regola non è affidata alla buona volontà del modello: la applica il codice."""
    class SceglieMaleMaLoDichiara(ModelloFinto):
        def scegli(self, riconoscimento, candidati, testo_utente=None):
            self.chiamate_scelta += 1
            return Scelta(scheda_id=candidati[0].scheda_id if candidati else None,
                          tipo_corrispondenza="solo_materiale", motivo="entrambi di plastica")

    from ecoscan.agente.tipi import TIPI_NON_VALIDI
    assert "solo_materiale" in TIPI_NON_VALIDI
    modello = SceglieMaleMaLoDichiara(Riconoscimento(oggetto="sandalo", confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    # il modello aveva indicato un candidato, ma il tipo dichiarato lo rende inutilizzabile
    assert risposta.livello_evidenza == 3


def test_il_tipo_di_corrispondenza_arriva_nella_risposta(ambiente):
    class ConTipo(ModelloFinto):
        def scegli(self, riconoscimento, candidati, testo_utente=None):
            self.chiamate_scelta += 1
            return Scelta(scheda_id=candidati[0].scheda_id, tipo_corrispondenza="sinonimo",
                          motivo="altro nome dello stesso oggetto")

    risposta = crea_agente(ambiente, ConTipo()).analizza(b"foto", "Torino")
    assert risposta.tipo_corrispondenza == "sinonimo"


def test_la_scelta_vede_categoria_e_sinonimi():
    """Senza categoria il modello può reinterpretare un nome ambiguo: davanti a "ciabatta"
    ha risposto "è un tipo di pane" e ha scelto una busta per alimenti."""
    from ecoscan.agente.modelli import _descrizione_oggetto
    testo = _descrizione_oggetto(
        Riconoscimento(oggetto="ciabatta", categoria="calzatura", sinonimi=["sandalo", "scarpa"],
                       materiali=["gomma"], stato="sporco"), None)
    assert "Categoria: calzatura" in testo
    assert "Chiamato anche: sandalo, scarpa" in testo
    assert "Oggetto: ciabatta" in testo


def test_lo_schema_del_riconoscimento_esige_sinonimi_e_categoria():
    """Lasciati facoltativi il modello li omette: è successo alla prima prova."""
    from ecoscan.agente.modelli import SCHEMA_RICONOSCIMENTO
    assert {"sinonimi", "categoria"} <= set(SCHEMA_RICONOSCIMENTO["required"])


def test_ogni_formulazione_porta_il_suo_primo_risultato(ambiente):
    """Con molte formulazioni la fusione premia chi compare in molte classifiche: una scheda
    trovata al primo posto da una sola formulazione può restare fuori dai candidati."""
    from ecoscan.agente.recupero import _fondi_garantendo_i_primi

    classifiche = {
        "a": [{"scheda_id": 1, "testo": "comune"}, {"scheda_id": 2, "testo": "x"}],
        "b": [{"scheda_id": 1, "testo": "comune"}, {"scheda_id": 3, "testo": "y"}],
        "solitaria": [{"scheda_id": 99, "testo": "Scarpe utilizzabile"}],
    }
    fusi = _fondi_garantendo_i_primi(classifiche, k=2)
    identificatori = [r["scheda_id"] for r in fusi]
    assert 1 in identificatori          # trovata da due formulazioni: resta in cima
    assert 99 in identificatori         # prima per una sola formulazione: garantita


@pytest.mark.parametrize("valore, atteso", [
    ("0", None),                                    # risposta reale del modello
    ("", None),
    ("Sì", None),
    ("È vuota o contiene ancora residui?", "È vuota o contiene ancora residui?"),
])
def test_un_chiarimento_che_non_e_una_domanda_viene_ignorato(valore, atteso):
    """Il campo è facoltativo e il modello lo riempie comunque: "0" mostrato all'utente
    sarebbe incomprensibile."""
    from ecoscan.agente.modelli import _chiarimento
    assert _chiarimento(valore) == atteso


def test_la_garanzia_copre_i_primi_due_risultati():
    """"calzatura" trova "Scarpe utilizzabile" al SECONDO posto, dietro "Laccio per scarpe":
    garantire solo il primo lasciava fuori la voce giusta."""
    from ecoscan.agente.recupero import _fondi_garantendo_i_primi

    classifiche = {
        "principale": [{"scheda_id": 1, "testo": "a"}, {"scheda_id": 2, "testo": "b"}],
        "calzatura": [{"scheda_id": 50, "testo": "Laccio per scarpe"},
                      {"scheda_id": 51, "testo": "Scarpe utilizzabile"}],
    }
    identificatori = [r["scheda_id"] for r in _fondi_garantendo_i_primi(classifiche, k=2)]
    assert 51 in identificatori


def test_i_candidati_non_crescono_oltre_il_massimo():
    """Un elenco lungo allunga il prompt della scelta senza aggiungere scelte utili, e su
    CPU il tempo si paga."""
    from ecoscan.agente.recupero import MASSIMO_CANDIDATI, _fondi_garantendo_i_primi

    classifiche = {f"m{i}": [{"scheda_id": i * 100 + j, "testo": "x"} for j in range(5)]
                   for i in range(8)}
    assert len(_fondi_garantendo_i_primi(classifiche, k=8)) <= MASSIMO_CANDIDATI
