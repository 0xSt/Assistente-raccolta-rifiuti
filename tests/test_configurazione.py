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
    import json
    import os
    env = {**os.environ, **(ambiente or {})}
    env.pop("ECOSCAN_QDRANT", None) if not (ambiente or {}).get("ECOSCAN_QDRANT") else None
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


def test_valore_non_numerico_segnalato(monkeypatch):
    monkeypatch.setenv("ECOSCAN_LOTTO_EMBEDDING", "molte")
    with pytest.raises(SystemExit, match="numero intero"):
        conf._intero("ECOSCAN_LOTTO_EMBEDDING", 32)


def test_riepilogo_mostra_la_modalita():
    assert conf.riepilogo()["modalita_qdrant"] in ("server", "in-process")
