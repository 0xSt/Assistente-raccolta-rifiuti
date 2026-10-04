# EcoScan Local

Assistente per la raccolta differenziata che gira **interamente in locale**.

Si fotografa un oggetto (o se ne scrive il nome), si indica il comune, e l'app risponde in
quale contenitore conferirlo citando la fonte ufficiale da cui proviene la regola. Quando
la destinazione dipende da una condizione dell'oggetto che non è stata dichiarata, il sistema la chiede.

Le regole sono estratte da fonti pubblicate dai gestori del servizio e indicizzate in un vector database
come documenti ricercabili.

Comuni del prototipo: **Napoli** e **Torino**.

---

## Prerequisiti

- [uv](https://docs.astral.sh/uv/) — scarica Python e le dipendenze da sé, non serve creare
  o attivare un virtualenv
- [Ollama](https://ollama.com/) in esecuzione sull'host
- Docker, per Qdrant e MLflow

## Esecuzione in locale

```bash
# 1. ambiente e configurazione
uv sync
cp .env.example .env            # su Windows: copy .env.example .env

# 2. modelli (una volta sola, ~3 GB)
ollama pull gemma3:4b           # riconoscimento dalle fotografie
ollama pull embeddinggemma      # vettori per la ricerca semantica

# 3. servizi di supporto
docker compose up -d qdrant mlflow
                                # Qdrant: http://localhost:6333/dashboard
                                # MLflow: http://localhost:5000

# 4. Extraction-Transform-Load pipeline: normalizza, carica nel relazionale, indicizza su Qdrant
uv run ecoscan-etl

# 5. applicazione
uv run ecoscan-api              # backend:   http://localhost:8000/docs
uv run ecoscan-frontend         # interfaccia: http://localhost:8501
```

Il passo 4 parte dai dati grezzi già versionati nel repository e dura pochi secondi. Per
riscaricare le fonti dai siti dei gestori serve `uv run ecoscan-etl --da estrazione`.

### Tutto in container

```bash
docker compose up -d                       # http://localhost:8501, Ollama resta sull'host
docker compose --profile completo up -d    # con anche Ollama in un container
```

## Altri comandi

Ogni comando accetta `--help`. I percorsi sono relativi alla radice del progetto, quindi
funzionano da qualsiasi cartella.

| Comando | Cosa fa |
|---|---|
| `ecoscan-analizza` | Prova l'agente da riga di comando, su una foto o su un nome |
| `ecoscan-valuta` | Valutazione su 141 casi: recupero, scelta, diagnosi, metriche |
| `ecoscan-valuta-foto` | Valutazione end-to-end dalle fotografie: costo della visione e tempi |
| `ecoscan-campiona` | Estrae voci dal database da cui scrivere nuovi casi di valutazione |
| `ecoscan-prompt` | Elenca i prompt con versione e impronta, e li pubblica su MLflow |
| `ecoscan-vettorizza` | Indicizza i documenti su Qdrant (incluso in `ecoscan-etl`) |

Le singole fasi della catena dati, se serve eseguirne una sola: `ecoscan-napoli` e
`ecoscan-torino` (estrazione dalle fonti), `ecoscan-transform` (normalizzazione delle
voci), `ecoscan-regole` (regole di categoria), `ecoscan-carica` (database relazionale).


## Dashboard valutazione in MLflow

<img width="1572" height="792" alt="image" src="https://github.com/user-attachments/assets/c8a1b757-4c15-4e08-b605-e8d3944a2b9d" />


```

