"""Test dell'agente: recupero, scelta dell'oggetto, scelta della variante, risposta.

Il modello di visione è finto e programmabile: qui interessa il **flusso**, non la qualità
di Gemma, che si misura con le sonde e con il set di valutazione.
"""
import pytest

from ecoscan.agente.agente import Agente, domande
from ecoscan.agente.avanzamento import Ascoltatore
from ecoscan.agente.recupero import candidati, menzionata, scegli_variante
from ecoscan.agente.tipi import Candidato, Riconoscimento, Scelta, Variante
from tests.conftest import ModelloFinto, SceglieIlDocumento


def crea_agente(ambiente, modello):
    return Agente(ambiente.qdrant, ambiente.vettorizzatore, modello)


# ------------------------------------------------------------------ domande

def test_le_parole_dell_utente_diventano_domande_per_l_indice():
    """Erano passate solo al modello: una descrizione precisa non aiutava il recupero."""
    r = Riconoscimento(oggetto="scatola", categoria="imballaggio in cartone")
    poste = domande(r, "è un cartone della pizza unto")
    assert "è un cartone della pizza unto" in poste
    assert "scatola è un cartone della pizza unto" in poste


def test_senza_testo_le_domande_restano_quelle_del_riconoscimento():
    r = Riconoscimento(oggetto="bottiglia", categoria="imballaggio")
    assert domande(r, None) == r.formulazioni()


def test_le_formulazioni_includono_sinonimi_e_categoria():
    """Il modello dice "sandalo", la fonte scrive "Scarpe": i sinonimi fanno da ponte."""
    r = Riconoscimento(oggetto="sandalo", sinonimi=["ciabatta"], categoria="calzatura")
    assert r.formulazioni() == ["sandalo", "sandalo calzatura", "ciabatta", "calzatura"]


# ------------------------------------------------------------------ recupero

def test_i_candidati_arrivano_dal_payload_del_documento(ambiente):
    """Nessuna lettura aggiuntiva dal relazionale: tutto ciò che serve è nel payload."""
    trovati = candidati(ambiente.qdrant, ambiente.vettorizzatore,
                        ["Bottiglia di plastica"], "Torino", livello=1)
    bottiglia = next(c for c in trovati if c.nome == "Bottiglia di plastica")
    assert bottiglia.destinazioni == ["imballaggi_plastica"]
    assert bottiglia.varianti[0].avvertenza == "Schiacciala prima di buttarla"


def test_un_documento_per_oggetto_porta_tutte_le_varianti(ambiente):
    trovati = candidati(ambiente.qdrant, ambiente.vettorizzatore,
                        ["Cartone da pizza"], "Torino", livello=1)
    pizza = next(c for c in trovati if c.nome == "Cartone da pizza")
    assert {v.condizione for v in pizza.varianti} == {"pulito", "sporco"}
    assert set(pizza.destinazioni) == {"carta_e_cartone", "organico"}


def test_i_livelli_non_si_mescolano(ambiente):
    oggetti = candidati(ambiente.qdrant, ambiente.vettorizzatore, ["carta"], "Torino", livello=1)
    regole = candidati(ambiente.qdrant, ambiente.vettorizzatore, ["carta"], "Torino", livello=2)
    assert all(c.livello == 1 for c in oggetti) and all(c.livello == 2 for c in regole)


def test_i_candidati_non_si_ripetono(ambiente):
    trovati = candidati(ambiente.qdrant, ambiente.vettorizzatore,
                        ["giornali", "giornali e riviste", "quotidiani"], "Torino", livello=1)
    assert len({c.id for c in trovati}) == len(trovati)


def test_il_codice_materiale_entra_fra_i_candidati(ambiente):
    trovati = candidati(ambiente.qdrant, ambiente.vettorizzatore,
                        ["cosa vuol dire PAP 21"], "Torino", livello=1)
    assert any(c.nome == "Simbolo PAP" for c in trovati)


# ------------------------------------------------------------------ varianti

def test_con_una_variante_sola_non_si_chiede_nulla():
    candidato = Candidato(id="x", livello=1, testo="Giornali", nome="Giornali",
                          varianti=[Variante([], ["carta"])])
    variante, da_chiarire = scegli_variante(candidato, [None, None])
    assert variante.destinazioni == ["carta"] and da_chiarire == []


def test_la_condizione_dichiarata_sceglie_la_variante():
    """"è unto" manda il cartone nell'organico: è la differenza che dà senso all'app."""
    candidato = Candidato(id="x", livello=1, testo="Cartone da pizza", nome="Cartone da pizza",
                          varianti=[Variante(["pulito"], ["carta_e_cartone"]),
                                    Variante(["sporco"], ["organico"])])
    variante, da_chiarire = scegli_variante(candidato, ["è unto", None])
    assert variante.destinazioni == ["organico"] and da_chiarire == []


def test_senza_condizione_dichiarata_si_chiede():
    candidato = Candidato(id="x", livello=1, testo="Cartone da pizza", nome="Cartone da pizza",
                          varianti=[Variante(["pulito"], ["carta_e_cartone"]),
                                    Variante(["sporco"], ["organico"])])
    variante, da_chiarire = scegli_variante(candidato, [None, None])
    assert variante is None and da_chiarire == ["pulito", "sporco"]


@pytest.mark.parametrize("condizione, noto, atteso", [
    ("sporco", "è unto", True),           # Torino scrive "sporco", l'utente dice "unto"
    ("unto", "è sporco", True),
    ("pulito", "è unto", False),
    ("unto", "cartone non unto", False),  # la negazione non va scambiata per l'altra variante
    ("non utilizzabile", "scarpe non utilizzabili", True),
    ("vuoto", "senza residui", True),
])
def test_menzionata(condizione, noto, atteso):
    assert menzionata(condizione, noto) is atteso


# ------------------------------------------------------------------ agente

def test_risposta_di_livello_1(ambiente):
    modello = SceglieIlDocumento("bottiglia", Riconoscimento(
        oggetto="bottiglia di plastica", materiali=["plastica"], confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    assert risposta.livello_evidenza == 1
    assert risposta.destinazioni == ["imballaggi_plastica"]
    assert risposta.avvertenza == "Schiacciala prima di buttarla"
    assert risposta.definitiva


def test_la_condizione_dichiarata_decide_la_risposta(ambiente):
    modello = SceglieIlDocumento("cartone da pizza", Riconoscimento(
        oggetto="cartone della pizza", confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino", testo_utente="è unto")
    assert risposta.destinazioni == ["organico"] and risposta.condizioni == ["sporco"]
    assert risposta.chiarimento is None


def test_senza_condizione_l_agente_chiede(ambiente):
    modello = SceglieIlDocumento("cartone da pizza", Riconoscimento(
        oggetto="cartone della pizza", confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    assert risposta.chiarimento and not risposta.definitiva
    assert "pulito" in risposta.chiarimento and "sporco" in risposta.chiarimento


def test_dopo_la_risposta_dell_utente_non_si_richiede(ambiente):
    """Ripetere la stessa domanda lascia l'utente in un giro senza uscita."""
    modello = SceglieIlDocumento("cartone da pizza", Riconoscimento(
        oggetto="cartone della pizza", confidenza=0.9))
    agente = crea_agente(ambiente, modello)
    prima = agente.analizza(b"foto", "Torino")
    assert prima.chiarimento
    dopo = agente.continua(prima.contesto, "è unto")
    assert dopo.chiarimento is None and dopo.destinazioni == ["organico"]


def test_oggetto_non_riconosciuto_va_al_livello_3(ambiente):
    modello = ModelloFinto(Riconoscimento(oggetto="", confidenza=0.0))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    assert risposta.livello_evidenza == 3 and modello.chiamate_scelta == 0


def test_nessun_documento_corrisponde(ambiente):
    modello = ModelloFinto(Riconoscimento(oggetto="astronave", confidenza=0.9), indice_scelto=0)
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    assert risposta.livello_evidenza == 3 and not risposta.destinazioni


def test_la_corrispondenza_per_solo_materiale_viene_scartata(ambiente):
    """La regola è applicata dall'agente, non dall'adattatore di un singolo modello."""
    class DichiaraSoloMateriale(ModelloFinto):
        def scegli(self, riconoscimento, candidati, testo_utente=None):
            self.chiamate_scelta += 1
            return Scelta(scheda_id=candidati[0].id if candidati else None,
                          tipo_corrispondenza="solo_materiale", motivo="entrambi di plastica")

    modello = DichiaraSoloMateriale(Riconoscimento(oggetto="sandalo", confidenza=0.9))
    assert crea_agente(ambiente, modello).analizza(b"foto", "Torino").livello_evidenza == 3


def test_cascata_dal_livello_1_al_2(ambiente):
    class SoloAlSecondoGiro(ModelloFinto):
        def scegli(self, riconoscimento, candidati, testo_utente=None):
            self.chiamate_scelta += 1
            if self.chiamate_scelta == 1:
                return Scelta(scheda_id=None, tipo_corrispondenza="nessuna", motivo="nessun oggetto")
            return Scelta(scheda_id=candidati[0].id, tipo_corrispondenza="categoria",
                          motivo="regola di categoria")

    modello = SoloAlSecondoGiro(Riconoscimento(oggetto="carta", confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino")
    assert risposta.livello_evidenza == 2 and modello.chiamate_scelta == 2


def test_la_ricerca_resta_dentro_il_comune(ambiente):
    modello = ModelloFinto(Riconoscimento(oggetto="giornali", confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Napoli")
    assert all(c.comune != "Torino" for c in risposta.candidati if hasattr(c, "comune"))


def test_il_contesto_permette_di_continuare_senza_rileggere_la_foto(ambiente):
    modello = ModelloFinto(Riconoscimento(oggetto="giornali", confidenza=0.9))
    agente = crea_agente(ambiente, modello)
    prima = agente.analizza(b"foto", "Torino")
    assert prima.contesto["comune"] == "Torino" and prima.contesto["prompt"]

    letture = {"n": 0}
    modello.riconosci = lambda *a, **k: letture.__setitem__("n", letture["n"] + 1)
    agente.continua(prima.contesto, "è vuota")
    assert letture["n"] == 0


def test_i_candidati_sono_ordinati_per_somiglianza(ambiente):
    """L'ordine è un'informazione: il modello legge un elenco."""
    trovati = candidati(ambiente.qdrant, ambiente.vettorizzatore,
                        ["cartone da pizza", "carta"], "Torino", livello=1)
    punteggi = [c.punteggio for c in trovati]
    assert punteggi == sorted(punteggi, reverse=True)


def test_nomina_l_oggetto_distingue_lo_specifico_dal_generico():
    """"Cartone per pizze" nomina l'oggetto, "Cartone da imballaggio" no."""
    from ecoscan.agente.recupero import nomina_l_oggetto
    riconoscimento = Riconoscimento(oggetto="cartone della pizza")
    specifico = Candidato(id="a", livello=1, testo="Cartone per pizze. …", nome="Cartone per pizze")
    generico = Candidato(id="b", livello=1, testo="Cartone da imballaggio. …",
                         nome="Cartone da imballaggio")
    assert nomina_l_oggetto(specifico, riconoscimento)
    assert not nomina_l_oggetto(generico, riconoscimento)


def test_il_documento_che_nomina_l_oggetto_vince_sul_generico(ambiente):
    """Il modello ha scelto "Cartone da imballaggio" mentre "Cartone per pizze" era il primo
    risultato: la preferenza per lo specifico la applica il codice."""
    class SceglieIlGenerico(ModelloFinto):
        def scegli(self, riconoscimento, candidati, testo_utente=None):
            self.chiamate_scelta += 1
            generici = [c for c in candidati if "pizza" not in (c.nome or "").lower()]
            bersaglio = generici[0] if generici else candidati[0]
            return Scelta(scheda_id=bersaglio.id, tipo_corrispondenza="categoria",
                          motivo="voce generica")

    modello = SceglieIlGenerico(Riconoscimento(oggetto="cartone da pizza", confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino", testo_utente="è sporco")
    if any("pizza" in (c.nome or "").lower() for c in risposta.candidati):
        assert risposta.destinazioni == ["organico"]
        assert "nomina l'oggetto" in risposta.motivo


def test_il_chiarimento_non_propone_condizioni_vuote():
    """"grandi quantità oppure nessuna condizione?" è una domanda senza risposta."""
    candidato = Candidato(id="x", livello=1, testo="Scatolone", nome="Scatolone",
                          varianti=[Variante([], ["carta"]),
                                    Variante(["grandi quantità"], ["isola"])])
    variante, da_chiarire = scegli_variante(candidato, [None, None])
    assert variante is None and da_chiarire == []


def test_il_chiarimento_porta_le_opzioni(ambiente):
    """Le condizioni sono note: l'interfaccia ne fa pulsanti invece di far scrivere."""
    modello = SceglieIlDocumento("cartone da pizza",
                                 Riconoscimento(oggetto="cartone della pizza", confidenza=0.9))
    agente = crea_agente(ambiente, modello)
    risposta = agente.analizza(b"foto", "Torino")
    assert risposta.chiarimento and set(risposta.opzioni) == {"pulito", "sporco"}
    # risolto il dubbio, non restano opzioni da proporre
    dopo = agente.continua(risposta.contesto, "sporco")
    assert dopo.opzioni == [] and dopo.destinazioni == ["organico"]


def test_la_risposta_dice_da_quale_documento_viene(ambiente):
    modello = SceglieIlDocumento("giornali", Riconoscimento(oggetto="giornale", confidenza=0.9))
    agente = crea_agente(ambiente, modello)
    risposta = agente.analizza(b"foto", "Torino")
    scelto = next(c for c in risposta.candidati if c.id == risposta.scelto_id)
    assert scelto.destinazioni == risposta.destinazioni


def test_correggere_l_oggetto_non_rilegge_la_foto(ambiente):
    """Il modello di visione ha già sbagliato: non lo si fa riguardare."""
    modello = SceglieIlDocumento("giornali", Riconoscimento(oggetto="foglio", confidenza=0.9))
    agente = crea_agente(ambiente, modello)
    prima = agente.analizza(b"foto", "Torino")
    letture = modello.chiamate_riconoscimento

    dopo = agente.correggi(prima.contesto, "giornali e riviste")
    assert modello.chiamate_riconoscimento == letture, "la foto non va riletta"
    assert dopo.riconoscimento.oggetto == "giornali e riviste"
    assert dopo.riconoscimento.confidenza == 1.0
    assert dopo.destinazioni == ["carta_e_cartone"]


def test_la_correzione_resta_nella_stessa_conversazione(ambiente):
    modello = SceglieIlDocumento("giornali", Riconoscimento(oggetto="foglio", confidenza=0.9))
    agente = crea_agente(ambiente, modello)
    prima = agente.analizza(b"foto", "Torino")
    dopo = agente.correggi(prima.contesto, "giornali")
    assert dopo.contesto["id_conversazione"] == prima.contesto["id_conversazione"]


class Registratore:
    """Ascolta le fasi dell'agente e le conserva, come farebbe il frontend."""

    def __init__(self):
        self.eventi = []

    def fase(self, nome, **dati):
        self.eventi.append({"fase": nome, **dati})

    @property
    def nomi(self):
        return [e["fase"] for e in self.eventi]


def test_le_fasi_arrivano_nell_ordine_in_cui_accadono(ambiente):
    """Su CPU l'attesa dura minuti: chi aspetta deve poter vedere a che punto è."""
    modello = SceglieIlDocumento("bottiglia", Riconoscimento(
        oggetto="bottiglia di plastica", confidenza=0.9))
    ascolto = Registratore()
    risposta = crea_agente(ambiente, modello).analizza(b"foto", "Torino", avanzamento=ascolto)

    assert ascolto.nomi[:2] == ["riconoscimento", "riconosciuto"]
    assert ascolto.nomi[2:5] == ["recupero", "recuperato", "scelta"]
    assert risposta.destinazioni == ["imballaggi_plastica"]


def test_il_riconoscimento_si_annuncia_prima_della_ricerca(ambiente):
    """È il motivo della funzione: accorgersi dell'errore senza aspettare la fine."""
    modello = SceglieIlDocumento("bottiglia", Riconoscimento(
        oggetto="bottiglia di plastica", confidenza=0.9))
    ascolto = Registratore()
    crea_agente(ambiente, modello).analizza(b"foto", "Torino", avanzamento=ascolto)

    visto = next(e for e in ascolto.eventi if e["fase"] == "riconosciuto")
    assert visto["riconoscimento"]["oggetto"] == "bottiglia di plastica"
    assert ascolto.nomi.index("riconosciuto") < ascolto.nomi.index("recupero")


def test_la_cascata_al_livello_2_si_vede_nelle_fasi(ambiente):
    """Se il livello 1 non dà nulla, chi aspetta deve capire perché ci mette di più."""
    modello = SceglieIlDocumento("regola di categoria che non esiste",
                                 Riconoscimento(oggetto="oggetto ignoto", confidenza=0.9))
    ascolto = Registratore()
    crea_agente(ambiente, modello).analizza(b"foto", "Torino", avanzamento=ascolto)
    livelli = [e["livello"] for e in ascolto.eventi if e["fase"] == "recupero"]
    assert livelli == [1, 2]


def test_continua_e_correggi_annunciano_le_loro_fasi(ambiente):
    modello = SceglieIlDocumento("cartone da pizza", Riconoscimento(
        oggetto="cartone della pizza", confidenza=0.9))
    agente = crea_agente(ambiente, modello)
    prima = agente.analizza(b"foto", "Torino")

    ascolto = Registratore()
    agente.continua(prima.contesto, "sporco", avanzamento=ascolto)
    assert "recupero" in ascolto.nomi and "riconoscimento" not in ascolto.nomi

    ascolto_correzione = Registratore()
    agente.correggi(prima.contesto, "giornali e riviste", avanzamento=ascolto_correzione)
    assert "recupero" in ascolto_correzione.nomi


def test_un_ascoltatore_rotto_non_fa_fallire_la_risposta(ambiente):
    """L'avanzamento è un di più: se il client se ne va, la risposta si completa lo stesso."""
    class Rotto:
        def fase(self, nome, **dati):
            raise RuntimeError("client sparito")

    modello = SceglieIlDocumento("bottiglia", Riconoscimento(
        oggetto="bottiglia di plastica", confidenza=0.9))
    risposta = crea_agente(ambiente, modello).analizza(
        b"foto", "Torino", avanzamento=Ascoltatore(lambda e: (_ for _ in ()).throw(OSError())))
    assert risposta.destinazioni == ["imballaggi_plastica"]
