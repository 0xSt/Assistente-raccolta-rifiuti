# Glossario

Termini usati nel codice, nel [diario](diario.md) e nella relazione. Quando un termine ha
un significato specifico in questo progetto, è segnalato.

## Il processo ETL

**ETL** — Extract, Transform, Load: le tre fasi con cui dati sparsi e disomogenei diventano
un database interrogabile. Qui: *Extract* scarica e legge le fonti ufficiali, *Transform*
le porta a un modello unico, *Load* le carica in SQLite.

**Extract (estrazione)** — Leggere la fonte così com'è, senza interpretarla. Produce il
livello grezzo. Ogni fonte ha il suo estrattore: `extract_torino.py` (PDF), `extract_napoli.py` (HTML).

**Transform (trasformazione)** — Portare dati di forma diversa a un modello comune:
pulire, separare, riconciliare. È qui che si prendono le decisioni interpretative, e per
questo è separato dall'estrazione: si può rieseguire cambiando le regole, senza riscaricare.

**Load (caricamento)** — Scrivere i dati normalizzati nel database di destinazione.
Qui avviene per **ricostruzione totale**: il database è cancellato e rifatto da zero a ogni
esecuzione, perché è un artefatto derivato e la verità sta nei file normalizzati.

**Livello grezzo** — Copia fedele di ciò che la fonte dice, con URL o pagina, data,
hash SHA-256 e versione dell'estrattore. Non si interpreta e non si corregge: serve a
risalire alla fonte esatta di ogni dato.

**Livello normalizzato** — Le stesse informazioni portate al modello comune fra i comuni:
nome pulito, condizioni, alias, destinazioni, avvertenza. È il livello su cui si ragiona.

**Scheda** — Unità restituita dalla ricerca. Una voce produce più schede (una per il nome
con le sue condizioni, una per ciascun alias); anche ogni regola ammessa o esclusa è una
scheda. Schede diverse possono puntare alla stessa voce.

**Livello di serving** — Le strutture costruite per rispondere in fretta: indice testuale,
vettori, viste. Si rigenera dal normalizzato e si può buttare via.

**Pipeline** — La catena di passaggi dall'estrazione al serving. "Rieseguire la pipeline"
significa ripartire dai file sorgente e riprodurre tutto.

**Idempotenza** — Proprietà per cui rieseguire un passaggio sugli stessi dati dà lo stesso
risultato. Nel progetto è garantita dalla cache con hash e dal fatto che il Transform non
modifica il grezzo.

**Provenienza (data lineage)** — La catena che lega un dato alla sua origine. Qui è
`record_grezzo → snapshot → fonte`.

**Snapshot** — Il contenuto di un file o di una pagina in un momento preciso, identificato
dal suo hash. Se la fonte cambia, cambia l'hash e ce ne accorgiamo.

**Hash SHA-256** — Impronta di un contenuto. Due file con lo stesso hash sono identici;
serve a sapere se una fonte è cambiata senza confrontarla riga per riga.

**Entity resolution** — Riconoscere che nomi diversi indicano la stessa cosa (a Napoli
"Divano", a Torino "Divani"). Rimandata: il campo `oggetto_canonico_id` è predisposto ma vuoto.

**Deduplicazione** — Unire record che descrivono la stessa voce. Qui è insensibile a
singolare e plurale e non risolve mai in automatico i casi con destinazioni diverse.

**Conflitto** — Due voci con stesso nome e stesse condizioni ma destinazioni diverse.
Viene segnalato, mai risolto dal codice: o è un errore del Transform o è una contraddizione
della fonte, e in entrambi i casi deve decidere una persona.

**Scraping** — Estrarre dati da pagine web pensate per essere lette da umani.

**robots.txt** — File in cui un sito dichiara cosa gli automatismi possono visitare.
L'estrattore di Napoli lo rispetta e si ferma se vieta l'accesso.

**Sitemap** — File XML in cui un sito elenca le proprie pagine. A Napoli è la strada più
affidabile per trovare tutte le 584 voci.

**Slug** — La parte finale di un URL che identifica una pagina
(`.../dove-lo-butto/bottiglia-in-plastica/`). Qui è l'identificatore stabile della voce.
A Napoli conserva anche informazioni perse dal titolo, ma degradate: "l'ago" diventa "lago".

**Fixture** — Dato di prova usato in un test. Una fixture più semplice della realtà fa
passare i test e nasconde i bug: è già successo in questo progetto.

## Dati e modello

**Voce** — Una riga del dizionario comunale: un oggetto e le sue destinazioni.
È il livello di evidenza 1.

**Regola di categoria** — Ciò che un comune dichiara per un intero contenitore
("nella carta sì i giornali, no gli scontrini"). È il livello di evidenza 2.

**Destinazione** — Dove si conferisce, con il nome che usa il comune: "Plastica e Metalli",
"Isola Ecologica Estesa". Non è il materiale.

**Canale** — Il tipo di destinazione, per confrontare comuni diversi: raccolta ordinaria,
contenitore dedicato, centro di raccolta, raccolta itinerante, ritiro a domicilio.

**Flusso** — Il materiale canonico (carta, plastica, metalli, vetro, organico, residuo…).
Serve a confrontare raggruppamenti diversi: "Vetro e imballaggi in metallo" a Torino è
vetro+metalli, "Plastica e Metalli" a Napoli è plastica+metalli.

**Trascrizione manuale** — Dato presente nella fonte ma non estraibile da uno script
(qui: testo dentro un'immagine), letto a occhio e messo in un file versionato. Nel database
porta un'origine distinta, perché è affidabile ma non riproducibile automaticamente.

**Assenza verificata** — Registrazione del fatto che una fonte *non* contiene una certa
informazione. Distingue "controllato, non c'è" da "non ancora controllato", e serve a non
far scattare avvisi dove non c'è nulla da fare.

**Polarità** — Se una regola di categoria dice cosa va nel contenitore (`ammesso`),
cosa non ci va (`escluso`) o aggiunge un'istruzione (`nota`).

**Revisione manuale** — Decisione presa da una persona sulle voci che il Transform non sa
risolvere da solo. Sta in un CSV versionato e viene riapplicata a ogni esecuzione, così non
va persa quando le regole cambiano.

**Dato di riferimento** — Dato curato a mano che non viene da nessuna fonte esterna e che
serve a interpretare gli altri: qui canale, colore e flussi delle destinazioni. Versionato
come il codice.

**Corrispondenza (mapping)** — Tabella che collega i nomi usati da una fonte a quelli del
modello normalizzato. Qui collega il nome della scheda alla destinazione: "Carta e Cartone"
nella pagina frazione è "Carta e Cartoncino" nelle voci.

**Frazione** — Come le aziende chiamano la categoria di raccolta. Nel progetto si usa
"destinazione" per il dato e "frazione" quando si cita la fonte.

**Destinazioni alternative** — Più destinazioni per la stessa voce significano "oppure",
non "in parte l'una e in parte l'altra": un divano si può portare all'isola ecologica
oppure far ritirare.

**Condizione** — Ciò che cambia la destinazione a parità di oggetto: pulito o unto,
vuoto o con residui, piccole o grandi quantità.

**Alias** — Nome alternativo della stessa voce, usato per la ricerca: "tetrapak" per
"Cartone per bevande".

**Codice materiale** — La sigla stampata sugli imballaggi (PET 01, ALU 41, C/PAP 81).
Napoli ha 16 voci basate su questi codici: utili, perché spesso sono leggibili nella foto.

**Livello di evidenza** — Quanto è fondata la risposta: 1 il comune ha classificato
l'oggetto, 2 esiste solo la regola di categoria e il criterio lo applica il modello,
3 nessuna regola del comune copre l'oggetto.

**Avvertenza** — Istruzione di preparazione legata a una voce ("proteggere l'ago con il
cappuccio", "contenitore vuoto").

**Da revisionare** — Marcatore che il Transform mette quando ha fatto una scelta di cui
non è certo. Non blocca nulla: produce un elenco di decisioni da prendere a mano.

## Modello e ricerca

**LLM multimodale** — Modello che accetta testo e immagini insieme. Qui Gemma 4, eseguito
in locale su Ollama.

**Ollama** — Server che espone modelli locali via API REST e gestisce l'accelerazione hardware.

**Quantizzazione** — Riduzione della precisione numerica dei pesi per far stare il modello
in meno memoria, al prezzo di un po' di accuratezza.

**Inferenza su CPU** — Esecuzione del modello senza GPU. Ogni token di prompt costa tempo:
è il vincolo che ha portato al retrieval invece di mettere l'intero catalogo nel prompt.

**Retrieval** — Recuperare da un archivio i pochi documenti utili a rispondere.

**RAG** — Retrieval-Augmented Generation: il modello risponde usando documenti recuperati,
non solo ciò che ha memorizzato.

**Ricerca lessicale (BM25)** — Ricerca per parole: precisa sui nomi esatti, cieca sulle
parafrasi ("contenitore del latte" non trova "Tetra Pak").

**FTS5** — Il motore di ricerca full-text integrato in SQLite.

**Tokenizer a trigrammi** — Spezza il testo in sequenze di tre caratteri. Tollera plurali
ed errori di battitura, e serve perché FTS5 non ha uno stemmer italiano.

**Stemming** — Ridurre le parole alla radice ("bottiglie" → "bottigli"). Non disponibile
per l'italiano in FTS5: da qui la scelta dei trigrammi.

**Embedding** — Vettore numerico che rappresenta il significato di un testo. Testi simili
hanno vettori vicini.

**Ricerca semantica** — Ricerca per vicinanza fra embedding. Risolve le parafrasi ma
confonde oggetti simili con destinazioni diverse: "bottiglia di vetro" e "bicchiere di
vetro" sono quasi identici e vanno in contenitori diversi.

**Ricerca ibrida** — Lessicale e semantica in parallelo, risultati fusi. Scelta del
progetto proprio perché i due difetti sono complementari.

**Normalizzazione di un vettore** — Riportarlo a lunghezza 1, così il coseno fra due
vettori si calcola con un semplice prodotto scalare.

**RRF (Reciprocal Rank Fusion)** — Metodo per fondere due classifiche usando la posizione
dei risultati invece dei punteggi, che non sono confrontabili fra loro.

**Scelta vincolata** — Chiedere al modello di scegliere fra candidati reali, o di
rispondere "nessuno", invece di lasciarlo produrre un nome libero. Contiene le allucinazioni.

**Allucinazione** — Risposta inventata ma plausibile. Qui è contenuta facendo arrivare la
regola finale sempre da SQL e mai dal modello.

**Output strutturato** — Risposta del modello vincolata a uno schema JSON, così il backend
può usarla senza interpretarne il testo.

## Strumenti

**File `.env`** — File di testo alla radice del progetto con le impostazioni locali
(`chiave=valore`). Non è versionato: `.env.example` ne è il modello. Evita di dover
impostare variabili a mano nel terminale, dove valgono per una sola finestra.

**Qdrant** — Database vettoriale usato nel progetto. Conserva le schede con il loro vettore
e un payload di metadati, e filtra per comune *durante* la ricerca. Si usa come container o,
nei test, in modalità in-process senza server.

**Payload** — I metadati associati a un vettore in Qdrant. Qui: comune, livello, tipo e
testo. Non contiene la destinazione, che sta solo nel relazionale.

**Modalità locale (in-process)** — Implementazione Python di Qdrant dentro il processo che
la usa, senza server. Comoda per test e prototipi; apre la cartella in esclusiva e non ha
dashboard.

**uv** — Gestore di ambienti e dipendenze Python usato nel progetto. `uv sync` prepara
l'ambiente da `uv.lock`, `uv run` esegue un comando dentro quell'ambiente.

**uv.lock** — File che fissa le versioni esatte di tutte le dipendenze. Va versionato:
è ciò che rende l'ambiente riproducibile.

**Entry point** — Comando installabile dichiarato in `[project.scripts]`
(`ecoscan-napoli`, `ecoscan-transform`…), che esegue una funzione `main()`.

**Profilo** — In questo progetto, l'insieme delle regole di Transform specifiche di un
comune. Il motore è unico, i profili cambiano.

**Test di regressione** — Test che fissa un comportamento già verificato, per accorgersi
se una modifica futura lo rompe.
