"""Il linter come test.

Import morti, variabili inutilizzate e parametri che nessuno passa si accumulano in silenzio:
finché nessuno li guarda, il codice sembra funzionare e intanto diventa più difficile da
leggere. Ruff li trova in un secondo, quindi vale la pena chiederglielo a ogni `pytest`
invece di ricordarsene ogni tanto.

La configurazione sta nel `pyproject.toml`, non qui: questo test la esegue, non la decide.
"""
import shutil
import subprocess

import pytest

from ecoscan.percorsi import RADICE


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff non installato")
def test_il_codice_passa_il_linter():
    esito = subprocess.run(["ruff", "check", "src", "tests"], cwd=RADICE,
                           capture_output=True, text=True, check=False)
    assert esito.returncode == 0, esito.stdout or esito.stderr
