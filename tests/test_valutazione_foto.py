"""Test della valutazione sulle foto: la scomposizione e i tempi.

Le foto vere non entrano nei test — richiedono Ollama e minuti di CPU. Qui si verifica la
meccanica: che il secondo giro serva a separare la colpa del modello di visione, che i
tempi si riportino come mediana e p90, e che una foto mancante si faccia notare subito.
"""
import json

import pytest

from ecoscan.valutazione import foto as vf
from ecoscan.valutazione.casi import Caso
from ecoscan.valutazione.esegui import Esito


def una_foto(**extra) -> vf.Foto:
    return vf.Foto(file="bottiglia.jpg", comune="Napoli", oggetto="bottiglia di plastica",
                   destinazioni_attese=["Plastica e Metalli"], **extra)


def esito(destinazioni: list[str], caso: Caso) -> Esito:
    return Esito(caso=caso, recuperato=True, destinazioni=destinazioni, posizione=1)


def esito_foto(vista: list[str], vero: list[str] | None, secondi=(40.0, 2.0)) -> vf.EsitoFoto:
    prova = una_foto()
    return vf.EsitoFoto(
        foto=prova, riconosciuto="bottiglia",
        reale=esito(vista, prova.caso),
        ideale=esito(vero, prova.caso) if vero is not None else None,
        secondi_riconoscimento=secondi[0], secondi_risposta=secondi[1])


def test_una_foto_diventa_un_caso_con_le_stesse_metriche():
    """Riusare `Caso` ed `Esito` non è pigrizia: due insiemi di metriche diversi non si
    potrebbero confrontare, e la scomposizione end-to-end sta proprio nel confronto."""
    caso = una_foto().caso
    assert caso.comune == "Napoli"
    assert caso.destinazioni_attese == ["Plastica e Metalli"]
    assert caso.origine == "foto"
    assert caso.riconoscimento.confidenza == 1.0


def test_la_colpa_e_della_visione_solo_se_l_oggetto_vero_avrebbe_funzionato():
    """È la sola domanda per cui il secondo giro esiste: sbagliata dalla foto, giusta
    dall'oggetto dichiarato."""
    assert esito_foto(["Organico"], ["Plastica e Metalli"]).colpa_della_visione is True
    # sbagliata in entrambi i giri: il difetto sta a valle, non nel riconoscimento
    assert esito_foto(["Organico"], ["Organico"]).colpa_della_visione is False
    # giusta in entrambi
    assert esito_foto(["Plastica e Metalli"], ["Plastica e Metalli"]).colpa_della_visione is False


def test_senza_il_secondo_giro_la_colpa_non_si_attribuisce():
    """`--solo-reale` misura ancora la correttezza, ma smette di dire da dove viene
    l'errore: la misura che manca non deve diventare un falso negativo."""
    senza = esito_foto(["Organico"], None)
    assert senza.colpa_della_visione is False
    assert vf.misure_foto([senza])["corrette_dall_oggetto_vero"] is None
    assert vf.misure_foto([senza])["perse_dalla_visione"] is None


def test_il_costo_della_visione_e_la_differenza_fra_i_due_giri():
    esiti = [esito_foto(["Organico"], ["Plastica e Metalli"]),
             esito_foto(["Plastica e Metalli"], ["Plastica e Metalli"])]
    misure = vf.misure_foto(esiti)
    assert misure["corrette_dalla_foto"] == 50.0
    assert misure["corrette_dall_oggetto_vero"] == 100.0
    assert misure["perse_dalla_visione"] == 1


@pytest.mark.parametrize("valori, quantile, atteso", [
    ([1.0], 0.5, 1.0),
    ([1.0, 2.0, 3.0, 100.0], 0.5, 2.0),      # la mediana ignora la coda, la media no
    ([1.0, 2.0, 3.0, 100.0], 0.9, 100.0),
    ([], 0.5, None),
])
def test_i_tempi_si_riportano_come_percentili(valori, quantile, atteso):
    """La media di dieci foto veloci e una lenta descrive una situazione che non è
    capitata a nessuno."""
    assert vf.percentile(valori, quantile) == atteso


def test_i_tempi_delle_due_fasi_si_sommano():
    e = esito_foto(["Plastica e Metalli"], None, secondi=(41.5, 2.25))
    assert e.secondi_totali == 43.75
    misure = vf.misure_foto([e])
    assert misure["riconoscimento_p50"] == 41.5
    assert misure["risposta_p50"] == 2.25


def test_le_etichette_si_leggono_e_i_campi_ignoti_non_rompono(tmp_path):
    percorso = tmp_path / "foto.jsonl"
    percorso.write_text(json.dumps(
        {"file": "a.jpg", "comune": "Torino", "oggetto": "giornale",
         "destinazioni_attese": ["carta_e_cartone"], "domani": 1}) + "\n", encoding="utf-8")
    assert vf.leggi_etichette(percorso)[0].oggetto == "giornale"


def test_una_foto_mancante_si_ferma_subito(tmp_path):
    """Meglio un errore in testa all'esecuzione che venti minuti di CPU e poi un buco."""
    with pytest.raises(SystemExit):
        una_foto().dati(tmp_path)
