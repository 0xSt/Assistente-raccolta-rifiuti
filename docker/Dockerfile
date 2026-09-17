# Un'immagine sola per backend e frontend: cambia solo il comando.
#
# Sono due servizi distinti e restano tali (il frontend parla solo con le API, e un test
# verifica che non importi l'agente né il database), ma per un prototipo costruire due
# immagini quasi identiche costerebbe tempo e spazio senza vantaggi.
FROM python:3.12-slim

# uv gestisce l'ambiente anche qui: le versioni sono quelle di uv.lock, le stesse provate
# in sviluppo. È il motivo per cui il file è versionato.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

# Prima le dipendenze, poi il codice: così una modifica al codice non rifà l'installazione.
# README.md serve perché pyproject.toml lo dichiara come `readme`: senza, la costruzione
# del pacchetto fallisce con un errore che non nomina il Dockerfile.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY data/riferimento ./data/riferimento
COPY data/revisioni ./data/revisioni
RUN uv sync --frozen --no-dev

# I dati veri (database e cache) arrivano da un volume: l'immagine resta leggera e
# l'ETL continua a essere una cosa che si lancia a mano, fuori dai container.
EXPOSE 8000 8501
CMD ["uv", "run", "ecoscan-api", "--host", "0.0.0.0"]
