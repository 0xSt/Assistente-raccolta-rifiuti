"""Test del frontend: client HTTP e formattazione dei messaggi.

L'interfaccia Streamlit non si prova qui; si provano le due parti che si sbagliano davvero,
cioè come si parla col backend e come una risposta diventa un messaggio leggibile.
"""
import pytest

from ecoscan.frontend import presentazione
from ecoscan.frontend.cliente import ClienteAPI, ErroreBackend


class RispostaFinta:
    def __init__(self, stato=200, corpo=None, testo=""):
        self.status_code, self._corpo, self.text = stato, corpo, testo

    def json(self):
        if self._corpo is None:
            raise ValueError("non è JSON")
        return self._corpo


@pytest.fixture
def cliente():
    return ClienteAPI("http://esempio/api/v1")


def test_analizza_manda_foto_e_comune(cliente, monkeypatch):
    visti = {}

    def finta(metodo, url, **argomenti):
        visti.update({"metodo": metodo, "url": url, **argomenti})
        return RispostaFinta(corpo={"comune": "Napoli"})

    monkeypatch.setattr("requests.request", finta)
    assert cliente.analizza(b"bytes", "foto.jpg", "Napoli", "è vuota")["comune"] == "Napoli"
    assert visti["url"].endswith("/analizza") and visti["data"] == {"comune": "Napoli", "testo": "è vuota"}
    assert visti["files"]["foto"][0] == "foto.jpg"


def test_il_testo_facoltativo_non_viene_inviato_se_vuoto(cliente, monkeypatch):
    visti = {}
    monkeypatch.setattr("requests.request",
                        lambda m, u, **a: visti.update(a) or RispostaFinta(corpo={}))
    cliente.analizza(b"x", "f.jpg", "Napoli", None)
    assert visti["data"] == {"comune": "Napoli"}


def test_un_errore_del_backend_diventa_un_messaggio_leggibile(cliente, monkeypatch):
    monkeypatch.setattr("requests.request",
                        lambda m, u, **a: RispostaFinta(404, {"detail": "comune sconosciuto: Atlantide"}))
    with pytest.raises(ErroreBackend, match="Atlantide"):
        cliente.comuni()


def test_le_destinazioni_si_chiedono_per_comune(cliente, monkeypatch):
    visti = {}

    def finta(metodo, url, **argomenti):
        visti.update({"url": url, **argomenti})
        return RispostaFinta(corpo=[{"nome": "organico", "etichetta": "Organico"}])

    monkeypatch.setattr("requests.request", finta)
    assert cliente.destinazioni("Torino")[0]["etichetta"] == "Organico"
    assert visti["url"].endswith("/destinazioni") and visti["params"] == {"comune": "Torino"}


def test_la_correzione_manda_contesto_e_oggetto(cliente, monkeypatch):
    visti = {}
    monkeypatch.setattr("requests.request",
                        lambda m, u, **a: visti.update({"url": u, **a}) or RispostaFinta(corpo={}))
    cliente.correggi({"comune": "Torino"}, "cartone della pizza")
    assert visti["url"].endswith("/correggi")
    assert visti["json"] == {"contesto": {"comune": "Torino"}, "oggetto": "cartone della pizza"}


def test_backend_spento_dice_come_avviarlo(cliente, monkeypatch):
    import requests

    def rifiuta(*a, **k):
        raise requests.exceptions.ConnectionError()

    monkeypatch.setattr("requests.request", rifiuta)
    with pytest.raises(ErroreBackend, match="ecoscan-api"):
        cliente.comuni()


def test_attesa_scaduta_spiega_perche(cliente, monkeypatch):
    import requests

    def tarda(*a, **k):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr("requests.request", tarda)
    with pytest.raises(ErroreBackend, match="minuti"):
        cliente.analizza(b"x", "f.jpg", "Napoli")


# ------------------------------------------------------------------ presentazione

ETICHETTE = {"imballaggi_plastica": "Imballaggi in plastica", "organico": "Organico",
             "carta_e_cartone": "Carta e cartone"}


def test_una_regola_di_esclusione_non_viene_ribaltata():
    """Presentata male, una regola di esclusione dice l'opposto del vero."""
    testo = presentazione.titolo({"oggetto": "tetrapak", "destinazioni": ["imballaggi_plastica"],
                                  "polarita": "escluso"}, ETICHETTE)
    assert "**non** va in" in testo and "Imballaggi in plastica" in testo


def test_il_nome_interno_della_destinazione_non_si_mostra():
    """A Torino le destinazioni nei dati sono chiavi: l'utente non deve mai leggerle."""
    testo = presentazione.titolo({"oggetto": "giornale", "destinazioni": ["carta_e_cartone"]},
                                 ETICHETTE)
    assert "Carta e cartone" in testo and "carta_e_cartone" not in testo


def test_senza_etichette_il_nome_interno_si_rende_leggibile():
    """Se /destinazioni non risponde la risposta arriva lo stesso, solo meno curata."""
    assert presentazione.etichetta("carta_e_cartone") == "Carta e cartone"
    assert presentazione.etichetta("Plastica e Metalli") == "Plastica e Metalli"


def test_si_dice_cosa_e_stato_riconosciuto_nella_foto():
    """È il passaggio più fragile: l'utente se ne accorge solo se lo vede."""
    frase = presentazione.frase_riconoscimento({"riconoscimento": {
        "oggetto": "cartone della pizza", "stato": "unto", "confidenza": 0.9}})
    assert "cartone della pizza" in frase and "unto" in frase
    assert presentazione.frase_riconoscimento({"riconoscimento": {"oggetto": ""}}) == ""


def test_il_riconoscimento_non_mostra_i_campi_interni():
    """Categoria e confidenza sono giudizi su cui l'utente non può fare niente: mostrarli
    riempie la riga che serve a smentire l'oggetto."""
    frase = presentazione.frase_riconoscimento({"riconoscimento": {
        "oggetto": "bicchiere", "categoria": "stoviglia", "materiali": ["vetro"],
        "confidenza": 0.3}})
    assert frase == "Ho riconosciuto: **bicchiere**"
    assert "👁️" not in frase


def test_il_materiale_si_mostra_solo_se_ha_deciso():
    """Fra "Bicchiere di vetro" e "Bicchiere in plastica" il materiale è la risposta: lì
    l'utente deve poterlo smentire."""
    frase = presentazione.frase_riconoscimento(
        {"condizioni": ["vetro"],
         "riconoscimento": {"oggetto": "bicchiere", "materiali": ["vetro"]}})
    assert frase == "Ho riconosciuto: **bicchiere**, vetro"


def test_con_due_varianti_l_altra_strada_e_una_frase():
    """Vedere il ramo non scelto insegna la regola per la volta dopo; con due rami l'altro
    è uno solo e si nomina, invece di diventare una tabella."""
    testo = presentazione.corpo({"livello_evidenza": 1, "condizioni": ["unto"],
                                 "scelto_id": "c1", "candidati": [{"id": "c1", "varianti": [
                                     {"condizione": "pulito", "destinazioni": ["carta_e_cartone"]},
                                     {"condizione": "unto", "destinazioni": ["organico"]}]}]},
                                ETICHETTE)
    assert testo.startswith("Se invece è pulito: **Carta e cartone**.")
    assert "→" not in testo and "✓" not in testo


def test_con_tre_varianti_resta_l_elenco():
    """Da tre in su la frase sola non regge: il confronto è fra più righe."""
    testo = presentazione.corpo({"livello_evidenza": 1, "condizioni": ["unto"],
                                 "scelto_id": "c1", "candidati": [{"id": "c1", "varianti": [
                                     {"condizione": "pulito", "destinazioni": ["carta_e_cartone"]},
                                     {"condizione": "unto", "destinazioni": ["organico"]},
                                     {"condizione": "rotto", "destinazioni": ["organico"]}]}]},
                                ETICHETTE)
    assert "se è pulito → Carta e cartone" in testo
    assert "**se è unto → Organico** ✓" in testo


def test_una_fonte_con_url_diventa_un_link():
    nota = presentazione.nota_fonte({
        "livello_evidenza": 1, "fonte": "asia_napoli_dove_lo_butto",
        "riferimento": "https://www.asianapoli.it/dove-lo-butto/abito-usato/"})
    assert "[Dizionario" in nota and "](https://www.asianapoli.it/dove-lo-butto/abito-usato/)" in nota


def test_una_fonte_senza_url_resta_testo():
    nota = presentazione.nota_fonte({"livello_evidenza": 1, "fonte": "amiat_rifiutologo_2025",
                                     "riferimento": "Rifiutologo AMIAT 2025, pagina 16"})
    assert "](" not in nota and "pagina 16" in nota
    assert nota.count("Rifiutologo AMIAT 2025") == 1, "il riferimento nomina già il documento"


def test_una_fonte_e_un_riferimento_distinti_si_leggono_entrambi():
    nota = presentazione.nota_fonte({"livello_evidenza": 2, "fonte": "amiat_rifiutologo_2025",
                                     "riferimento": "pagina 8"})
    assert "Rifiutologo AMIAT 2025" in nota and "pagina 8" in nota


def test_una_voce_ammessa_dice_dove_va():
    testo = presentazione.titolo({"oggetto": "bottiglia", "destinazioni": ["Plastica e Metalli"]})
    assert testo.startswith("Bottiglia: va in") and "Plastica e Metalli" in testo


def test_senza_destinazioni_lo_dice_chiaramente():
    assert "Non so" in presentazione.titolo({"destinazioni": []})


def test_il_livello_di_evidenza_si_dice_solo_quando_e_un_eccezione():
    """Una frase che compare in ogni risposta non informa: al livello 1 la voce nomina
    l'oggetto, che è ciò che l'utente si aspetta già."""
    assert presentazione.corpo({"livello_evidenza": 1,
                                "tipo_corrispondenza": "stesso_oggetto"}) == ""
    assert presentazione.corpo({"livello_evidenza": 1, "tipo_corrispondenza": "sinonimo"}) == ""
    categoria = presentazione.corpo({"livello_evidenza": 1, "tipo_corrispondenza": "categoria"})
    assert "non elenca proprio questo oggetto" in categoria
    assert "regola generale del contenitore" in presentazione.corpo({"livello_evidenza": 2})
    tre = presentazione.corpo({"livello_evidenza": 3})
    assert "non dice nulla" in tre and "centro di raccolta" in tre


def test_la_condizione_sta_nel_titolo_e_non_altrove():
    """"va in Organico se è unto" è una frase; titolo più "Vale se è unto." sono due
    affermazioni che l'utente deve rimettere insieme."""
    risposta = {"livello_evidenza": 1, "tipo_corrispondenza": "stesso_oggetto",
                "oggetto": "cartone della pizza", "destinazioni": ["organico"],
                "condizioni": ["unto"]}
    assert presentazione.titolo(risposta, ETICHETTE) == \
        "Cartone della pizza: va in **Organico** se è unto."
    assert "Vale" not in presentazione.messaggio(risposta, ETICHETTE)
    assert presentazione.messaggio(risposta, ETICHETTE).count("unto") == 1


def test_una_condizione_di_quantita_entra_nel_titolo_senza_diventare_uno_stato():
    """"Vale se è: piccole quantità" era la frase sbagliata più visibile."""
    testo = presentazione.titolo({"oggetto": "polistirolo", "destinazioni": ["organico"],
                                  "condizioni": ["piccole quantità"]}, ETICHETTE)
    assert testo.endswith("per piccole quantità.") and "se è" not in testo


def test_avvertenza_e_condizioni_compaiono():
    risposta = {"livello_evidenza": 1, "oggetto": "barattolo", "destinazioni": ["organico"],
                "condizioni": ["unto"], "avvertenza": "Svuotalo prima"}
    testo = presentazione.messaggio(risposta, ETICHETTE)
    assert "unto" in testo and "Svuotalo prima" in testo


def test_la_nota_di_fonte_dice_livello_e_provenienza():
    nota = presentazione.nota_fonte({"livello_evidenza": 2, "fonte": "amiat_rifiutologo_2025",
                                     "riferimento": "pagina 8"})
    assert "regola di categoria" in nota and "pagina 8" in nota


def test_la_risposta_riprende_cio_che_l_utente_ha_appena_detto():
    """È la parola che fa di due messaggi affiancati uno scambio."""
    risposta = {"livello_evidenza": 1, "oggetto": "cartone della pizza",
                "destinazioni": ["organico"], "condizioni": ["unto"]}
    assert presentazione.titolo(risposta, ETICHETTE, risposto="è tutto unto") == \
        "Ok, unto: va in **Organico**.", "si riprende la condizione applicata, non le sue parole"
    assert presentazione.titolo(risposta, ETICHETTE).startswith("Cartone della pizza:")




def test_la_ripresa_non_ripete_il_nome_del_contenitore():
    """"Ok, vetro: va in Vetro" è peggio del titolo normale."""
    risposta = {"oggetto": "bicchiere", "destinazioni": ["vetro"], "condizioni": []}
    assert presentazione.titolo(risposta, {"vetro": "Vetro"}, risposto="vetro") == \
        "Bicchiere: va in **Vetro**."


def test_la_contraddizione_della_fonte_viene_detta():
    """Quando il comune dà destinazioni diverse per lo stesso caso, l'utente deve saperlo."""
    testo = presentazione.corpo({"livello_evidenza": 1, "contraddizione": True})
    assert "destinazioni diverse" in testo


def test_il_frontend_non_importa_il_backend():
    """Il frontend deve parlare solo con le API: se importasse l'agente o il database,
    la valutazione misurerebbe qualcosa di diverso da ciò che usa l'utente."""
    import ast

    from ecoscan.percorsi import RADICE

    vietati = ("ecoscan.agente", "ecoscan.db")
    for file in (RADICE / "src/ecoscan/frontend").glob("*.py"):
        albero = ast.parse(file.read_text(encoding="utf-8"))
        moduli = [n.module or "" for n in ast.walk(albero) if isinstance(n, ast.ImportFrom)]
        moduli += [a.name for n in ast.walk(albero) if isinstance(n, ast.Import) for a in n.names]
        assert not [m for m in moduli if m.startswith(vietati)], f"{file.name} importa il backend"


def test_il_controfattuale_di_una_quantita_non_diventa_uno_stato():
    """"Se invece è piccole quantità" è la frase sbagliata che il tipo evita."""
    testo = presentazione.corpo({"livello_evidenza": 1, "condizioni": ["grandi quantità"],
                                 "scelto_id": "c1", "candidati": [{"id": "c1", "varianti": [
                                     {"condizione": "piccole quantità", "destinazioni": ["organico"]},
                                     {"condizione": "grandi quantità",
                                      "destinazioni": ["carta_e_cartone"]}]}]}, ETICHETTE)
    assert testo == "Per piccole quantità: **Organico**."


# ------------------------------------------------------ domanda scritta e legenda

def test_la_domanda_scritta_manda_comune_e_oggetto(cliente, monkeypatch):
    visti = {}
    monkeypatch.setattr("requests.request",
                        lambda m, u, **a: visti.update({"url": u, **a}) or RispostaFinta(corpo={}))
    cliente.domanda("Torino", "cartone della pizza")
    assert visti["url"].endswith("/domanda")
    assert visti["json"] == {"comune": "Torino", "oggetto": "cartone della pizza", "testo": None}


def test_le_etichette_si_ricavano_dall_elenco_dei_contenitori(monkeypatch):
    """La legenda e la traduzione delle risposte leggono la stessa cosa: una chiamata sola."""
    from ecoscan.frontend import app as interfaccia

    monkeypatch.setattr(interfaccia, "elenco_destinazioni",
                        lambda base, comune: [{"nome": "organico", "etichetta": "Organico",
                                               "canale": "raccolta_ordinaria"}])
    assert interfaccia.etichette_destinazioni("x", "Torino") == {"organico": "Organico"}


# ------------------------------------------------------- il come, non solo il dove

PROCEDURA_RITIRO = {"canale": "ritiro_domicilio", "titolo": "Lo ritirano a casa tua",
                    "passi": ["Chiama il numero verde", "Esponilo la sera prima"],
                    "nota": "Senza prenotazione è abbandono di rifiuti.",
                    "sforzo": 2, "da_casa": True}
PROCEDURA_ISOLA = {"canale": "centro_raccolta", "titolo": "Lo porti tu all'isola ecologica",
                   "passi": ["Porta un documento", "Vai negli orari di apertura"],
                   "nota": "", "sforzo": 5, "da_casa": False}


def test_la_procedura_diventa_passi_nel_corpo():
    """Per un microonde "va in Isola Ecologica" è vero e insufficiente: manca il come."""
    testo = presentazione.corpo({"livello_evidenza": 1, "procedure": [PROCEDURA_ISOLA]})
    assert "Lo porti tu all'isola ecologica" in testo
    assert "- Porta un documento" in testo
    assert "- Vai negli orari di apertura" in testo


def test_piu_canali_diventano_alternative_numerate_dalla_piu_comoda():
    """L'ordine è il messaggio: prima ciò che si fa da casa, poi ciò che chiede la macchina."""
    testo = presentazione.corpo({"livello_evidenza": 1,
                                 "procedure": [PROCEDURA_RITIRO, PROCEDURA_ISOLA]})
    assert "Puoi fare in due modi" in testo
    assert testo.index("1. Lo ritirano a casa tua") < testo.index("2. Lo porti tu")
    assert "il più comodo" in testo


def test_una_procedura_sola_non_si_numera():
    testo = presentazione.corpo({"livello_evidenza": 1, "procedure": [PROCEDURA_ISOLA]})
    assert "1. " not in testo and "Puoi fare in" not in testo


def test_la_nota_della_procedura_si_legge():
    """"Senza prenotazione è abbandono di rifiuti" è la cosa che evita una multa: non è
    un dettaglio da nascondere in un expander."""
    testo = presentazione.corpo({"livello_evidenza": 1, "procedure": [PROCEDURA_RITIRO]})
    assert "abbandono di rifiuti" in testo


def test_la_raccolta_ordinaria_da_sola_non_si_scrive():
    """È il canale della maggioranza delle risposte: tre righe uguali sotto ogni oggetto
    sono la definizione di rumore, e tutti sanno cos'è un cassonetto."""
    ordinaria = {"canale": "raccolta_ordinaria", "titolo": "Lo butti da casa",
                 "passi": ["Mettilo nel sacco del colore giusto"], "sforzo": 1}
    assert presentazione.corpo({"livello_evidenza": 1, "procedure": [ordinaria]}) == ""
    due = presentazione.corpo({"livello_evidenza": 1, "procedure": [ordinaria, PROCEDURA_ISOLA]})
    assert "Lo butti da casa" in due, "accanto a un altro canale il confronto serve"


def test_senza_procedure_il_messaggio_e_vuoto():
    """La risposta normale è il titolo e basta: nel corpo non resta niente da dire."""
    assert presentazione.corpo({"livello_evidenza": 1,
                                "tipo_corrispondenza": "stesso_oggetto"}) == ""


def test_il_livello_3_dice_dove_chiedere_invece_di_non_so():
    """Chi ha l'oggetto in mano deve comunque buttarlo da qualche parte: indicare il centro
    di raccolta non è indovinare la destinazione, è dire dove si chiede."""
    testo = presentazione.corpo({"livello_evidenza": 3, "ripiego": PROCEDURA_ISOLA})
    assert "che il dizionario non elenca" in testo
    assert "Porta un documento" in testo


def test_il_livello_3_senza_ripiego_resta_la_frase_di_prima():
    testo = presentazione.corpo({"livello_evidenza": 3})
    assert "sito del comune" in testo


# ------------------------------------------------------------ quando chiede, chiede e basta

DOMANDA = {"livello_evidenza": 1, "oggetto": "cartone della pizza",
           "destinazioni": ["organico"], "condizioni": ["unto"],
           "chiarimento": "Per rispondere con certezza devo sapere se l'oggetto è: "
                          "pulito oppure unto?",
           "opzioni": ["pulito", "unto"], "fonte": "amiat_rifiutologo_2025",
           "riferimento": "pagina 8", "procedure": [PROCEDURA_ISOLA],
           "scelto_id": "c1", "candidati": [{"id": "c1", "varianti": [
               {"condizione": "pulito", "destinazioni": ["carta_e_cartone"]},
               {"condizione": "unto", "destinazioni": ["organico"]}]}]}


def test_quando_chiede_il_messaggio_e_solo_la_domanda():
    """Una destinazione sotto la domanda è una risposta che l'assistente non garantisce:
    chi si ferma prima porta via un contenitore che nessuno gli ha promesso."""
    testo = presentazione.messaggio(DOMANDA, ETICHETTE)
    assert testo.endswith("pulito oppure unto?**")
    assert "Cartone della pizza: va in" not in testo, "nessuna destinazione data per buona"
    assert "Lo porti tu" not in testo, "le procedure arrivano col turno dopo"
    assert presentazione.nota_fonte(DOMANDA) == "", "non c'è ancora una fonte da dichiarare"


def test_la_domanda_e_una_riga_sola():
    """Elencare prima i contenitori fra cui cambia la risposta non spiegava la domanda: la
    anticipava, e i pulsanti portano già le stesse parole."""
    assert presentazione.messaggio(DOMANDA, ETICHETTE) == \
        "**" + DOMANDA["chiarimento"] + "**"
    assert "dipende" not in presentazione.messaggio(DOMANDA, ETICHETTE)


def test_le_due_strade_si_imparano_dopo_la_risposta():
    """È lì che servono: una delle due è la risposta per l'oggetto che si ha in mano."""
    risposto = dict(DOMANDA, chiarimento=None)
    assert "Se invece è pulito: **Carta e cartone**." in \
        presentazione.messaggio(risposto, ETICHETTE, risposto="unto")
