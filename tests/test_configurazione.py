"""Test della configurazione da file `.env`.

Il punto che conta: le variabili d'ambiente vere devono avere la precedenza sul file,
altrimenti un container non potrebbe sovrascrivere un valore senza modificare il disco.
"""
import subprocess
import sys

import pytest

from ecoscan import configurazione as conf
from ecoscan.percorsi import RADICE

CODICE = "from ecoscan import configurazione as c; import json; print(json.dumps(c.riepilogo()))"


def leggi_configurazione(cwd, ambiente=None):
    """Legge la configurazione in un processo separato, con un ambiente ripulito.

    Tutte le ECOSCAN_* ereditate vengono tolte: il test deve dipendere dal file, non da
    come è configurata la macchina di chi lo esegue.
    """
    import json
    import os
    env = {k: v for k, v in os.environ.items() if not k.startswith("ECOSCAN_")}
    env.update(ambiente or {})
    uscita = subprocess.run([sys.executable, "-c", CODICE], cwd=cwd, capture_output=True,
                            text=True, env=env, check=True)
    return json.loads(uscita.stdout)


def test_esiste_il_modello_versionato():
    assert (RADICE / ".env.example").is_file(), "manca il modello di configurazione"


def test_env_example_documenta_tutte_le_variabili_lette():
    testo = (RADICE / ".env.example").read_text(encoding="utf-8")
    lette = {"ECOSCAN_QDRANT", "ECOSCAN_OLLAMA", "ECOSCAN_MODELLO_EMBEDDING", "ECOSCAN_LOTTO_EMBEDDING"}
    mancanti = sorted(v for v in lette if v not in testo)
    assert not mancanti, f"variabili lette dal codice ma assenti da .env.example: {mancanti}"


def test_valori_predefiniti_senza_file(tmp_path):
    """Senza .env il progetto funziona comunque, in modalità in-process."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    letta = leggi_configurazione(tmp_path)
    assert letta["modalita_qdrant"] == "in-process"
    assert letta["modello"] == "embeddinggemma"


def test_il_file_env_viene_letto(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / ".env").write_text("ECOSCAN_QDRANT=http://esempio:6333\nECOSCAN_LOTTO_EMBEDDING=8\n")
    letta = leggi_configurazione(tmp_path)
    assert letta["qdrant"] == "http://esempio:6333" and letta["modalita_qdrant"] == "server"
    assert letta["lotto"] == "8"


def test_l_ambiente_vince_sul_file(tmp_path):
    """Serve a Docker: sovrascrivere un valore senza toccare il file su disco."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / ".env").write_text("ECOSCAN_QDRANT=http://dal-file:6333\n")
    letta = leggi_configurazione(tmp_path, {"ECOSCAN_QDRANT": "http://dall-ambiente:6333"})
    assert letta["qdrant"] == "http://dall-ambiente:6333"


def test_una_variabile_vuota_non_zittisce_il_file(tmp_path):
    """Un `ECOSCAN_X=` vuoto nell'ambiente non deve far ignorare il valore del file."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / ".env").write_text("ECOSCAN_LOTTO_EMBEDDING=8\n")
    letta = leggi_configurazione(tmp_path, {"ECOSCAN_LOTTO_EMBEDDING": "   "})
    assert letta["lotto"] == "8"


def test_valore_non_numerico_segnalato(monkeypatch):
    monkeypatch.setenv("ECOSCAN_LOTTO_EMBEDDING", "molte")
    with pytest.raises(SystemExit, match="numero intero"):
        conf._intero("ECOSCAN_LOTTO_EMBEDDING", 32)


def test_riepilogo_mostra_la_modalita():
    assert conf.riepilogo()["modalita_qdrant"] in ("server", "in-process")


def test_il_modello_di_visione_predefinito_e_quello_che_funziona(tmp_path):
    """Gemma 4 dichiara `vision` ma non interpreta le fotografie (D79): il predefinito deve
    restare un modello verificato, altrimenti chi clona il progetto parte da un guasto."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    assert leggi_configurazione(tmp_path)["modello_visione"] == "gemma3:4b"


def test_i_prefissi_degli_embedding_si_possono_spegnere(tmp_path):
    """Servono a confrontare due configurazioni, non a indovinare quale sia giusta."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / ".env").write_text("ECOSCAN_PREFISSI_EMBEDDING=no\n")
    assert leggi_configurazione(tmp_path)["prefissi_embedding"] == "no"
    assert leggi_configurazione(tmp_path.parent / tmp_path.name, {"ECOSCAN_PREFISSI_EMBEDDING": "si"}
                                )["prefissi_embedding"] == "si"
