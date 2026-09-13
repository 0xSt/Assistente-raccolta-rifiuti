"""Controlli che impediscono alla documentazione di restare indietro rispetto al codice.

Non verificano che il testo sia *giusto* — quello resta un lavoro umano — ma che le parti
meccanicamente verificabili siano coerenti. Un test che fallisce è più efficace di un
promemoria: costringe ad aggiornare il diario prima di chiudere una modifica.
"""
import re
import tomllib

import pytest

from ecoscan.percorsi import RADICE

DOCS = RADICE / "docs"
DIARIO = DOCS / "diario.md"
GLOSSARIO = DOCS / "glossario.md"
README = RADICE / "README.md"


@pytest.fixture(scope="module")
def versione():
    return tomllib.loads((RADICE / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


@pytest.fixture(scope="module")
def comandi():
    dati = tomllib.loads((RADICE / "pyproject.toml").read_text(encoding="utf-8"))
    return set(dati["project"]["scripts"])


def test_la_versione_ha_una_voce_nel_diario(versione):
    """Ogni versione deve comparire nella cronologia: è ciò che tiene il diario aggiornato."""
    testo = DIARIO.read_text(encoding="utf-8")
    assert f"### v{versione}" in testo, (
        f"la versione {versione} non ha una voce in docs/diario.md: "
        "aggiungila alla cronologia prima di chiudere la modifica")


def test_lo_stato_del_progetto_cita_la_versione_corrente(versione):
    for file in (DIARIO, README):
        assert f"v{versione}" in file.read_text(encoding="utf-8"), (
            f"{file.name} non cita la versione {versione}: aggiorna la sezione di stato")


def test_ogni_comando_e_documentato(comandi):
    testo = README.read_text(encoding="utf-8")
    mancanti = sorted(c for c in comandi if c not in testo)
    assert not mancanti, f"comandi non documentati nel README: {mancanti}"


def test_i_moduli_etl_sono_citati_da_qualche_documento():
    """Un modulo nuovo deve essere nominato almeno una volta: se non lo è, o è di troppo
    o la documentazione non è stata aggiornata."""
    testo = "\n".join(f.read_text(encoding="utf-8") for f in [*DOCS.glob("*.md"), README])
    moduli = {f.stem for f in (RADICE / "src/ecoscan/etl").glob("*.py") if f.stem != "__init__"}
    mancanti = sorted(m for m in moduli if m not in testo)
    assert not mancanti, f"moduli mai citati nella documentazione: {mancanti}"


def test_le_decisioni_sono_numerate_senza_buchi_ne_doppioni():
    numeri = re.findall(r"^\| D(\d+)(b?) \|", DIARIO.read_text(encoding="utf-8"), re.MULTILINE)
    etichette = [n + suffisso for n, suffisso in numeri]
    assert len(etichette) == len(set(etichette)), "decisioni duplicate nel diario"
    principali = sorted({int(n) for n, _ in numeri})
    assert principali == list(range(1, max(principali) + 1)), (
        f"numerazione delle decisioni con buchi: manca {set(range(1, max(principali) + 1)) - set(principali)}")


def test_ogni_decisione_ha_uno_stato_valido():
    righe = re.findall(r"^\| D\d+b? \|.*$", DIARIO.read_text(encoding="utf-8"), re.MULTILINE)
    ammessi = ("Accettata", "Rimandata", "Superata")
    senza = [r for r in righe if not any(a in r for a in ammessi)]
    assert not senza, f"decisioni senza stato valido: {senza}"


def test_il_glossario_copre_i_termini_ricorrenti():
    glossario = GLOSSARIO.read_text(encoding="utf-8")
    essenziali = ["ETL", "Livello grezzo", "Livello normalizzato", "Conflitto", "Slug",
                  "Condizione", "Alias", "Livello di evidenza", "Ricerca ibrida", "uv"]
    mancanti = [t for t in essenziali if f"**{t}**" not in glossario]
    assert not mancanti, f"termini assenti dal glossario: {mancanti}"
