# Decisioni di progetto

Formato: decisione, motivazione, stato. Le decisioni si aggiornano, non si cancellano: una decisione superata resta con lo stato "superata da Dn".

| # | Decisione | Motivazione | Stato |
|---|---|---|---|
| D1 | Web app locale in Python, Docker multi-container: frontend Streamlit, backend FastAPI, modello su Ollama | Privacy, esecuzione offline, requisito del progetto | Accettata |
| D2 | Modello base `gemma4:e2b`, `gemma4:e4b` come confronto in valutazione | Laptop con 16 GB di RAM, CPU Ryzen, nessuna GPU dedicata | Accettata |
| D3 | Input: foto di **un solo oggetto**, comune obbligatorio, testo facoltativo | Perimetro dell'agente definito da Stef | Accettata |
| D4 | Domande solo testuali: indicazione provvisoria e richiesta di una foto prima di una risposta sicura | La foto verifica materiale, componenti e stato | Accettata |
| D5 | Comuni: Napoli e Torino | Formati complementari (HTML e PDF); Rifiutologo 2025 granulare e recente | Accettata |
| D6 | Tre livelli di evidenza: 1 voce di dizionario, 2 regola di categoria, 3 nessuna regola del comune | La certezza della risposta dipende da chi ha classificato l'oggetto | Accettata |
| D7 | Mai usare regole di un altro comune | Le regole cambiano tra comuni (es. metalli con vetro a Torino, con plastica a Napoli) | Accettata |
| D8 | Retrieval ibrido: FTS5 a trigrammi + embedding, fusione RRF, filtro per comune prima della ricerca | Il solo semantico confonde oggetti simili con destinazioni diverse (bottiglia/bicchiere di vetro) | Accettata |
| D9 | Il modello sceglie tra candidati reali o risponde "nessuno"; la regola finale arriva sempre da SQL | Contenere le allucinazioni, rendere la valutazione misurabile | Accettata |
| D10 | Ricerca a cascata: voci → regole di categoria → livello 3 | Il livello di evidenza diventa un risultato del flusso, non una stima del modello | Accettata |
| D11 | Nessun catalogo canonico degli oggetti per ora (`oggetto_canonico_id` facoltativo) | Evitare l'entity resolution nel prototipo senza chiudere la porta | Accettata |
| D12 | Un solo file SQLite: FTS5 + vettori | Nessun container database aggiuntivo sul laptop | Accettata |
| D13 | Schema a tre livelli: grezzo, normalizzato, serving | Tracciabilità di ogni dato fino alla fonte | Accettata |
| D14 | Più destinazioni per una voce sono **alternative** (OR), non componenti | Verificato su entrambe le fonti (es. Divani, Armadio) | Accettata |
| D15 | Destinazioni classificate per **canale** e collegate a **flussi** canonici molti-a-molti | Confrontare comuni con raggruppamenti diversi | Accettata |
| D16 | Estrazione Torino deterministica dai marcatori vettoriali, senza LLM | Riproducibile e verificabile; LLM riservato ai casi ambigui | Accettata |
| D17 | Estrattore Napoli senza classi CSS; lista "Puoi inoltre conferire" non usata per l'appartenenza al contenitore | Elementor rigenera le classi; la lista è quasi identica su voci con destinazioni diverse | Accettata |
| D18 | Destinazioni lette dal testo **aggregato** degli elementi, non dai singoli nodi; estrazione a due passaggi con ripiego su vocabolario | Ogni destinazione è un elemento separato: i nodi di testo sono frammentati (`(`, nome, `)`) | Accettata |
| D19 | Scoperta delle voci dalla sitemap XML (584 URL), non dalla paginazione dell'indice | Confermata dalla ricognizione; l'indice mostra 40 voci per pagina | Accettata |
| D20 | Gestione di ambiente e dipendenze con **uv**; codice come package `src/ecoscan`, comandi in `[project.scripts]` | Ambiente riproducibile da `uv.lock`, import assoluti stabili, comandi eseguibili da qualsiasi cartella | Accettata |
| D21 | Percorsi centralizzati in `ecoscan/percorsi.py`, con radice trovata dal `pyproject.toml` e override `ECOSCAN_RADICE` | Evita percorsi relativi alla cartella corrente, che si rompono nei container e nei comandi installati | Accettata |
| D22 | Le descrizioni delle destinazioni non si estraggono dalle pagine voce | Sono identiche su tutte le voci che usano quella destinazione: proprietà della destinazione, da estrarre una volta sola | Accettata |
| D23 | Il campo avvertenza ha priorità sul testo ricavato dallo slug | L'avvertenza conserva accenti e apostrofi, lo slug li perde | Accettata |
| D24 | Le parentesi nei nomi vanno classificate (alias vs condizione), non trattate in modo uniforme | A Napoli indicano sinonimi, esempi o condizioni; a Torino quasi sempre condizioni | Accettata |
| D25 | Le parentesi hanno 4 significati (condizione, sinonimo, esempi, codice materiale) e vengono classificate, non trattate uniformemente | Dai dati: "(40)" è un codice CER-like, "(tetrapak)" un sinonimo, "(in Grandi Quantità)" una condizione | Accettata |
| D26 | Le condizioni si estraggono anche fuori dalle parentesi, ovunque nel nome | "Cartone **pulito** per pizze" (carta) vs "Cartone **unto** per pizze" (organico) | Accettata |
| D27 | Le voci composte si separano solo con criteri prudenti; ogni separazione è marcata `da_revisionare` | La virgola indica composizione, condizione o elenco di contesti: separare sempre produrrebbe alias falsi | Accettata |
| D28 | Deduplicazione insensibile a singolare/plurale; destinazioni diverse = conflitto segnalato, mai risolto in automatico | "Assorbente"/"Assorbenti" sono la stessa voce; una contraddizione della fonte non va nascosta | Accettata |
| D29 | Le voci non reali si scartano per nome | Il dizionario pubblico contiene "Test di esempio" con tre destinazioni | Accettata |

## Questioni aperte

- **Pagine frazione: le regole di esclusione non vengono estratte.** Tutte le regole risultano `ammesso`; la nota "NO" isolata nella pagina del Vetro mostra che la sezione "cosa non differenziare" esiste ma non viene associata agli oggetti. Serve per il livello di evidenza 2.
- Le pagine "Non riciclabile" e "Altri servizi" non producono regole: da verificare se sono davvero prive di elenchi.
- Revisione manuale delle voci marcate `da_revisionare` dal Transform.
- Descrizioni e indirizzi delle destinazioni: 363 voci su 584 richiedono di andare da qualche parte (isole ecologiche, ecopunti), quindi prima o poi serve dire dove.
- Torino: Transform delle condizioni non tra parentesi ("con residui", "unta", "pulito/sporco") e degli alias.
- Estrazione delle regole di categoria: Torino pagine 8-12, Napoli sei pagine frazione e opuscolo PDF.
- Set di test con foto etichettate e metriche (riconoscimento, destinazione per comune, latenza).
