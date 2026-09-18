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
        "oggetto": "cartone della pizza", "materiali": ["cartone"], "confidenza": 0.9}})
    assert "cartone della pizza" in frase and "sicurezza alta" in frase
    assert "bassa" in presentazione.frase_riconoscimento(
        {"riconoscimento": {"oggetto": "x", "confidenza": 0.1}})
    assert presentazione.frase_riconoscimento({"riconoscimento": {"oggetto": ""}}) == ""


def test_la_spiegazione_cita_il_documento_del_comune():
    risposta = {"scelto_id": "oggetto:Torino:cartone-per-pizze", "tipo_corrispondenza": "stesso_oggetto",
                "motivo": "nomina l'oggetto", "candidati": [
                    {"id": "oggetto:Torino:cartone-per-pizze", "nome": "Cartone per pizze",
                     "testo": "Cartone per pizze. Se è unto va in organico.",
                     "destinazioni": ["organico"]},
                    {"id": "oggetto:Torino:cartone", "nome": "Cartone da imballaggio",
                     "destinazioni": ["carta_e_cartone"], "testo": "Cartone da imballaggio."}]}
    testo = presentazione.spiegazione(risposta, ETICHETTE)
    assert "> Cartone per pizze." in testo, "il documento va citato parola per parola"
    assert "è proprio questo oggetto" in testo
    assert "Cartone da imballaggio → Carta e cartone" in testo, "le scartate vanno mostrate"


def test_le_varianti_restano_visibili_dopo_la_scelta():
    """Vedere il ramo non scelto insegna la regola per la volta dopo."""
    testo = presentazione.corpo({"livello_evidenza": 1, "condizioni": ["unto"],
                                 "scelto_id": "c1", "candidati": [{"id": "c1", "varianti": [
                                     {"condizione": "pulito", "destinazioni": ["carta_e_cartone"]},
                                     {"condizione": "unto", "destinazioni": ["organico"]}]}]},
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


def test_il_livello_di_evidenza_e_spiegato_a_parole():
    uno = presentazione.corpo({"livello_evidenza": 1})
    due = presentazione.corpo({"livello_evidenza": 2})
    tre = presentazione.corpo({"livello_evidenza": 3})
    assert "elenca proprio questo oggetto" in uno
    assert "regola generale del contenitore" in due
    assert "non dice nulla" in tre and "centro di raccolta" in tre


def test_il_chiarimento_e_in_evidenza():
    testo = presentazione.corpo({"livello_evidenza": 1, "chiarimento": "È vuota o piena?"})
    assert "**È vuota o piena?**" in testo


def test_avvertenza_e_condizioni_compaiono():
    testo = presentazione.corpo({"livello_evidenza": 1, "condizioni": ["unto"],
                                 "avvertenza": "Svuotala prima"})
    assert "unto" in testo and "Svuotala prima" in testo


def test_la_nota_di_fonte_dice_livello_e_provenienza():
    nota = presentazione.nota_fonte({"livello_evidenza": 2, "fonte": "amiat_rifiutologo_2025",
                                     "riferimento": "pagina 8"})
    assert "regola di categoria" in nota and "pagina 8" in nota


def test_i_candidati_diventano_righe_leggibili():
    righe = presentazione.riassunto_candidati({"scelto_id": "s1", "candidati": [
        {"id": "s1", "livello": 1, "testo": "Scarpe. Se è utilizzabile va in Contenitore Abiti Usati.",
         "destinazioni": ["Contenitore Abiti Usati"], "punteggio": 0.8123}]})
    assert righe[0]["documento"].startswith("Scarpe.")
    assert righe[0]["somiglianza"] == 0.812
    assert righe[0]["scelto"] == "✓"


def test_la_contraddizione_della_fonte_viene_detta():
    """Quando il comune dà destinazioni diverse per lo stesso caso, l'utente deve saperlo."""
    testo = presentazione.corpo({"livello_evidenza": 1, "contraddizione": True})
    assert "destinazioni diverse" in testo


def test_il_frontend_non_importa_il_backend():
    """Il frontend deve parlare solo con le API: se importasse l'agente o il database,
    la valutazione misurerebbe qualcosa di diverso da ciò che usa l'utente."""
    import ast
    from pathlib import Path

    from ecoscan.percorsi import RADICE

    vietati = ("ecoscan.agente", "ecoscan.db")
    for file in (RADICE / "src/ecoscan/frontend").glob("*.py"):
        albero = ast.parse(file.read_text(encoding="utf-8"))
        moduli = [n.module or "" for n in ast.walk(albero) if isinstance(n, ast.ImportFrom)]
        moduli += [a.name for n in ast.walk(albero) if isinstance(n, ast.Import) for a in n.names]
        assert not [m for m in moduli if m.startswith(vietati)], f"{file.name} importa il backend"


def test_una_condizione_di_quantita_non_diventa_uno_stato():
    """"Vale se è: piccole quantità" era la frase sbagliata più visibile."""
    testo = presentazione.corpo({"livello_evidenza": 1, "condizioni": ["piccole quantità"]})
    assert "Vale per piccole quantità." in testo and "Vale se è" not in testo


def test_le_varianti_di_quantita_si_leggono_bene():
    testo = presentazione.corpo({"livello_evidenza": 1, "condizioni": ["grandi quantità"],
                                 "scelto_id": "c1", "candidati": [{"id": "c1", "varianti": [
                                     {"condizione": "piccole quantità", "destinazioni": ["organico"]},
                                     {"condizione": "grandi quantità",
                                      "destinazioni": ["carta_e_cartone"]}]}]}, ETICHETTE)
    assert "per piccole quantità → Organico" in testo
    assert "**per grandi quantità → Carta e cartone** ✓" in testo
