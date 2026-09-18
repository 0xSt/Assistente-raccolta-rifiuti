"""La radice del progetto deve risolversi anche lanciando i comandi da un'altra cartella."""
import subprocess
import sys
from pathlib import Path

from ecoscan.percorsi import RADICE, SCHEMA_SQL


def test_radice_contiene_pyproject():
    assert (RADICE / "pyproject.toml").is_file()
    assert SCHEMA_SQL.is_file()


def test_radice_indipendente_dalla_cartella(tmp_path):
    codice = "from ecoscan.percorsi import RADICE; print(RADICE)"
    out = subprocess.run([sys.executable, "-c", codice], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert Path(out.stdout.strip()) == RADICE


def test_variabile_ambiente_ha_priorita(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOSCAN_RADICE", str(tmp_path))
    from ecoscan.percorsi import radice_progetto
    assert radice_progetto() == tmp_path.resolve()
