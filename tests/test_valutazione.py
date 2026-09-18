"""Test della valutazione: i casi, la diagnosi, il riscontro che diventa dataset.

Si misura la meccanica della misura, non la qualità del sistema: che un caso si legga e si
scriva senza doppioni, che la diagnosi distingua un recupero fallito da una scelta
sbagliata, e che un pollice giù senza alternativa non entri nel dataset.
"""
import json

import pytest

from ecoscan.agente.agente import Agente
from ecoscan.valutazione import esegui as val
from ecoscan.valutazione.casi import Caso, aggiungi, caso_da_riscontro, leggi, tutti

# --------------------------------------------------------------------------- i casi


def test_un_caso_diventa_un_riconoscimento_certo():
    """Il riconoscimento è un dato, non un'ipotesi: la soglia di confidenza non va rieseguita."""
    caso = Caso(comune="Napoli", oggetto="forchetta", materiali=["acciaio"],
                destinazioni_attese=["Plastica e Metalli"])
    riconoscimento = caso.riconoscimento
    assert riconoscimento.oggetto == "forchetta"
    assert riconoscimento.materiali == ["acciaio"]
    assert riconoscimento.confidenza == 1.0


def test_un_caso_senza_attesa_non_e_valido():
    assert not Caso(comune="Napoli", oggetto="forchetta").valido
    assert not Caso(comune="Napoli", oggetto="", destinazioni_attese=["x"]).valido
    assert Caso(comune="Napoli", oggetto="forchetta", destinazioni_attese=["x"]).valido


def test_lo_stesso_caso_non_si_aggiunge_due_volte(tmp_path):
    """Dieci pollici su sullo stesso oggetto gonfierebbero le percentuali senza misurare
    niente di nuovo."""
    percorso = tmp_path / "da_riscontri.jsonl"
    caso = Caso(comune="Napoli", oggetto="forchetta", destinazioni_attese=["Indifferenziata"])
    assert aggiungi(caso, percorso) is True
    assert aggiungi(caso, percorso) is False
    assert len(leggi(percorso)) == 1


def test_il_caso_manuale_vince_su_quello_da_riscontro(tmp_path):
    """L'attesa decisa da noi batte quella di un utente che potrebbe sbagliarsi."""
    manuale = Caso(comune="Napoli", oggetto="forchetta", destinazioni_attese=["Metalli"])
    da_utente = Caso(comune="Napoli", oggetto="forchetta", destinazioni_attese=["Indifferenziata"],
                     origine="riscontro")
    (tmp_path / "casi.jsonl").write_text(
        json.dumps(manuale.__dict__, ensure_ascii=False) + "\n", encoding="utf-8")
    aggiungi(da_utente, tmp_path / "da_riscontri.jsonl")

    raccolti = tutti(tmp_path)
    assert len(raccolti) == 1
    assert raccolti[0].destinazioni_attese == ["Metalli"]


def test_un_campo_sconosciuto_nel_file_non_rompe_la_lettura(tmp_path):
    """I file crescono nel tempo: un campo in più di una versione futura non deve fermare
    la valutazione di oggi."""
    percorso = tmp_path / "casi.jsonl"
    percorso.write_text(json.dumps(
        {"comune": "Napoli", "oggetto": "x", "destinazioni_attese": ["y"], "domani": 1}) + "\n",
        encoding="utf-8")
    assert leggi(percorso)[0].oggetto == "x"


# --------------------------------------------------------------- dal riscontro al caso

BASE = {"comune": "Napoli", "oggetto": "forchetta", "destinazioni_date": ["Indifferenziata"],
        "contesto": {"riconoscimento": {"oggetto": "forchetta", "materiali": ["acciaio"],
                                        "categoria": "posata"}}}


def test_il_pollice_su_fissa_le_destinazioni_date():
    caso = caso_da_riscontro({**BASE, "corretta": True})
    assert caso.destinazioni_attese == ["Indifferenziata"]
    assert caso.origine == "riscontro"
    assert caso.materiali == ["acciaio"]      # rieseguibile senza rileggere la foto
    assert caso.categoria == "posata"


def test_il_pollice_giu_con_alternativa_fissa_quella_dell_utente():
    caso = caso_da_riscontro({**BASE, "corretta": False,
                              "destinazione_attesa": "Plastica e Metalli",
                              "motivo": "contenitore_sbagliato"})
    assert caso.destinazioni_attese == ["Plastica e Metalli"]


def test_il_pollice_giu_senza_alternativa_non_diventa_un_caso():
    """Sapere che è sbagliata senza sapere cosa era giusto non si può misurare."""
    assert caso_da_riscontro({**BASE, "corretta": False}) is None


def test_un_oggetto_riconosciuto_male_non_diventa_un_caso():
    """Il difetto sta nel riconoscimento, che è proprio il passaggio che i casi tengono fermo."""
    assert caso_da_riscontro({**BASE, "corretta": False, "motivo": "oggetto_sbagliato",
                              "destinazione_attesa": "Vetro"}) is None


def test_senza_oggetto_non_si_costruisce_niente():
    assert caso_da_riscontro({"comune": "Napoli", "corretta": True}) is None


# --------------------------------------------------------------------------- la diagnosi

def caso_dei_giornali(**extra) -> Caso:
    """Una voce senza varianti: l'attesa è una sola destinazione, quindi l'esito non dipende
    da quale condizione il codice sceglie."""
    return Caso(comune="Torino", oggetto="giornale",
                destinazioni_attese=["carta_e_cartone"], **extra)


def test_corretto_quando_la_risposta_porta_alla_destinazione_attesa(ambiente):
    from tests.conftest import SceglieIlDocumento
    agente = Agente(ambiente.recupero, SceglieIlDocumento("Giornali"), k=8)
    esito = val.valuta_caso(agente, caso_dei_giornali())
    assert esito.diagnosi == val.CORRETTO
    assert esito.recuperato is True


def test_recupero_fallito_quando_il_documento_atteso_non_esce(ambiente):
    """La distinzione che conta: se nessun documento fra i candidati porta dove doveva, il
    modello non poteva sceglierlo, e intervenire sul prompt non servirebbe a niente."""
    from tests.conftest import ModelloFinto
    caso = Caso(comune="Torino", oggetto="giornale",
                destinazioni_attese=["destinazione che nessun documento raggiunge"])
    agente = Agente(ambiente.recupero, ModelloFinto(indice_scelto=0), k=8)
    esito = val.valuta_caso(agente, caso)
    assert esito.recuperato is False
    assert esito.posizione is None
    assert esito.diagnosi == val.RECUPERO_FALLITO


@pytest.mark.parametrize("recuperato, destinazioni, diagnosi", [
    # il documento c'era e la risposta ci è arrivata: niente da fare
    (True, ["carta_e_cartone"], val.CORRETTO),
    # il caso della forchetta: il documento c'era, il modello ha scelto un altro.
    # Si interviene sul prompt di scelta, non sull'indice
    (True, ["organico"], val.SCELTA_SBAGLIATA),
    # il modello non poteva sceglierlo: si interviene sull'indice o sulle formulazioni
    (False, ["organico"], val.RECUPERO_FALLITO),
    # giusto per caso: una regola di categoria ha rimediato a un dizionario incompleto
    (False, ["carta_e_cartone"], val.ALTRA_STRADA),
])
def test_la_diagnosi_dice_dove_intervenire(recuperato, destinazioni, diagnosi):
    """La tabella 2x2 che rende la valutazione azionabile: non "quanto sbaglia", ma
    "dove va messa la prossima ora di lavoro"."""
    esito = val.Esito(caso=caso_dei_giornali(), recuperato=recuperato,
                      destinazioni=destinazioni)
    assert esito.diagnosi == diagnosi


def test_una_scelta_sbagliata_si_riconosce_eseguendo_un_caso(ambiente):
    """La stessa diagnosi, ma dall'esecuzione vera: il modello sceglie un documento che
    porta altrove, e il recupero aveva fatto il suo."""
    from tests.conftest import ModelloFinto
    agente = Agente(ambiente.recupero, ModelloFinto(indice_scelto=0), k=8)
    esito = val.valuta_caso(agente, caso_dei_giornali(livello_atteso=1))
    assert esito.recuperato is True
    assert esito.livello_corretto is not None


def test_senza_modello_si_misura_il_solo_recupero(ambiente):
    """La modalità piu utile mentre si lavora sull'indice: non tocca il modello, quindi si
    esegue in secondi invece che in minuti, e misura il tetto."""
    from ecoscan.valutazione.esegui import _ModelloAssente
    agente = Agente(ambiente.recupero, _ModelloAssente(), k=8)
    esito = val.valuta_caso(agente, caso_dei_giornali(), con_modello=False)
    assert esito.valutata_la_scelta is False
    assert esito.recuperato is True
    assert val.misure([esito])["risposte_corrette"] is None


def test_le_misure_sono_percentuali_sui_casi_eseguiti(ambiente):
    from tests.conftest import SceglieIlDocumento
    agente = Agente(ambiente.recupero, SceglieIlDocumento("Giornali"), k=8)
    esiti = [val.valuta_caso(agente, caso_dei_giornali())]
    misure = val.misure(esiti)
    assert misure["casi"] == 1
    assert misure["recupero"] == 100.0


def test_senza_casi_le_misure_non_esplodono():
    assert val.misure([])["casi"] == 0


@pytest.mark.parametrize("destinazioni, attese, atteso", [
    (["carta_e_cartone"], ["carta_e_cartone"], True),
    # basta una destinazione in comune: un oggetto con piu varianti ne offre parecchie
    (["organico", "carta_e_cartone"], ["carta_e_cartone"], True),
    (["organico"], ["carta_e_cartone"], False),
    ([], ["carta_e_cartone"], False),
])
def test_un_documento_porta_alla_destinazione_attesa(destinazioni, attese, atteso):
    from ecoscan.agente.tipi import Candidato, Variante
    candidato = Candidato(id="x", livello=1, testo="t",
                          varianti=[Variante(destinazioni=destinazioni)])
    assert val.porta_alla_destinazione(candidato, attese) is atteso
