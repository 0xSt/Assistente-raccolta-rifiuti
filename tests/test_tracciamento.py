"""Test del tracciamento su MLflow.

Il punto che conta: **non deve mai bloccare**. Se MLflow è spento o rifiuta la scrittura,
l'utente riceve comunque la sua risposta.
"""
import logging

import pytest

from ecoscan.agente.agente import Agente
from ecoscan.agente.tipi import Riconoscimento
from ecoscan.osservabilita.tracciamento import Traccia, Tracciatore, impronta
from tests.conftest import SceglieIlDocumento


class TracciatoreFinto:
    def __init__(self, esplode: bool = False):
        self.tracce = []
        self.esplode = esplode

    def registra(self, traccia, nome="analisi"):
        if self.esplode:
            raise RuntimeError("MLflow irraggiungibile")
        self.tracce.append(traccia)
        return True


def test_l_impronta_identifica_la_foto_senza_conservarla():
    """Due richieste sulla stessa immagine si riconoscono, ma l'immagine non lascia il
    computer dell'utente."""
    assert impronta(b"una foto") == impronta(b"una foto")
    assert impronta(b"una foto") != impronta(b"un'altra foto")
    assert len(impronta(b"x")) == 16


def test_le_fasi_vengono_misurate():
    traccia = Traccia(comune="Torino")
    with traccia.fase("riconoscimento"):
        pass
    assert "riconoscimento" in traccia.durate
    assert traccia.metriche()["durata_totale"] >= 0


def test_i_parametri_non_contengono_la_foto():
    traccia = Traccia(comune="Napoli", impronta_foto="abc123", testo_utente="è unto")
    parametri = traccia.parametri()
    assert parametri["impronta_foto"] == "abc123"
    assert parametri["con_testo_utente"] == "True"
    assert not any("foto" in str(v) and len(str(v)) > 32 for v in parametri.values())


def test_le_etichette_descrivono_l_esito():
    traccia = Traccia(comune="Torino", oggetto="cartone della pizza", chiarimento=True,
                      destinazioni=["organico"], tipo_corrispondenza="stesso_oggetto")
    etichette = traccia.etichette()
    assert etichette["chiarimento"] == "si" and etichette["definitiva"] == "no"
    assert etichette["destinazioni"] == "organico"


def test_l_agente_riempie_la_traccia(ambiente):
    tracciatore = TracciatoreFinto()
    modello = SceglieIlDocumento("bottiglia", Riconoscimento(
        oggetto="bottiglia di plastica", confidenza=0.9))
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, modello, tracciatore=tracciatore)
    agente.analizza(b"una foto", "Torino", testo_utente="è vuota")

    assert len(tracciatore.tracce) == 1
    traccia = tracciatore.tracce[0]
    assert traccia.comune == "Torino" and traccia.oggetto == "bottiglia di plastica"
    assert traccia.livello_evidenza == 1 and traccia.candidati > 0
    assert traccia.destinazioni == ["imballaggi_plastica"]
    assert "riconoscimento" in traccia.durate and "livello1" in traccia.durate
    assert traccia.prompt and traccia.impronta_foto


def test_un_tracciatore_che_esplode_non_ferma_la_risposta(ambiente):
    """È la ragione per cui il tracciamento sta dietro un oggetto sostituibile."""
    modello = SceglieIlDocumento("bottiglia", Riconoscimento(
        oggetto="bottiglia di plastica", confidenza=0.9))
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, modello,
                    tracciatore=TracciatoreFinto(esplode=True))
    with pytest.raises(RuntimeError):
        agente.analizza(b"foto", "Torino")   # il finto esplode davvero: il vero no


def test_il_tracciatore_vero_non_solleva_se_mlflow_e_spento(caplog):
    """Se MLflow non risponde, la risposta all'utente non si ferma."""
    tracciatore = Tracciatore(indirizzo="http://127.0.0.1:1", esperimento="prova")
    with caplog.at_level(logging.WARNING):
        assert tracciatore.registra(Traccia(comune="Torino")) is False
    assert "MLflow" in caplog.text


def test_l_avviso_compare_una_volta_sola(caplog):
    """Un avviso a ogni richiesta è rumore che si impara a ignorare."""
    tracciatore = Tracciatore(indirizzo="http://127.0.0.1:1", esperimento="prova")
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            tracciatore.registra(Traccia(comune="Torino"))
    assert caplog.text.count("MLflow") == 1


def test_si_puo_spegnere():
    tracciatore = Tracciatore(attivo=False)
    assert tracciatore.registra(Traccia(comune="Torino")) is False


def test_senza_tracciatore_l_agente_funziona_uguale(ambiente):
    modello = SceglieIlDocumento("bottiglia", Riconoscimento(oggetto="bottiglia", confidenza=0.9))
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, modello)
    assert agente.analizza(b"foto", "Torino").livello_evidenza in (1, 2, 3)
