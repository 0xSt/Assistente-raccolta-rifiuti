"""Test del docker-compose.

Non avviano container: verificano che il file dica quello che intendiamo dicesse. Un
indirizzo sbagliato in un servizio si scopre altrimenti solo alzando tutto, e a quel punto
l'errore sembra dell'applicazione.
"""
import pytest
import yaml

from ecoscan.percorsi import RADICE

COMPOSE = RADICE / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_i_servizi_attesi_ci_sono(compose):
    assert set(compose["services"]) == {"qdrant", "mlflow", "backend", "frontend", "ollama"}


def test_il_frontend_conosce_solo_il_backend(compose):
    """Se il frontend avesse gli indirizzi di Qdrant o Ollama, prima o poi qualcuno li
    userebbe, e la valutazione misurerebbe un percorso diverso da quello dell'utente."""
    ambiente = compose["services"]["frontend"]["environment"]
    assert ambiente == {"ECOSCAN_API": "http://backend:8000/api/v1"}


def test_il_backend_punta_ai_servizi_giusti(compose):
    ambiente = compose["services"]["backend"]["environment"]
    assert ambiente["ECOSCAN_QDRANT"] == "http://qdrant:6333"
    assert ambiente["ECOSCAN_MLFLOW"] == "http://mlflow:5000"
    # Ollama sta sull'host durante lo sviluppo
    assert "host.docker.internal" in ambiente["ECOSCAN_OLLAMA"]
    assert "host.docker.internal" in ambiente["ECOSCAN_OLLAMA_CHAT"]


def test_il_database_e_montato_in_sola_lettura(compose):
    """L'ETL resta un lavoro da riga di comando: il servizio che risponde non scrive."""
    volumi = compose["services"]["backend"]["volumes"]
    assert any(v.endswith(":ro") and "/app/data" in v for v in volumi)


def test_il_frontend_aspetta_un_backend_pronto(compose):
    """`depends_on` da solo aspetta che il servizio sia partito, non che risponda."""
    dipendenze = compose["services"]["frontend"]["depends_on"]
    assert dipendenze["backend"]["condition"] == "service_healthy"
    assert "healthcheck" in compose["services"]["backend"]


def test_ollama_e_sotto_profilo(compose):
    """In sviluppo il modello sta sull'host: è già scaricato e resta caricato in memoria."""
    assert compose["services"]["ollama"]["profiles"] == ["completo"]
    for servizio in ("qdrant", "mlflow", "backend", "frontend"):
        assert "profiles" not in compose["services"][servizio]


def test_i_dati_che_devono_sopravvivere_stanno_su_volume(compose):
    assert set(compose["volumes"]) == {"qdrant_dati", "mlflow_dati", "ollama_modelli"}


def test_le_immagini_sono_fissate_a_una_versione(compose):
    """"latest" rende l'ambiente irriproducibile: fra un mese non è più lo stesso."""
    for nome, servizio in compose["services"].items():
        if immagine := servizio.get("image"):
            assert ":" in immagine or immagine == "ecoscan-local", nome
            assert not immagine.endswith(":latest"), nome


def test_il_dockerfile_esiste_e_usa_le_versioni_bloccate():
    testo = (RADICE / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen" in testo, "senza --frozen le versioni non sono quelle provate"
    assert "COPY pyproject.toml uv.lock" in testo


def test_il_dockerignore_esclude_i_dati_pesanti():
    righe = (RADICE / ".dockerignore").read_text(encoding="utf-8").split()
    for pesante in ("data/cache", "data/sorgenti", ".venv", ".git"):
        assert pesante in righe


def test_il_dockerfile_copia_i_file_dichiarati_nel_pyproject():
    """`readme = "README.md"` nel pyproject fa fallire la costruzione del pacchetto se il
    file non è nell'immagine, con un errore che non nomina il Dockerfile."""
    import tomllib

    dati = tomllib.loads((RADICE / "pyproject.toml").read_text(encoding="utf-8"))
    dockerfile = (RADICE / "docker" / "Dockerfile").read_text(encoding="utf-8")

    if readme := dati["project"].get("readme"):
        assert readme in dockerfile, f"{readme} è dichiarato nel pyproject ma non copiato"
    for pacchetto in dati.get("tool", {}).get("hatch", {}).get(
            "build", {}).get("targets", {}).get("wheel", {}).get("packages", []):
        cartella = pacchetto.split("/")[0]
        assert f"COPY {cartella}" in dockerfile, f"{pacchetto} non è copiato nell'immagine"


def test_il_dockerignore_non_esclude_i_file_necessari():
    """`.dockerignore` e il Dockerfile devono essere d'accordo: un file escluso lì non
    arriva, per quante COPY si scrivano."""
    import tomllib

    dati = tomllib.loads((RADICE / "pyproject.toml").read_text(encoding="utf-8"))
    escluse = {r.strip() for r in (RADICE / ".dockerignore").read_text(encoding="utf-8").splitlines()}
    assert dati["project"].get("readme", "README.md") not in escluse
    assert "src" not in escluse
