# Architettura di EcoScan Local

Come è fatto il sistema, come sono legati i file, e perché. È il documento da leggere per
orientarsi; il **[diario](diario.md)** racconta *quando* e *perché* le cose sono cambiate,
questo dice *com'è adesso*.

Aggiornato alla **v0.49.1**.

---

## 1. Cosa fa, e la regola che tiene tutto insieme

Si fotografa un oggetto da buttare e si riceve dove va, secondo le regole del proprio
comune. Tutto gira in locale: i modelli sono su Ollama, l'indice su Qdrant, i dati su
SQLite.

Una sola regola spiega quasi ogni scelta di progetto:

> **La destinazione viene sempre da un documento del comune. Il modello serve a capire cosa
> c'è nella foto e a scegliere fra documenti reali, mai a dire dove va una cosa.**

Da qui discendono la scelta vincolata (il modello indica un numero in un elenco, non scrive
un nome), il livello di evidenza (quanto è fondata la risposta), il link alla fonte sotto
ogni risposta e il fatto che la variante giusta la scelga il codice e non il modello.

---

## 2. I quattro livelli dei dati

| Livello | Dove | Cosa contiene | Chi lo produce | In git? |
|---|---|---|---|---|
| **Sorgente** | `data/sorgenti/` | I PDF e le pagine originali dei gestori | scaricati a mano | no (tranne le trascrizioni) |
| **Grezzo** | `data/grezzo/` | Copia fedele della fonte: JSONL di Napoli, CSV di Torino | Extract | **sì** |
| **Normalizzato** | `data/normalizzato/` | Voci pulite: nome, condizioni, alias, codice, destinazioni, provenienza | Transform | no |
| **Relazionale** | `data/ecoscan.db` | SQLite: 12 tabelle, la verità strutturata | Carica | no |
| **Indice** | Qdrant | Un documento per oggetto e per regola, con tutto il payload | Documenti + Vettorizza | no |

Solo il grezzo è versionato, insieme alle revisioni manuali (`data/revisioni/`) e ai file di
riferimento (`data/riferimento/`). Tutto il resto si rigenera con i comandi: un `git clone`
basta a ricostruire il database, e serve Ollama solo per l'indice.

---

## 3. La catena ETL

```
   fonti pubbliche (PDF AMIAT, sito ASIA)
            │
            ▼  extract_torino · extract_napoli · extract_torino_regole
      data/grezzo/                                    ← versionato
            │
            ▼  esegui_transform   (transform_comune + un Profilo per comune)
      data/normalizzato/*_voci.jsonl
            │
            ▼  normalizza_regole
      data/normalizzato/regole.jsonl
            │
            ▼  carica              (+ db/schema.sql, data/riferimento/destinazioni.csv)
      data/ecoscan.db
            │
            ▼  documenti           un testo leggibile per oggetto e per regola
            │
            ▼  vettorizza          (+ Ollama per gli embedding)
         Qdrant
```

Comandi, nell'ordine in cui si lanciano dopo un aggiornamento che tocca i dati:

```
uv run ecoscan-transform     uv run ecoscan-carica
uv run ecoscan-regole        uv run ecoscan-carica     # sì, due volte
uv run ecoscan-vettorizza                              # il lungo: richiede Ollama
```

Il doppio `carica` non è un refuso: le regole normalizzate si generano fra i due passaggi.

**Idee portanti di questa catena**

- **Il Transform è un motore unico con profili per comune.** Le regole che cambiano da una
  fonte all'altra (cosa è una condizione, cosa un alias, come si scrive il riferimento)
  stanno in un `Profilo`; il motore è lo stesso. Aggiungere un comune significa scrivere un
  profilo, non un secondo Transform.
- **Le decisioni prese a mano vivono in git** (`data/revisioni/*.csv`) e vengono riapplicate
  a ogni rigenerazione: correggere un dato non è un'operazione che si perde.
- **I documenti sono l'unità che il modello legge.** Un oggetto diventa *un* testo con tutte
  le sue varianti ("Cartone da pizza. Se è pulito va in carta e cartone; se è sporco va in
  organico"), e il payload porta destinazioni, condizioni, avvertenza e fonte. Da lì in poi
  per rispondere non si legge più il relazionale.

---

## 4. Il percorso di una risposta

```
  utente ─▶ frontend/app.py (Streamlit)
                 │
                 ▼ frontend/cliente.py ──HTTP──▶ api/app.py
                                                    │ api/risorse.py  (db · Qdrant · modello · recupero · agente)
                                                    ▼
                                            agente/agente.py
      ┌──────────────────────────────────────────────┴──────────────────────────────┐
      │ 1. riconoscimento   modelli.py → riconosci(foto)    "cosa vedo"             │
      │ 2. recupero         Recupero.candidati(...)         livello 1, poi 2        │
      │    ↳ filtro         materiali.py                    via i materiali estranei│
      │ 3. scelta           modelli.py → scegli(candidati)  un numero, o "nessuno"  │
      │ 4. variante         recupero.scegli_variante(...)   la sceglie il CODICE    │
      └──────────────────────────────────────────────┬──────────────────────────────┘
                                                     ▼
                                   api/schemi.py ─▶ frontend/presentazione.py ─▶ chat
```

**I quattro passaggi, e chi decide cosa**

| # | Passaggio | Lo fa | Nota |
|---|---|---|---|
| 1 | Riconoscimento | il modello | descrive l'oggetto; il prompt gli **vieta** di dire dove va |
| 2 | Recupero | l'indice | prima il dizionario (livello 1), poi le regole di categoria (livello 2) |
| — | Filtro materiali | il codice | un documento di un altro materiale non arriva alla scelta |
| 3 | Scelta vincolata | il modello | sceglie fra documenti reali; se dichiara una corrispondenza debole, il codice la scarta |
| 4 | Variante | il codice | quale ramo vale lo decide ciò che l'utente ha detto; se non basta, si chiede |

**Il livello di evidenza** è il prodotto dell'ordine del passaggio 2, e viaggia fino
all'interfaccia:

| Livello | Significato | Come si legge in chat |
|---|---|---|
| 1 | il comune elenca proprio questo oggetto | "Il comune elenca proprio questo oggetto." |
| 2 | non lo elenca, vale la regola generale del contenitore | "questa è la regola generale del contenitore" |
| 3 | il comune non dice nulla | "Non so dove va questo oggetto." |

**I tre modi di rivolgersi all'agente**, tutti turni della stessa conversazione:

- `analizza` — dalla foto alla risposta;
- `continua` — dopo un chiarimento, riparte dal riconoscimento già fatto (la foto non si
  rilegge: è il passaggio lento);
- `correggi` — l'utente dichiara qual è l'oggetto, con confidenza massima; si rifanno solo
  recupero e scelta.

---

## 5. Mappa dei moduli

### Dati (non girano mai mentre si risponde)

| File | Responsabilità |
|---|---|
| `etl/extract_napoli.py` | Estrae le voci dal dizionario di ASIA (HTML) |
| `etl/extract_torino.py` | Estrae le voci dal Rifiutologo AMIAT (PDF) |
| `etl/extract_torino_regole.py` | Estrae le schede delle regole di categoria di Torino |
| `etl/napoli_qualita.py` | Slug, normalizzazione degli spazi, difetti noti della fonte |
| `etl/ispeziona_napoli.py` | Lettura e riepilogo del grezzo di Napoli |
| `etl/transform_comune.py` | Il motore: da voce grezza a voce normalizzata, passaggio per passaggio |
| `etl/transform_napoli.py` · `etl/transform_torino.py` | I due profili: cosa cambia da una fonte all'altra |
| `etl/esegui_transform.py` | Il comando che applica il motore e scrive il normalizzato |
| `etl/normalizza_regole.py` | Le regole di categoria collegate alle destinazioni |
| `etl/revisioni.py` | Applica le decisioni prese a mano, versionate in git |
| `etl/trascrizioni.py` | Le parti di fonte trascritte a mano, quando l'estrazione non arriva |
| `etl/qualita_nomi.py` | I nomi rimasti sgrammaticati dopo la normalizzazione diventano motivi di revisione |
| `db/schema.sql` | Lo schema relazionale: 12 tabelle |
| `db/carica.py` | Costruisce il database, una funzione per tabella |
| `db/documenti.py` | Costruisce i documenti da indicizzare (oggetto, regola, destinazione) e li arricchisce con dati della fonte: canale, flussi, regole che nominano l'oggetto |
| `db/vettorizza.py` | Indicizza su Qdrant e cerca; parla con Ollama per gli embedding |

### Ragionamento

| File | Responsabilità |
|---|---|
| `agente/agente.py` | Orchestrazione dei quattro passaggi; `Richiesta` tiene insieme cosa si cerca |
| `agente/recupero.py` | L'interfaccia `Recupero` e `RecuperoQdrant`; scelta della variante |
| `agente/modelli.py` | Il modello di visione dietro un protocollo, con l'implementazione Ollama |
| `agente/tipi.py` | `Riconoscimento`, `Candidato`, `Variante`, `Scelta`, `Risposta` |
| `agente/immagini.py` | Ridimensiona e ricodifica le foto prima dell'invio al modello |
| `agente/cache.py` | Decoratore di `ModelloVisione`: la stessa foto non si riconosce due volte |
| `materiali.py` | Famiglie di materiali e quando due si escludono |
| `condizioni.py` | Natura di una condizione (stato, quantità, utenza): come si scrive, che domanda fa |
| `procedure.py` | Come si conferisce a ciascun canale, e l'ordine per sforzo delle alternative |
| `prompt/` | I prompt come file versionati, con versione e impronta sul contenuto |

### Confine HTTP

| File | Responsabilità |
|---|---|
| `api/app.py` | Otto rotte, registrate per area: stato, agente, ricerca |
| `api/schemi.py` | La forma pubblica di ingressi e uscite (Pydantic), separata dai tipi interni |
| `api/risorse.py` | Connessioni e agente costruiti una volta all'avvio; database in sola lettura |

Le rotte: `/salute`, `/comuni`, `/destinazioni`, `/analizza`, `/continua`, `/correggi`,
`/domanda`, `/cerca`.

### Interfaccia

| File | Responsabilità |
|---|---|
| `frontend/app.py` | La chat in Streamlit: allegato o nome scritto, chiarimenti a pulsante, correzione, legenda dei contenitori |
| `frontend/cliente.py` | L'unico punto di contatto col backend |
| `frontend/presentazione.py` | Da risposta dell'API a messaggio leggibile: titolo, corpo, domanda, fonte |

### Osservabilità e diagnostica

| File | Responsabilità |
|---|---|
| `osservabilita/tracciamento.py` | Una traccia MLflow per turno; mai bloccante |
| `osservabilita/prompt_registrati.py` | Pubblica i prompt nel registro, senza creare doppioni |
| `agente/prova.py` | `ecoscan-analizza`: prova l'agente su una foto vera, con i tempi |
| `agente/diagnostica.py` | Verifica il canale immagine con un'immagine dal contenuto noto |
| `osservabilita/valutazione_registrata.py` | Ogni esecuzione della valutazione come run MLflow, in un esperimento suo |
| `valutazione/casi.py` | Cos'è un caso e i tre insiemi (regressioni, campione, assenti) |
| `valutazione/campiona.py` | `ecoscan-campiona`: estrazione stratificata dal database, con seme fisso |
| `valutazione/esegui.py` | `ecoscan-valuta`: recall@k come tetto, diagnosi, confronto fra esecuzioni. Vedi [valutazione.md](valutazione.md) |
| `valutazione/foto.py` | `ecoscan-valuta-foto`: end-to-end dalla foto, costo della visione, tempi su CPU |

### Trasversali

| File | Responsabilità |
|---|---|
| `configurazione.py` | Le impostazioni lette dal `.env`, con i valori predefiniti |
| `percorsi.py` | Radice del progetto, cartelle dati, caricamento del `.env` |

---

## 6. Le regole di dipendenza

Sono ciò che impedisce al sistema di diventare un groviglio. Alcune hanno un test che le
verifica.

| Regola | Perché | Verificata da |
|---|---|---|
| L'ETL non gira mai mentre si risponde | il servizio è di sola lettura: non può corrompere ciò che gli serve | apertura `mode=ro` + test |
| Il frontend non conosce Qdrant, Ollama o il database | altrimenti la valutazione misurerebbe un percorso diverso da quello dell'utente | `test_frontend.py` |
| L'agente non conosce Qdrant | riceve un `Recupero`: la ricerca è sostituibile | `test_agente.py` |
| L'agente non conosce MLflow | riceve un tracciatore; senza, funziona identico | `test_tracciamento.py` |
| `presentazione.py` non conosce Streamlit | prende dizionari, restituisce stringhe: si prova senza interfaccia | — |
| Il backend è senza stato | il contesto viaggia col client; niente sessioni da perdere | `test_api.py` |
| I tipi interni non escono dall'API | `api/schemi.py` traduce: i due lati cambiano indipendentemente | — |

---

## 7. I punti di sostituzione

Dove il sistema è pensato per cambiare senza riscritture:

| Punto | Interfaccia | Oggi | Domani |
|---|---|---|---|
| Ricerca | `Recupero` | `RecuperoQdrant` (semantica + codici esatti) | una ricerca ibrida, senza toccare l'agente |
| Modello di visione | `ModelloVisione` | `ModelloOllama` | un altro modello, o un finto nei test |
| Tracciamento | `Tracciatore` / `TracciatoreNullo` | MLflow | un altro sistema, o nulla |
| Comune | `Profilo` nel Transform | Napoli, Torino | un terzo comune è un profilo in più |
| Risorse | `Risorse` | database e servizi veri | versione finta nei test, senza alzare niente |

---

## 8. Osservabilità

Ogni turno — `analizza`, `continua`, `correggi` — è **una traccia MLflow**:

```
traccia "analizza"                       ← input, output, foto allegata, tag
├── span riconoscimento        (LLM)     ← prompt usato, cosa ha visto il modello
├── span recupero_livello1     (RETRIEVER) ← domande poste, documenti trovati, scarti
├── span scelta_livello1       (LLM)     ← candidati mostrati, numero scelto, motivo
└── (se serve) gli stessi due al livello 2
```

- i turni della stessa conversazione condividono la **sessione**, così si leggono insieme;
- ogni traccia punta a un **LoggedModel** che descrive la configurazione in uso (modelli,
  `k`, soglie, prompt) e alle versioni dei prompt pubblicate nel registro;
- se MLflow non risponde, **l'utente riceve comunque la sua risposta**: il tracciamento
  serve a capire come va il sistema, non a farlo funzionare.

---

## 9. Test

559 test, tutti veloci: i modelli sono finti, Qdrant gira in memoria, nessuna rete.

| Gruppo | Cosa presidia |
|---|---|
| ETL (`test_transform*`, `test_napoli`, `test_torino*`, `test_revisioni`, `test_trascrizioni`) | che la normalizzazione non cambi in silenzio |
| Dati (`test_carica`, `test_documenti`, `test_vettorizza`) | schema, documenti, indice |
| Valutazione (`test_valutazione`, `test_campiona`, `test_valutazione_foto`, `test_valutazione_registrata`) | che le metriche non dicano di sapere ciò che non hanno misurato, e che il dataset non diventi tautologico |
| Agente (`test_agente`, `test_materiali`, `test_condizioni`, `test_prompt`) | i quattro passaggi e le politiche del codice |
| Confine (`test_api`, `test_frontend`) | il contratto delle rotte e la leggibilità dei messaggi |
| Sistema (`test_docker`, `test_configurazione`, `test_percorsi`) | che il compose dica ciò che intendiamo |
| Presidio (`test_documentazione`, `test_lint`) | che documentazione e pulizia non restino indietro |

`test_documentazione.py` è il più insolito: fallisce se la versione corrente non ha una voce
nel diario, se un comando o un modulo non è documentato, se la numerazione delle decisioni ha
buchi, o **se un modulo non è citato in questo documento**.

I test che richiedono file non versionati (i PDF di Torino) si **saltano**, non falliscono.

---

## 10. Configurazione

Tutto passa dal `.env` (modello versionato: `.env.example`), letto da `configurazione.py`.
Le variabili che cambiano il comportamento:

| Variabile | Effetto |
|---|---|
| `ECOSCAN_MODELLO_VISIONE` | quale modello guarda le foto |
| `ECOSCAN_MODELLO_EMBEDDING` | quale modello vettorizza (cambiarlo impone di reindicizzare) |
| `ECOSCAN_QDRANT` · `ECOSCAN_OLLAMA` · `ECOSCAN_API` | dove stanno i servizi |
| `ECOSCAN_LATO_MAX_IMMAGINE` | quanto grande arriva la foto al modello |
| `ECOSCAN_MLFLOW*` | indirizzo, esperimento, interruttore, foto, attesa, riprova |

In Docker gli indirizzi diventano i nomi dei servizi. I cinque servizi del compose:
`qdrant`, `mlflow`, `backend`, `frontend`, e `ollama` sotto il profilo `completo` (in
sviluppo Ollama resta sull'host, dove il modello è già scaricato).

---

## 11. Come si aggiorna questo documento

Va rivisto **quando cambia la struttura**, non a ogni riga di codice. In pratica:

- **modulo nuovo o rimosso** → aggiorna la mappa (sezione 5). Un test lo impone: se un
  modulo di `src/ecoscan/` non è citato qui, `test_documentazione.py` fallisce;
- **rotta nuova** → sezione 5, elenco delle rotte;
- **passaggio nuovo nell'agente, o un passaggio che cambia ordine** → sezione 4;
- **interfaccia nuova, o un'implementazione in più** → sezione 7;
- **regola di dipendenza nuova** → sezione 6;
- **comando ETL nuovo, o un ordine diverso** → sezione 3;
- **niente di tutto questo** → non toccarlo: un documento che cambia a ogni commit smette di
  essere letto.

Aggiorna anche la riga "Aggiornato alla **vX.Y.Z**" in cima, così si vede a colpo d'occhio
se è rimasto indietro.

Resta a carico di chi scrive ciò che una macchina non può verificare: che i diagrammi
descrivano il flusso vero, e che le motivazioni siano ancora quelle.
