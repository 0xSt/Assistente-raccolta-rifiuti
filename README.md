# EcoScan Local

Assistente per la raccolta differenziata che gira interamente in locale. L'utente fotografa **un oggetto**, indica il **comune** e, se vuole, aggiunge un testo; l'app risponde dove conferirlo, con la fonte ufficiale.

Progetto universitario. Comuni del prototipo: **Napoli** (ASIA) e **Torino** (AMIAT).

## Stato attuale (v0.44.0)

Il quadro completo è in [docs/diario.md](docs/diario.md).

| Componente | Stato |
|---|---|
| Extract Torino (PDF) | 324 voci dall'elenco A-Z + 10 schede di regole |
| Extract Napoli (HTML) | 584 voci dal dizionario + 6 pagine frazione |
| Transform Napoli | 578 voci normalizzate: 0 conflitti, 0 da revisionare |
| Transform Torino | 324 voci normalizzate: 0 conflitti, 0 da revisionare |
| Regole di categoria | 110 normalizzate e collegate alle destinazioni |
| Revisione manuale | 37 decisioni prese (4% delle voci), nessuna aperta |
| Load relazionale | Fatto: comuni, destinazioni, voci, condizioni, alias, regole, decisioni |
| Serving — documenti su Qdrant | Fatto: 996 documenti arricchiti dalla fonte, ricerca semantica, aggancio esatto dei codici |
| Agente (riconoscimento, cascata, scelta, risposta) | Fatto: usabile senza HTTP |
| API FastAPI | Fatto: otto rotte, backend senza stato e di sola lettura |
| Frontend a chat (Streamlit) | Fatto: allegato immagine, chiarimenti a pulsante, riconoscimento visibile e correggibile, citazione della fonte |
| Tracciamento e prompt su MLflow | Fatto: una traccia per turno con foto e retrieval, sessioni, versione dell'app e prompt collegati |
| Docker completo | Fatto: cinque servizi, Ollama sull'host in sviluppo |
| Valutazione | Fatto: 92 casi in tre insiemi (regressioni, campione, assenti), otto metriche, confronto fra esecuzioni, run su MLflow |
| Valutazione sulle foto | Pronta: 20 etichette scritte, le foto sono da scattare |
| Backend, frontend, modello | Da fare |

## Struttura

```
pyproject.toml       dipendenze, comandi e configurazione di pytest
docker-compose.yml   i cinque servizi: qdrant, mlflow, backend, frontend, ollama
docker/Dockerfile    immagine di backend e frontend
.env.example         modello delle impostazioni; copialo in .env
uv.lock              versioni bloccate (da versionare)
src/ecoscan/
  percorsi.py        radice del progetto e cartelle dati
  etl/               estrattori (grezzo), motore del Transform e profili per comune
  db/                schema.sql e script dimostrativo dello schema
tests/               test di regressione e unitari
data/valutazione/    i casi (tre insiemi) e le etichette delle foto
data/revisioni/      decisioni manuali sulle voci incerte (versionate)
data/riferimento/    destinazioni: canale, colore, flussi di materiale (versionati)
data/grezzo/         output degli estrattori (versionati)
data/sorgenti/       documenti ufficiali scaricati (NON versionati, vedi docs/fonti.md)
data/cache/          cache HTML dell'estrattore Napoli (NON versionata)
docs/                fonti, decisioni, qualità dei dati
```

## Come eseguire

Serve solo [uv](https://docs.astral.sh/uv/): scarica Python e le dipendenze da sé, non serve creare o attivare un virtualenv.

```bash
uv sync                         # prepara l'ambiente da uv.lock

uv run ecoscan-torino           # Torino, dizionario A-Z: metti prima il PDF in data/sorgenti/
uv run ecoscan-torino-regole    # Torino, regole di categoria dalle pagine 8-12
uv run ecoscan-napoli --recon   # Napoli: ricognizione, poche pagine
uv run ecoscan-napoli           # Napoli: estrazione completa (584 voci)
uv run ecoscan-ispeziona        # riepiloga il grezzo di Napoli già estratto
uv run ecoscan-transform        # normalizza le voci dei due comuni -> data/normalizzato/
uv run ecoscan-regole           # normalizza le regole di categoria e le collega alle destinazioni
uv run ecoscan-carica           # ricostruisce data/ecoscan.db dai file normalizzati
uv run ecoscan-carica --verifica # solo i controlli di coerenza, senza scrivere
uv run ecoscan-documenti        # mostra i documenti da indicizzare (per leggerli)

ollama pull embeddinggemma      # una volta sola, serve per i vettori
docker compose up -d qdrant mlflow   # solo i servizi di supporto, per sviluppare
                                # Qdrant:  http://localhost:6333/dashboard
                                # MLflow:  http://localhost:5000
uv run ecoscan-vettorizza       # indicizza i documenti su Qdrant
uv run ecoscan-vettorizza --verifica   # controlla che l'indicizzazione sia corretta
uv run ecoscan-nomi             # elenca i nomi rimasti sgrammaticati dopo la normalizzazione
uv run ecoscan-valuta --senza-modello  # il tetto: recall@k sui casi, senza Ollama (secondi)
uv run ecoscan-valuta           # recupero + scelta; --salva / --confronta per due esecuzioni
uv run ecoscan-campiona         # estrae voci dal database da cui scrivere nuovi casi
uv run ecoscan-valuta-foto      # end-to-end dalle foto: costo della visione e tempi su CPU
uv run ecoscan-prompt           # elenca i prompt con versione e impronta
uv run ecoscan-prompt --pubblica   # registra su MLflow quelli nuovi o modificati

uv run ecoscan-api              # backend: http://localhost:8000/docs
uv run ecoscan-frontend         # interfaccia a chat: http://localhost:8501

# oppure tutto in container (Ollama resta sull'host):
docker compose up -d            # http://localhost:8501
docker compose --profile completo up -d    # con anche Ollama in un container
uv run ecoscan-vettorizza --cerca "contenitore del latte" --comune Napoli  # prova la ricerca

ollama pull gemma3:4b           # modello multimodale (~3 GB), vedi D79 nel diario
uv run ecoscan-analizza --foto foto/bottiglia.jpg --comune Napoli
uv run ecoscan-analizza --oggetto "bottiglia di vetro" --comune Torino   # senza foto
uv run ecoscan-analizza --foto foto/x.jpg --descrivi    # descrizione libera della foto
uv run ecoscan-analizza --diagnostica                   # il canale immagine funziona?
uv run ecoscan-analizza --foto foto/x.jpg --scalini     # la stessa foto a misure decrescenti

uv run pytest                   # i test Torino si saltano se il PDF non è presente
uv run ruff check src tests     # anche dentro pytest, come test_lint.py
uv run ecoscan-demo             # carica i dati nello schema ed esegue interrogazioni di esempio
```

La prima estrazione di Napoli scarica 584 pagine con una pausa di 1,5 secondi fra una e
l'altra, quindi dura circa **15 minuti**; stampa l'avanzamento ogni 25 voci. Le esecuzioni
successive leggono da `data/cache/` e durano pochi secondi. Due conseguenze pratiche:
la cache non va cancellata senza motivo, e conviene **versionare il grezzo prodotto**
(`data/grezzo/napoli/`), così chi parte da un clone pulito non riscarica nulla.

Ogni comando accetta `--help`. I percorsi sono relativi alla radice del progetto, quindi funzionano da qualsiasi cartella; `ECOSCAN_RADICE` permette di forzarla (utile nei container).

### Aggiungere dipendenze e file

```bash
uv add <pacchetto>              # dipendenza di esecuzione (aggiorna pyproject.toml e uv.lock)
uv add --dev <pacchetto>        # dipendenza solo di sviluppo
```

I nuovi moduli vanno in `src/ecoscan/`; per renderli eseguibili basta aggiungere una riga in `[project.scripts]` che punti a una funzione `main()`.

## Configurazione

Le impostazioni stanno nel file `.env` alla radice del progetto. Non è versionato: si crea
dal modello all'inizio, una volta sola.

```
copy .env.example .env       (prompt dei comandi)
cp .env.example .env         (bash)
```

Dentro trovi dove sta Qdrant, l'endpoint di Ollama, il modello di embedding e la dimensione
dei lotti. Le variabili d'ambiente vere, se impostate a un valore non vuoto, hanno la precedenza sul
file: serve a Docker per sovrascrivere un valore senza modificare nulla su disco.

Ogni comando che le usa stampa in testa le impostazioni in uso, così si vede subito se
Qdrant sta in modalità `server` o `in-process`.

## Mappa dei moduli

| Modulo | Cosa fa |
|---|---|
| `etl/extract_torino.py` | Legge l'elenco A-Z del Rifiutologo: destinazioni dai marcatori vettoriali |
| `etl/extract_torino_regole.py` | Legge le schede per frazione (pagine 8-12): ammessi ed esclusi |
| `etl/extract_napoli.py` | Scarica e legge il dizionario ASIA e le pagine frazione |
| `etl/napoli_qualita.py` | Pulizia dei testi e rilevamento dei difetti delle voci di Napoli |
| `etl/trascrizioni.py` | Dati leggibili solo a occhio (testo dentro immagini) e assenze verificate |
| `etl/ispeziona_napoli.py` | Riepilogo del grezzo di Napoli, senza riscaricare nulla |
| `etl/transform_comune.py` | Motore del Transform: condizioni, alias, deduplicazione |
| `etl/transform_napoli.py`, `etl/transform_torino.py` | Regole specifiche di ciascun comune (`Profilo`) |
| `etl/revisioni.py` | Decisioni manuali, applicate a ogni riesecuzione |
| `etl/esegui_transform.py` | Comando che mette insieme Transform, profili e revisioni |
| `etl/normalizza_regole.py` | Collega le regole di categoria alle destinazioni dei comuni |
| `agente/tipi.py` | Riconoscimento, candidato, scelta, risposta |
| `agente/modelli.py` | Modello di visione: interfaccia e implementazione Ollama |
| `agente/recupero.py` | L'interfaccia `Recupero` e `RecuperoQdrant`: candidati per livello di evidenza; scelta della variante |
| `materiali.py` | Famiglie di materiali e quando due si escludono: un documento di un altro materiale non è la risposta |
| `condizioni.py` | Natura di una condizione (stato, quantità, utenza): come si scrive e che domanda fa |
| `agente/agente.py` | Orchestrazione: riconoscimento → cascata → scelta → risposta |
| `agente/prova.py` | Comando per provare l'agente su una foto, con i tempi per fase |
| `agente/diagnostica.py` | Verifica del canale immagine con un'immagine dal contenuto noto |
| `api/app.py` | Rotte FastAPI per area: stato, agente (analizza, domanda, continua, correggi), ricerca |
| `api/risorse.py` | Connessioni e agente condivisi, database in sola lettura |
| `api/schemi.py` | Forma pubblica di ingressi e uscite (Pydantic) |
| `osservabilita/tracciamento.py` | Tracce delle conversazioni su MLflow: turni, retrieval, foto, versione dell'app; mai bloccanti |
| `osservabilita/prompt_registrati.py` | Pubblicazione idempotente dei prompt nel registro di MLflow |
| `frontend/app.py` | Interfaccia a chat in Streamlit, con allegato immagine |
| `frontend/cliente.py` | Unico punto di contatto col backend |
| `frontend/presentazione.py` | Da risposta dell'API a messaggio leggibile |
| `agente/immagini.py` | Ridimensionamento e ricodifica delle foto prima dell'invio |
| `prompt/` | I prompt come file versionati, con versione e impronta |
| `percorsi.py` | Radice del progetto, cartelle dati, caricamento del `.env` |
| `configurazione.py` | Impostazioni lette dal `.env`, con i valori predefiniti |
| `db/schema.sql` | Schema del livello relazionale |
| `db/carica.py` | Load: ricostruisce il database dai file normalizzati |
| `db/vettorizza.py` | Indicizzazione dei documenti su Qdrant e ricerca semantica |
| `db/documenti.py` | Costruzione dei documenti da indicizzare: oggetto, regola, destinazione |
| `valutazione/casi.py` | I tre insiemi di casi: cos'è un caso, come si legge e si scrive |
| `valutazione/campiona.py` | Estrazione stratificata di voci dal database (`ecoscan-campiona`) |
| `valutazione/esegui.py` | Recupero, scelta, diagnosi e confronto (`ecoscan-valuta`) |
| `valutazione/foto.py` | Valutazione end-to-end sulle foto e tempi (`ecoscan-valuta-foto`) |
| `osservabilita/valutazione_registrata.py` | Ogni esecuzione della valutazione come run di MLflow |

## Documentazione

- **[docs/architettura.md](docs/architettura.md)**: come è fatto il sistema, come sono legati i file, e perché. Il documento da cui partire per orientarsi nel codice.
- **[docs/diario.md](docs/diario.md)**: il file da leggere per primo. Stato del progetto, decisioni prese e perché, questioni aperte, annotazioni e cronologia delle modifiche.
- [docs/glossario.md](docs/glossario.md): significato dei termini usati nel progetto, in particolare quelli dell'ETL
- [docs/fonti.md](docs/fonti.md): link e documenti da cui provengono i dati
- [docs/qualita_dati.md](docs/qualita_dati.md): catalogo dei difetti di ciascuna fonte
- [docs/valutazione.md](docs/valutazione.md): cosa si misura, con quali metriche e su quali dati

Diario e glossario si tengono aggiornati man mano: il diario a ogni modifica sostanziale o decisione, il glossario quando entra in gioco un termine nuovo.

Non è affidato alla memoria: `tests/test_documentazione.py` fallisce se la versione corrente non ha una voce nella cronologia del diario, se un comando o un modulo non è documentato, se la numerazione delle decisioni ha buchi o doppioni, o se manca un termine essenziale dal glossario.
