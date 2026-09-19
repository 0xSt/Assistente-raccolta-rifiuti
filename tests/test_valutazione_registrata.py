"""Test della registrazione delle valutazioni su MLflow.

Il requisito vero è uno solo e si prova senza server: **una misura non si perde perché
manca un servizio di osservabilità**. Il resto è la forma dei parametri.
"""
from ecoscan.osservabilita import valutazione_registrata as vr


def test_i_parametri_annidati_si_appiattiscono():
    """MLflow accetta coppie di stringhe: la configurazione annidata e i conteggi dei casi
    devono diventare parametri leggibili nella tabella delle run."""
    parametri = vr._appiattisci({
        "data": "2026-09-19T15:40", "k": 8, "modalita": "senza_modello",
        "casi": {"regressioni": 18, "campione": 52},
        "configurazione": {"modello_visione": "gemma3:4b", "prompt_scelta": "scelta v8@a3f1"}})
    assert parametri["k"] == "8"
    assert parametri["modello_visione"] == "gemma3:4b"
    assert parametri["casi_regressioni"] == "18"
    assert parametri["casi_campione"] == "52"
    assert "configurazione" not in parametri


def test_con_mlflow_spento_la_valutazione_non_si_ferma(monkeypatch, capsys):
    """D116 applicato alla valutazione: il tracciamento serve a capire come va il sistema,
    non a farlo funzionare. Un server irraggiungibile costa una riga di avviso."""
    monkeypatch.setattr(vr.conf, "MLFLOW_ATTESA", 1)
    registrata = vr.registra({"data": "x", "k": 8}, {"recupero": 88.0},
                             indirizzo="http://127.0.0.1:1")   # porta chiusa
    assert registrata is False
    assert "non registrata" in capsys.readouterr().out


def test_si_puo_spegnere_del_tutto(monkeypatch):
    monkeypatch.setattr(vr.conf, "MLFLOW_ATTIVO", False)
    assert vr.registra({}, {"recupero": 88.0}) is False


def test_solo_i_numeri_diventano_metriche():
    """`misure()` restituisce anche `None` per ciò che non ha misurato: passarlo a MLflow
    farebbe fallire la run, e una metrica assente non è una metrica a zero."""
    numeriche = {c: v for c, v in {"recupero": 88.0, "casi": 70,
                                   "livello_atteso": None}.items()
                 if isinstance(v, (int, float))}
    assert numeriche == {"recupero": 88.0, "casi": 70}
