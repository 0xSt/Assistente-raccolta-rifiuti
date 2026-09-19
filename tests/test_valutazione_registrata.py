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


def test_un_server_spento_non_fa_perdere_la_misura(monkeypatch, capsys, tmp_path):
    """La regola che distingue una misura dall'osservabilità: una traccia persa non fa
    danno, una misura persa sì — costa minuti di CPU e non si ripete uguale."""
    monkeypatch.setattr(vr.conf, "MLFLOW_ATTESA", 1)
    registrata = vr.registra({"data": "x", "k": 8}, {"recupero": 88.0},
                             indirizzo="http://127.0.0.1:1",      # porta chiusa
                             ripiego=tmp_path / "locale.db")
    uscita = capsys.readouterr().out
    assert registrata is True
    assert "non raggiungibile" in uscita and "archivio locale" in uscita
    assert (tmp_path / "locale.db").is_file(), "la run doveva finire qui"


def test_l_interruttore_delle_conversazioni_non_spegne_le_misure(monkeypatch, capsys, tmp_path):
    """`ECOSCAN_MLFLOW_ATTIVO` governa le tracce delle conversazioni. Una misura si prende
    una volta sola: l'unico modo di non registrarla è chiederlo con `--senza-mlflow`."""
    monkeypatch.setattr(vr.conf, "MLFLOW_ATTIVO", False)
    monkeypatch.setattr(vr.conf, "MLFLOW_ATTESA", 1)
    assert vr.registra({"data": "x"}, {"recupero": 88.0}, indirizzo="http://127.0.0.1:1",
                       ripiego=tmp_path / "locale.db") is True


def test_se_non_si_puo_scrivere_da_nessuna_parte_il_comando_si_ferma(monkeypatch, tmp_path):
    """Tacere qui sarebbe la cosa peggiore: la misura è persa e chi l'ha lanciata non lo
    saprebbe."""
    import pytest
    monkeypatch.setattr(vr.conf, "MLFLOW_ATTESA", 1)
    # un file al posto di una cartella: la creazione dell'archivio non può riuscire
    ostacolo = tmp_path / "non-e-una-cartella"
    ostacolo.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="NON è stata registrata"):
        vr.registra({"data": "x"}, {"recupero": 88.0}, indirizzo="http://127.0.0.1:1",
                    ripiego=ostacolo / "locale.db")




def test_solo_i_numeri_diventano_metriche():
    """`misure()` restituisce anche `None` per ciò che non ha misurato: passarlo a MLflow
    farebbe fallire la run, e una metrica assente non è una metrica a zero."""
    numeriche = {c: v for c, v in {"recupero": 88.0, "casi": 70,
                                   "livello_atteso": None}.items()
                 if isinstance(v, (int, float))}
    assert numeriche == {"recupero": 88.0, "casi": 70}


def test_i_nomi_delle_metriche_passano_il_vaglio_di_mlflow():
    """MLflow rifiuta la chiocciola, e rifiutando `recall@8` faceva fallire **tutta** la
    scrittura: una sola chiamata, una sola transazione, zero metriche registrate.

    La conversione sta solo al confine: dentro il progetto la metrica si chiama ancora
    `recall@8`, che è il nome con cui si legge in letteratura.
    """
    assert vr.nome_valido("recall@8") == "recall_at_8"
    assert vr.nome_valido("contenitore_corretto") == "contenitore_corretto"
    ammessi = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.: /")
    for chiave in ("recall@1", "recall@4", "recall@8", "copertura", "astensione_corretta",
                   "riconoscimento_p50", "casi_regressioni"):
        assert set(vr.nome_valido(chiave)) <= ammessi, chiave


def test_un_server_irraggiungibile_dice_anche_come_accenderlo(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(vr.conf, "MLFLOW_ATTESA", 1)
    vr.registra({"data": "x"}, {"recupero": 88.0}, indirizzo="http://127.0.0.1:1",
                ripiego=tmp_path / "locale.db")
    uscita = capsys.readouterr().out
    assert "non raggiungibile" in uscita and "docker compose up -d mlflow" in uscita
    assert "mlflow ui --backend-store-uri" in uscita
