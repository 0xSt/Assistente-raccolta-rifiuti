# Diario di progetto — EcoScan Local

File unico di riferimento per capire **cosa è stato fatto, perché, e cosa resta da fare**.
Ha inglobato i precedenti `CHANGELOG.md` e `docs/decisioni.md`.

Altri documenti, che restano separati perché sono cataloghi di riferimento e non cronologia:
- [fonti.md](fonti.md) — da quali documenti e URL provengono i dati
- [qualita_dati.md](qualita_dati.md) — catalogo dei difetti di ciascuna fonte e come sono trattati
- [glossario.md](glossario.md) — significato dei termini usati qui

## Come si aggiorna

L'aggiornamento non è affidato alla buona volontà: `tests/test_documentazione.py` fallisce se
la versione in `pyproject.toml` non ha una voce nella cronologia qui sotto, se un comando o un
modulo non è documentato nel README, se la numerazione delle decisioni ha buchi o doppioni, se
una decisione è priva di stato, o se manca un termine essenziale dal glossario. Un test rosso
si nota; un promemoria no.

Restano a carico di chi scrive le cose che una macchina non può verificare: che la motivazione
di una decisione sia vera, che una questione aperta sia ancora aperta, che i numeri citati
corrispondano all'ultima esecuzione.

Va aggiornato **a ogni cambiamento sostanziale**, non a ogni riga di codice. In pratica:

- una **modifica** entra in "Cronologia" quando cambia il comportamento del sistema o i dati prodotti;
- una **decisione** entra nella tabella quando fissa una regola che vincola il lavoro futuro. Le decisioni non si cancellano: quando cadono, restano con stato "superata da Dn";
- una **questione aperta** si aggiunge quando si scopre un problema che non si risolve subito, e si toglie quando è chiusa;
- un'**annotazione** serve per ciò che non è né decisione né modifica, ma che servirà ricordare (es. una scoperta sui dati, una trappola in cui si è già caduti).

---

## Stato attuale (v0.48.1, 25/09/2026)

| Componente | Stato |
|---|---|
| Estrattore Torino (PDF) | Completo: 324 voci dall'elenco A-Z |
| Estrattore Napoli (HTML) | Completo: 584 voci dal dizionario, 6 pagine frazione |
| Transform Napoli | Eseguito: 584 grezze → 1 scartata, 5 fuse, **578 normalizzate**. 0 conflitti, 0 da revisionare |
| Transform Torino | Eseguito: **324 normalizzate**, 0 conflitti, 0 da revisionare |
| Regole nel normalizzato | Fatto: **110 regole** collegate alle destinazioni (Napoli 50 su 4, Torino 60 su 9) |
| Load relazionale | Fatto: `ecoscan-carica` ricostruisce `data/ecoscan.db` dai file normalizzati |
| Serving | Documenti su Qdrant, sola ricerca semantica, aggancio esatto dei codici materiale |
| Agente | Fatto: riconoscimento, cascata dei livelli, scelta vincolata, risposta. Indipendente da HTTP |
| API FastAPI | Fatto: analizza, continua, correggi, cerca, comuni, destinazioni, salute, riscontro |
| Frontend a chat | Fatto (v0.31.0): etichette leggibili, riconoscimento visibile e correggibile, chiarimenti a pulsante, citazione del documento |
| Osservabilità | Fatto (v0.30.0): tracce MLflow per turno con foto, retrieval e sessione; versione dell'app e prompt collegati |
| Docker | Fatto: qdrant, mlflow, backend, frontend; ollama sotto profilo |
| Regole di categoria — Napoli | Completo per quanto la fonte pubblica: 38 ammessi, 11 esclusi (5 Vetro estratti + 6 Umido trascritti a mano), 2 assenze verificate |
| Regole di categoria — Torino | Estratte: 10 schede, 30 ammessi, 27 esclusi |
| Revisione manuale | **Completa**: 32 decisioni prese (16 per comune), 0 aperte, 0 voci da revisionare |
| Valutazione | Fatto: 141 casi in quattro insiemi, otto metriche, run su MLflow. Mancano le foto da scattare |
| Backend, frontend, modello | Da fare |

---

## Decisioni

Formato: decisione, motivazione, stato.

### Prodotto e architettura

| # | Decisione | Motivazione | Stato |
|---|---|---|---|
| D1 | Web app locale in Python, Docker multi-container: frontend Streamlit, backend FastAPI, modello su Ollama | Privacy, esecuzione offline, requisito del progetto | Accettata |
| D2 | Modello base `gemma4:e2b`, `gemma4:e4b` come confronto in valutazione | Superata da D79: la scelta era corretta sulla carta, ma la parte visiva di Gemma 4 non funziona su questa installazione | Superata da D79 |
| D3 | Input: foto di **un solo oggetto**, comune obbligatorio, testo facoltativo | Perimetro dell'agente definito da Stef | Accettata |
| D4 | Domande solo testuali: indicazione provvisoria e richiesta di una foto prima di una risposta sicura | La foto verifica materiale, componenti e stato | Accettata |
| D5 | Comuni del prototipo: Napoli e Torino | Formati complementari (HTML e PDF); Rifiutologo 2025 granulare e recente | Accettata |
| D20 | Ambiente e dipendenze con **uv**; codice come package `src/ecoscan`, comandi in `[project.scripts]` | Ambiente riproducibile da `uv.lock`, import assoluti stabili, comandi eseguibili da qualsiasi cartella | Accettata |
| D21 | Percorsi centralizzati in `ecoscan/percorsi.py`, radice trovata dal `pyproject.toml`, override `ECOSCAN_RADICE` | I percorsi relativi alla cartella corrente si rompono nei container e nei comandi installati | Accettata |

### Risposta dell'agente e retrieval

| # | Decisione | Motivazione | Stato |
|---|---|---|---|
| D6 | Tre livelli di evidenza: 1 voce di dizionario, 2 regola di categoria, 3 nessuna regola del comune | La certezza della risposta dipende da chi ha classificato l'oggetto | Accettata |
| D7 | Mai usare le regole di un altro comune | Le regole cambiano davvero: bicchiere di vetro → non riciclabile a Napoli, vetro a Torino | Accettata |
| D8 | Retrieval ibrido: FTS5 a trigrammi + embedding, fusione RRF, filtro per comune prima della ricerca | Il solo semantico confonde oggetti simili con destinazioni diverse (bottiglia/bicchiere di vetro) | Accettata |
| D9 | Il modello sceglie tra candidati reali o risponde "nessuno"; la regola finale arriva sempre da SQL | Contenere le allucinazioni, rendere la valutazione misurabile | Accettata |
| D10 | Ricerca a cascata: voci → regole di categoria → livello 3 | Il livello di evidenza diventa un risultato del flusso, non una stima del modello | Accettata |

### Schema dati

| # | Decisione | Motivazione | Stato |
|---|---|---|---|
| D11 | Nessun catalogo canonico degli oggetti per ora (`oggetto_canonico_id` facoltativo) | Evitare l'entity resolution nel prototipo senza chiudere la porta | Accettata |
| D12 | Un solo file SQLite: FTS5 + vettori con sqlite-vec | Superata da D59: il criterio era la sola efficienza, ma per un progetto universitario conta anche che l'architettura sia leggibile e la tecnologia appropriata | Superata da D59 |
| D34 | **Il corpus resta testuale: solo la query è multimodale.** Nessuna indicizzazione di immagini | Gemma 4 è generativo e non produce vettori confrontabili; servirebbe un modello CLIP in più. Le immagini delle fonti sono stilizzate e rappresentano categorie, e l'informazione che decide la risposta è testuale e locale, non visiva | Accettata |
| D35 | Nessuna descrizione visiva generata da Gemma per ora | Rimandata da Stef: costa una notte di calcolo e va valutata, non data per buona. Resta come possibile sviluppo | Rimandata |
| D36 | Load a ricostruzione totale, in tre passaggi separati (relazionale, lessicale, vettoriale) | La verità sta nei file normalizzati, il database è un artefatto derivato: più semplice di una logica di aggiornamento e idempotente | Accettata |
| D37 | Una scheda genera più vettori (nome+condizioni, ogni alias); la destinazione non entra mai nel testo indicizzato | Chi cerca "tetrapak" non deve sperare che assomigli a "Cartone per bevande". Indicizzare la destinazione farebbe trovare gli oggetti per contenitore e allontanerebbe oggetti quasi identici con destinazioni diverse, che è proprio il caso in cui serve chiedere all'utente | Accettata |
| D13 | Tre livelli: grezzo, normalizzato, serving | Tracciabilità di ogni dato fino alla fonte | Accettata |
| D14 | Più destinazioni per una voce sono **alternative** (OR), non componenti | Verificato su entrambe le fonti (Divani, Armadio) | Accettata |
| D15 | Destinazioni classificate per **canale** e collegate a **flussi** canonici molti-a-molti | Confrontare comuni con raggruppamenti diversi (vetro+metalli a Torino, plastica+metalli a Napoli) | Accettata |

### Estrazione

| # | Decisione | Motivazione | Stato |
|---|---|---|---|
| D16 | Torino: estrazione deterministica dai marcatori vettoriali, senza LLM | Riproducibile e verificabile; LLM riservato ai casi ambigui | Accettata |
| D17 | Napoli: nessuna dipendenza dalle classi CSS; la lista "Puoi inoltre conferire" non determina il contenitore | Elementor rigenera le classi; la lista è quasi identica su voci con destinazioni diverse | Accettata |
| D18 | Destinazioni lette dal testo **aggregato** degli elementi, non dai singoli nodi; due passaggi con ripiego su vocabolario | I nodi di testo sono frammentati: `(`, nome e `)` stanno in elementi diversi | Accettata |
| D19 | Scoperta delle voci dalla sitemap XML (584 URL), non dalla paginazione dell'indice | Confermato dalla ricognizione; l'indice mostra 40 voci per pagina | Accettata |
| D22 | Le descrizioni delle destinazioni non si estraggono dalle pagine voce | Sono identiche su tutte le voci che usano quella destinazione: proprietà della destinazione | Accettata |
| D23 | Il campo avvertenza ha priorità sul testo ricavato dallo slug | L'avvertenza conserva accenti e apostrofi, lo slug li perde ("l'ago" → "lago") | Accettata |
| D32 | Nelle pagine frazione la raccolta dipende dalla polarità: ammessi dai `<strong>`, esclusi dagli `<li>` | Il markup delle due sezioni è diverso; cercare solo i `<strong>` restituiva zero esclusioni in silenzio | Accettata |
| D45 | Le decisioni manuali stanno in CSV versionati (`data/revisioni/<comune>.csv`) che il Transform applica a ogni esecuzione | Il Transform riscrive il normalizzato da zero: una correzione fatta lì andrebbe persa. Così le decisioni sono riproducibili, tracciabili in git e numerabili nella relazione | Accettata |
| D46 | Una decisione riferita a uno slug inesistente fa fallire l'esecuzione | Se la fonte cambia, la decisione va rivista, non ignorata in silenzio | Accettata |
| D55 | Vettori in SQLite come BLOB, ricerca esaustiva in NumPy | Superata da D59: la scelta era corretta sul piano prestazionale ma non su quello architetturale | Superata da D59 |
| D59 | **Qdrant** come database vettoriale, SQLite per il relazionale: due store con ruoli distinti | Qdrant trova i candidati, SQLite dà la risposta. Il filtro per comune diventa una condizione applicata *dentro* la query e non un passaggio successivo, quindi il vincolo D7 è strutturale. Si incastra con l'architettura multi-container (D1) e la dashboard serve anche per la relazione. Con ~1100 vettori le prestazioni non discriminavano: la scelta è di architettura, non di velocità | Accettata |
| D60 | Client configurabile con `ECOSCAN_QDRANT`: URL → server, percorso → modalità in-process | I test girano senza container e senza rete, lo sviluppo non richiede Docker acceso, la consegna usa il server. Una riga di configurazione, tre modi di lavorare | Accettata |
| D62 | Le impostazioni stanno in un file `.env` alla radice, con `.env.example` versionato come modello | Le variabili impostate a mano nel terminale valgono per una finestra sola e si dimenticano: un valore mancante fa scrivere i vettori nel posto sbagliato senza errori. Un file rende la configurazione esplicita e riproducibile | Accettata |
| D63 | Le variabili d'ambiente vere hanno la precedenza sul `.env`, **ma una variabile vuota conta come assente** | La precedenza serve a Docker; l'eccezione sul vuoto evita che un `ECOSCAN_X=` lasciato in giro faccia ignorare il file in silenzio | Accettata |
| D64 | I comandi stampano in testa le impostazioni in uso | Il modo più rapido per accorgersi che una variabile non era quella che si credeva | Accettata |
| D65 | L'indicizzazione si verifica con l'**autorecupero**, non solo con i conteggi | Conteggi e identificatori possono tornare anche con i vettori associati alle schede sbagliate. Cercare il testo di una scheda e pretendere che ritrovi sé stessa al primo posto è l'unico controllo che lega vettore e identificatore | Accettata |
| D66 | Il codice materiale entra nel testo indicizzato | È la sigla che l'utente legge sull'imballaggio ("PAP 21"), e senza di esso "Simbolo GL o GLS" è identico per i codici 70, 71 e 72: tre voci con destinazioni diverse diventerebbero indistinguibili | Accettata |
| D70 | L'agente è un oggetto Python indipendente da FastAPI | Valutazione e test lo chiamano direttamente: se la logica stesse nelle rotte, misurarla richiederebbe di alzare un server | Accettata |
| D71 | I prompt sono file versionati in `src/ecoscan/prompt/`, con versione dichiarata e impronta calcolata sul contenuto | Ogni risposta registra quale prompt l'ha prodotta; una modifica senza cambio di versione resta comunque visibile dall'impronta | Accettata |
| D72 | `analizza` (dalla foto) e `rispondi` (dal riconoscimento) sono separati | Permette di valutare retrieval e scelta senza rieseguire il modello di visione su ogni foto, che su CPU è il passaggio più lento | Accettata |
| D73 | Il chiarimento nasce dai dati, non dall'intuito del modello: se fra i candidati ci sono omonimi con destinazioni diverse, la condizione si chiede | "Capsule del caffè in plastica" con e senza residuo vanno in contenitori diversi e dalla foto non si distingue | Accettata |
| D75 | Le richieste a Ollama passano `keep_alive` (30 minuti di norma) | Senza, il modello viene scaricato e ricaricato fra una chiamata e l'altra: su CPU sono decine di secondi per passaggio, e l'agente ne fa fino a tre | Accettata |
| D82 | Il modello di visione produce anche **sinonimi** e **categoria** dell'oggetto, usati come formulazioni aggiuntive | È il ponte fra il vocabolario del modello e quello della fonte: il modello dice "sandalo", ASIA scrive "Scarpe". Con la sola parola "sandalo" la ricerca semantica restituiva parole che le somigliano nella forma ("Salse", "Sdraio", "Scaldabagno") | Accettata |
| D90 | La sonda riporta **quale scheda** ha soddisfatto l'attesa, e il primo risultato quando fallisce | Cercando "Scarpe" come sottostringa si accettava "Laccio per scarpe": un falso positivo va visto, non dedotto confrontando due output diversi | Accettata |
| D94 | Il backend apre il database in **sola lettura** | L'ETL resta una serie di comandi separati: il servizio che risponde alle richieste non può corrompere ciò che gli serve per rispondere. Il vincolo è nel codice (`mode=ro`), non una promessa | Accettata |
| D95 | Gli schemi delle API sono tipi Pydantic distinti dai tipi interni dell'agente | Permette di cambiare i tipi interni senza rompere il contratto col frontend, e viceversa | Accettata |
| D97 | Il frontend è una **chat con allegato**, non un modulo con campi | È il gesto che le persone già conoscono dagli assistenti; e la conversazione serve davvero, perché l'agente fa domande quando la condizione decide la destinazione | Accettata |
| D98 | Il frontend parla solo con le API, e un test verifica che non importi l'agente né il database | Se importasse il backend, la valutazione misurerebbe qualcosa di diverso da ciò che usa l'utente | Accettata |
| D99 | La formattazione dei messaggi sta in un modulo a parte, con i suoi test | È la parte che si sbaglia più facilmente: una regola di esclusione presentata male dice l'opposto del vero | Accettata |
| D96 | La rotta `/riscontro` registra il giudizio dell'utente su una risposta | Ogni riga è un esempio etichettato da una persona: è il modo meno costoso di costruire il set di valutazione, che oggi non esiste | Accettata |
| D111 | **Una sola strategia di ricerca: la semantica.** Rimossi FTS5, trigrammi, riduzione alla radice, parole di servizio, fusione RRF, garanzie e tetti | Le sonde mostravano che l'ibrido non cambiava il risultato: 14 su 16 in entrambi i casi, con un caso migliorato e uno peggiorato. Un secondo metodo tenuto per prudenza è complessità senza guadagno | Accettata |
| D120 | Un'**immagine sola** per backend e frontend, con comandi diversi | Restano due servizi distinti e separati nel codice (un test verifica che il frontend non importi il backend), ma costruire due immagini quasi identiche costerebbe tempo e spazio senza vantaggi in un prototipo | Accettata |
| D121 | Il database è montato nel backend come volume in **sola lettura**; l'ETL resta fuori dai container | Chi risponde alle richieste non scrive i dati che gli servono per rispondere. Il vincolo è nel compose oltre che nel codice | Accettata |
| D122 | Il frontend conosce **solo** l'indirizzo del backend, anche nel compose | Se avesse quelli di Qdrant o Ollama, prima o poi qualcuno li userebbe, e la valutazione misurerebbe un percorso diverso da quello dell'utente | Accettata |
| D123 | Il tracciamento passa dalle **run** alle **tracce** di MLflow Tracing: una traccia per turno, con span per riconoscimento, recupero e scelta | La run registrava un riassunto (conteggi, tempi); la traccia registra cosa è entrato e cosa è uscito da ogni passaggio, che è ciò che serve per capire una risposta sbagliata e, più avanti, per la valutazione | Accettata |
| D124 | Le **foto** si salvano come allegati delle tracce, con l'impronta accanto; `ECOSCAN_MLFLOW_FOTO=no` torna alla sola impronta | Senza la foto una traccia di riconoscimento non si può giudicare. Supera D117, per decisione di Stef | Accettata |
| D125 | I turni della stessa conversazione condividono `mlflow.trace.session`; l'identificativo viaggia nel contesto | Il backend resta senza stato: il contesto era già il canale per ciò che deve sopravvivere fra `analizza` e `continua` | Accettata |
| D126 | I parametri significativi formano un **LoggedModel** (nome = impronta dei parametri) collegato a ogni traccia; i prompt pubblicati si collegano per **impronta**, non per numero di versione | Stessi parametri dopo un riavvio, stesso LoggedModel. I numeri di versione del registro e quelli dei file non coincidono, l'impronta sì | Accettata |
| D127 | Il server MLflow nel compose ha la **stessa versione** del client nel `uv.lock`, e un test lo verifica | Tracce, allegati e collegamenti dipendono dal server: con versioni diverse le funzioni nuove fallirebbero, e il tracciamento non bloccante lo nasconderebbe | Accettata |
| D128 | Le destinazioni hanno un'**etichetta** leggibile, curata a mano in `destinazioni.csv`; le risposte continuano a portare il nome interno | I nomi di Torino sono chiavi (`carta_e_cartone`) e l'utente non deve leggerle. Tradurre nell'interfaccia e non nei dati lascia il nome interno come chiave stabile di tutto il resto | Accettata |
| D129 | Ogni **voce** porta fonte e riferimento (URL della pagina a Napoli, pagina del PDF a Torino), come già facevano le regole | Senza, una risposta di livello 1 non poteva dire da dove veniva: la provenienza c'era nel grezzo e si perdeva nel Transform | Accettata |
| D130 | Il **riconoscimento** della foto si mostra sempre all'utente, prima della risposta | È il passaggio più fragile della catena e l'unico che l'utente può smentire con certezza, perché ha l'oggetto in mano | Accettata |
| D131 | Nuova rotta `/correggi`: l'utente dichiara l'oggetto e si rifanno solo ricerca e scelta, con confidenza 1.0 | La foto non si rilegge (è il passaggio lento) e non si fa riguardare a un modello che ha già sbagliato. È il motivo per cui `analizza` e `rispondi` erano separati (D72) | Accettata |
| D132 | Il chiarimento porta con sé le **opzioni**, e l'interfaccia ne fa pulsanti | Le condizioni vengono dalle varianti del documento: farle scrivere a mano aggiungeva solo modi di sbagliare | Accettata |
| D133 | "Come ci sono arrivato" mostra la **citazione** del documento scelto, il motivo e le voci scartate; la tabella dei punteggi passa in secondo piano | I punteggi di somiglianza spiegano il sistema a chi lo sviluppa, non la risposta a chi la riceve. La citazione è anche la prova che la destinazione non è inventata dal modello | Accettata |
| D134 | *(ritirata)* Un oggetto composto riceve una risposta per ogni parte separabile | Provata in v0.32.0 e rimossa in v0.32.1: la prima foto vera (piatto con forchetta appoggiata sopra) ha mostrato che il caso frequente non è l'oggetto con parti separabili ma la foto con **più oggetti distinti**, che è un problema diverso. La funzione costava una ricerca e una chiamata al modello per parte senza risolverlo | Superata da D136, ritirata in v0.32.1 |
| D135 | *(ritirata)* Nessun chiarimento per le parti, e parti cercate solo senza domande in sospeso | Cadono con D134 | Superata da D136, ritirata in v0.32.1 |
| D136 | Più oggetti nella stessa foto restano **fuori portata** per ora: il modello descrive un solo oggetto, quello principale | Distinguere gli altri oggetti da buttare dallo sfondo (in una foto: un piatto, una forchetta, un portatile, una scrivania, un cavo) è un problema di riconoscimento, non di recupero, e va affrontato da solo | Accettata |
| D137 | *(ritirata)* L'agente annuncia le sue fasi a un oggetto `Avanzamento` | Provata in v0.33.0 e rimossa in v0.33.1 per decisione di Stef | Superata: ritirata in v0.33.1 |
| D138 | *(ritirata)* Rotte a flusso di eventi accanto a quelle esistenti | Cade con D137 | Superata: ritirata in v0.33.1 |
| D139 | *(ritirata)* Lavoro dell'agente in un thread, eventi in coda | Cade con D137 | Superata: ritirata in v0.33.1 |
| D140 | Le condizioni si distinguono in **stato**, **quantità** e **chi conferisce**: cambia la frase ("vale per piccole quantità" invece di "vale se è: piccole quantità") e cambia la domanda ("quanto ne hai?" invece di "com'è?") | Contate sui dati veri: 147 condizioni, di cui 15 di quantità e 5 di utenza. Sono abbastanza da produrre frasi sbagliate spesso, e la distinzione si può leggere dal testo senza toccare i dati. Il modulo sta fuori da agente e frontend perché serve a entrambi: la domanda la compone l'agente, la frase la scrive la presentazione | Accettata |
| D141 | Le **clausole di ammissibilità** ("solo se compostabile certificato") restano un caso da revisione manuale, non una distinzione nei dati | Contate: 1 su 147. Un campo nuovo nel normalizzato, la migrazione dello schema e la rivettorizzazione non si ripagano per una riga | Accettata |
| D142 | Ruff configurato nel `pyproject.toml` ed eseguito come test (`test_lint.py`), saltato se ruff non è installato | Import morti e parametri inutilizzati si accumulano in silenzio. Un test che li trova a ogni `pytest` costa un secondo; ricordarsene ogni tanto non funziona | Accettata |
| D143 | Le rotte dell'API si registrano per area (stato, agente, ricerca, riscontro), e i passaggi dell'agente stanno in metodi separati (`_recupera`, `_scegli`, `_prova_livello`, `_cascata`, `_componi`) | `crea_app` era una funzione di 112 righe in cui ogni rotta nuova allungava la stessa closure; `rispondi` teneva insieme soglia, cascata e composizione. Le unità piccole si leggono e si provano da sole | Accettata |
| D144 | I passaggi che lavorano sullo stesso oggetto lo ricevono come dato: `Richiesta` nell'agente, `Estratti` nel Transform | Erano firme da sei e sette parametri, in cui l'ordine contava più del significato e ogni aggiunta li allungava | Accettata |
| D145 | Il recupero è un'**interfaccia** (`Recupero`) con un'implementazione (`RecuperoQdrant`): l'agente riceve un recupero, non Qdrant e il vettorizzatore | L'agente dichiara cosa gli serve — candidati per comune e livello — e non sa da dove arrivino. Una ricerca ibrida diventa un'implementazione in più invece di una modifica all'agente, e i test possono usare un recupero in memoria senza Qdrant | Accettata |
| D146 | Nella configurazione tracciata `modello_embedding` diventa `recupero` (per esempio `qdrant:embeddinggemma`) | Il parametro che conta non è il modello di embedding ma la strategia di ricerca nel suo insieme: quando ce ne sarà più d'una, la traccia dovrà dire quale era in uso | Accettata |
| D147 | Un documento che dichiara un materiale **incompatibile** con quello riconosciuto viene tolto dai candidati **prima** della scelta; se lo scarto svuoterebbe l'elenco non si scarta nulla | Davanti a una forchetta d'acciaio il modello ha scelto "Forchetta in plastica" pur avendo riconosciuto l'acciaio e averlo scritto nel motivo. Togliere il documento è più sicuro che sperare nel prompt, e vale per qualunque modello. La clausola di salvataggio evita che un riconoscimento sbagliato sul materiale renda muto il sistema | Accettata |
| D148 | Il confronto sul materiale legge il **nome** del documento, non tutto il testo | Il testo dice anche dove va ("Va in Plastica e Metalli"), e quello è il contenitore: letto come materiale faceva scartare "Scatolette per tonno", che è di metallo. Trovato provando il filtro sui candidati veri di `/cerca`, non a tavolino | Accettata |
| D149 | La formulazione "oggetto + materiale" si pone all'indice **subito dopo** l'oggetto e la categoria | Misurato: "forchetta" non raggiunge "Stoviglie in metallo", "forchetta acciaio" sì (posizione 9). La formulazione col materiale esisteva ma stava in fondo, e il tetto di cinque domande la tagliava via proprio quando serviva | Accettata |
| D150 | `docs/architettura.md` descrive la struttura del sistema, e due test lo tengono allineato: ogni modulo dev'essere citato, e il documento deve nominare la versione corrente | Il diario racconta *quando* le cose sono cambiate, il glossario *cosa* vuol dire una parola: mancava il documento che dice *com'è fatto adesso*. Senza un test si sarebbe disallineato al terzo commit, come succede a ogni documento di architettura scritto una volta sola | Accettata |
| D151 | Il prompt di scelta dichiara che una voce con un nome **collettivo** ("stoviglie", "posate", "imballaggi") copre ogni oggetto dell'insieme, ed è una corrispondenza buona e non un ripiego | Osservato su foto vera: per una forchetta d'acciaio il modello aveva "Stoviglie in metallo" fra i candidati e rispondeva comunque "nessuna", facendo scendere la risposta al livello 2. Il concetto di "categoria" c'era già, ma gli esempi erano tutti specifico→generico dello stesso tipo di oggetto (sandalo→scarpe), non membro→insieme | Accettata |
| D152 | Lo stesso prompt limita quando dire "nessuna": vale se l'elenco parla d'altro, non se la voce è più larga dell'oggetto | La riga "meglio dire non lo so che indicare il contenitore sbagliato" è giusta ma sbilanciava verso lo 0: va equilibrata, o la prudenza diventa rinuncia | Accettata |
| D153 | Il recupero si valuta con un **dataset di casi** che parte dal riconoscimento, non dalla foto, e il recall@k si legge come **tetto** alla correttezza finale | Se a ogni esecuzione si rileggessero le foto, una differenza fra due esecuzioni potrebbe venire dal recupero, dalla scelta o dal modello di visione: tre cause per un solo effetto. Fissando il riconoscimento, ciò che resta misura solo recupero e scelta. E un errore va diagnosticato prima che riparato: "il documento c'era e non è stato scelto" e "il documento non c'era" chiedono due lavori diversi, come ha mostrato il caso della forchetta | Accettata |
| D154 | Un candidato conta come recuperato se **porta a una destinazione attesa**, non se ha un certo `id` | Lo stesso oggetto compare sotto nomi diversi ("Stoviglie in metallo", "Posate") e all'utente interessa il contenitore, non quale riga del regolamento è stata citata. Legare l'attesa all'`id` renderebbe il dataset fragile a ogni rigenerazione dei dati | Accettata |
| D155 | Il riscontro dell'utente diventa un caso di valutazione solo quando porta **un'attesa**: pollice su, o pollice giù con l'alternativa. Il pollice giù nudo resta nel registro grezzo | Sapere che una risposta è sbagliata senza sapere quale fosse quella giusta non si può rieseguire. Per questo l'interfaccia, dopo un pollice giù, chiede dove andava davvero fra i contenitori del comune: è l'unica domanda che trasforma un giudizio in una misura | Accettata |
| D156 | Un pollice giù con motivo "non ha capito che oggetto è" **non** diventa un caso | Il difetto sta nel riconoscimento, cioè proprio nel passaggio che i casi tengono fermo: un caso costruito su un oggetto sbagliato misurerebbe recupero e scelta su una domanda che non era quella giusta | Accettata |
| D157 | I casi da riscontro vivono in un file **separato e non versionato** da quelli scritti a mano, e in caso di collisione vince il manuale | Hanno autorità diversa: i primi sono un contratto che decidiamo noi e si discute in revisione, i secondi un campione di cosa succede davvero, che può contenere l'attesa sbagliata di un utente | Accettata |
| D158 | Il riconoscimento si mette in cache in memoria, dietro l'interfaccia `ModelloVisione`, con chiave impronta della foto + testo dell'utente; la **scelta no** | Il riconoscimento è il passaggio lento (minuti su CPU) ed è il più ripetuto, perché la stessa foto si rimanda decine di volte mentre si sviluppa. La scelta dipende dai candidati, che cambiano con l'indice e con le politiche: metterla in cache renderebbe invisibile proprio ciò che stiamo misurando. In memoria e non su disco perché un riconoscimento è il giudizio di una versione di un prompt, e non deve sopravvivere alla configurazione che l'ha prodotto | Accettata |
| D159 | I nomi mutilati dalla normalizzazione si riconoscono dalla **grammatica**, non dalla lunghezza, e diventano un motivo di revisione dentro il Transform | Accorciare un nome di metà è spesso il comportamento giusto ("Barattolo in latta (scatola di pelati, tonno…)" → "Barattolo in latta") e i nomi corti sono spesso sigle legittime. I controlli stretti su 902 voci ne segnalano 4: la precisione conta più della copertura, perché un controllo che grida al lupo viene disattivato. Collegarli ai motivi di revisione fa sì che la rottura si segnali da sé, invece di finire in un elenco che nessuno guarda | Accettata |
| D160 | Un oggetto si può **scrivere** invece di fotografarlo (`/domanda`), partendo dal riconoscimento dichiarato dall'utente con confidenza massima | Chi sa come si chiama la cosa non deve aspettare minuti perché un modello glielo confermi, e non rischia che glielo sbagli. È anche la porta d'ingresso per chi l'oggetto non ce l'ha in mano. Stessa cascata, stessa scelta, stesse tracce: cambia solo da dove viene il riconoscimento | Accettata |
| D172 | Il dataset di valutazione ha **una sorgente sola**: i casi scritti a mano. Niente casi generati dai giudizi degli utenti | Un dataset vale quanto l'autorità delle sue attese. Un'attesa non esaminata non è un caso in più, è un caso che può far "correggere" un sistema che funziona — ed è successo con il frullatore, scritto a mano da chi aveva il dizionario davanti. I riscontri avrebbero prodotto attese di qualità peggiore e in quantità maggiore, mescolate alle nostre in un'unica percentuale. Una seconda sorgente futura avrà un file e una percentuale suoi | Accettata |
| D171 | Quando un caso fallisce, la valutazione mostra **dove portavano i documenti recuperati**, non solo l'attesa | Un'attesa sbagliata e un recupero fallito producono la stessa riga, e nella modalità senza modello non c'è nemmeno la risposta a distinguerli. Col frullatore ho accusato il recupero di un errore che era mio: il sistema trovava la voce giusta e più specifica. Il costo di un dataset sbagliato è che si "corregge" un sistema che funziona | Accettata |
| D170 | Il tipo di corrispondenza dichiarato dal modello viene **verificato dal codice** dove è verificabile: se il nome del documento nomina l'oggetto, è `stesso_oggetto`, comunque il modello abbia voluto chiamare la relazione | Da quando la presentazione mostra l'etichetta all'utente (D163), sbagliarla è dire una frase falsa. Per un divano a Napoli il documento scelto era proprio "Divani" e il modello ha dichiarato "categoria": il messaggio negava che il comune elencasse l'oggetto mentre la fonte citata era la sua pagina dedicata. La direzione opposta (una voce che *contiene* l'oggetto) richiede il senso delle parole e resta al prompt. È D83 applicato all'etichetta invece che alla scelta | Accettata |
| D164 | Le **essenziali** delle formulazioni entrano sempre, le aggiuntive riempiono i posti che restano; il tetto sale da 5 a 7 | Un elenco unico ordinato per specificità si è rotto due volte allo stesso modo: la domanda col materiale (forchetta, v0.37.0) e quella con la sola categoria (microonde, v0.40.2) stavano in coda e il tetto le tagliava proprio nei casi in cui servivano. Le quattro essenziali coprono i quattro modi in cui il dizionario nomina le cose: per oggetto, per oggetto con contesto, per materiale, per categoria | Accettata |
| D165 | La domanda estesa usa al massimo **due materiali** | Il modello ne elenca volentieri quattro; una domanda di cinque parole in cui l'oggetto è una parola sola parla di *di cosa è fatto* e non di *cos'è*, e la ricerca si sposta sui materiali. È la stessa causa di D80, misurata su un caso nuovo | Accettata |
| D166 | La **procedura di smaltimento** si attacca al *canale*, non alla destinazione né alla voce | Nove coppie (comune, canale) invece di 902 voci: si scrivono a mano una volta e si versionano. Il canale è già nei dati (`destinazione.canale`) e distingue cinque **gesti** diversi, non cinque etichette. Per un terzo del dizionario di Napoli "va in X" è vero e insufficiente: 195 voci finiscono in un'isola ecologica, 57 chiedono una prenotazione | Accettata |
| D167 | Le alternative si ordinano per **sforzo**, e la raccolta ordinaria sparisce quando ci sono altri canali | 115 voci di Napoli hanno destinazioni su canali diversi, e non sono equivalenti per chi deve muoversi: buttare nel sacco è diverso dal caricare un microonde in macchina. Spiegare anche il cassonetto occuperebbe il posto di ciò che invece va spiegato | Accettata |
| D168 | Le procedure **non contengono** indirizzi, orari e numeri di telefono, e una colonna `da_verificare` dichiara cosa manca | Sono dati che il progetto non ha ancora estratto dalla fonte. Inventarli sarebbe peggio che ometterli: una procedura verosimile e sbagliata manda una persona a un cancello chiuso. Due test lo impediscono per costruzione, cercando orari e numeri nel testo | Accettata |
| D169 | Al livello 3 si indica il **centro di raccolta** invece di fermarsi a "non lo so" | Chi ha l'oggetto in mano deve comunque buttarlo da qualche parte. Non è indovinare la destinazione — quello resterebbe scorretto — è dire dove si chiede: il centro di raccolta accetta le tipologie che il dizionario non elenca | Accettata |
| D162 | Il prompt di scelta dichiara che una voce **fratello** — un altro oggetto della stessa categoria — non è una corrispondenza, e che `categoria` vale solo se la voce *contiene* l'oggetto | Per un microonde il modello ha scelto "Bistecchiera elettrica" dichiarando `categoria`, motivandola con "è un elettrodomestico da forno, come il microonde": il "come" è la spia, perché descrive una somiglianza fra pari e non un'appartenenza. La definizione nel prompt era giusta ma senza controesempio, e la regola sui nomi collettivi (D151) ha reso il modello più disposto a dire `categoria` | Accettata |
| D163 | La presentazione distingue `stesso_oggetto` da `categoria` e `sinonimo`: "il comune elenca proprio questo oggetto" solo per il primo | Con una corrispondenza per categoria la frase afferma più di quanto il sistema sappia, e la fonte citata rimanda a un altro oggetto. Una frase falsa è peggio di una risposta approssimativa: toglie all'utente il motivo per dubitare e per usare il pollice giù | Accettata |
| D161 | L'interfaccia mostra la **legenda dei contenitori del comune**, raggruppati per canale | Una risposta come "Multimateriale" non dice niente a chi non conosce i contenitori del suo comune, e l'elenco è anche il modo più onesto di dichiarare i limiti del sistema: ciò che non è in lista, l'assistente non può indicarlo. Il raggruppamento per canale è la distinzione che cambia il gesto: il porta a porta si fa da casa, il centro di raccolta richiede di spostarsi | Accettata |
| D116 | Il tracciamento su MLflow **non è mai bloccante** e fallisce in fretta (tre secondi, un solo tentativo) | Serve a capire come va il sistema, non a farlo funzionare. Senza i limiti sui tentativi il client riprova per minuti e la risposta all'utente resta appesa | Accettata |
| D117 | Delle foto si registra solo l'**impronta**, mai l'immagine | Due richieste sulla stessa foto si riconoscono, ma l'immagine non lascia il computer di chi l'ha scattata: è coerente con un progetto che gira in locale | Superata da D124, per decisione di Stef |
| D118 | I prompt restano file in git; il registro di MLflow li **collega alle run** che li hanno usati | La verità e il diff stanno in git; MLflow serve a sapere quale versione ha prodotto un certo risultato | Superata da D126: il registro collega i prompt alle tracce, non più alle run |
| D119 | Le sonde coprono tre famiglie: codici materiale, parafrasi d'uso e controlli facili | Senza le prime due il banco di prova misura solo i casi comodi; senza i terzi non ci si accorge di una rottura | Accettata |
| D114 | I candidati arrivano al modello **ordinati per somiglianza** | Il modello legge un elenco, e l'ordine è un'informazione che prima gli veniva nascosta | Accettata |
| D115 | Se un documento **nomina proprio l'oggetto** riconosciuto, vince su quello generico, e la preferenza la applica il codice | Davanti a un cartone della pizza il modello ha scelto "Cartone da imballaggio" mentre "Cartone per pizze" era il primo risultato con il punteggio più alto | Accettata |
| D112 | I **codici materiale** si agganciano in modo esatto con un'espressione regolare, non con una ricerca | Un codice ("PAP 21") è un identificatore, non un testo: era l'unico caso in cui il lessicale batteva il semantico, e tre righe lo risolvono meglio di duecento | Accettata |
| D113 | L'agente non legge più dal relazionale a tempo di risposta: tutto ciò che serve è nel payload del documento | Superata la divisione "Qdrant trova, SQLite risponde" (D61): con le destinazioni nel testo e nel payload, il backend interroga un archivio solo. SQLite resta il punto di arrivo dell'ETL, da cui i documenti si costruiscono | Accettata |
| D61 | Nel payload di Qdrant solo ciò che serve a cercare; destinazioni, condizioni e provenienza restano in SQLite | Superata da D113, per decisione di Stef: le destinazioni entrano nel testo indicizzato e nel payload. Il rischio di due verità è chiuso dalla ricostruzione totale | Superata da D113 |
| D107 | L'unità indicizzata diventa il **documento**: uno per oggetto con tutte le sue varianti, uno per ciascuna voce delle regole, uno per destinazione (non indicizzato) | Le vecchie schede erano frammenti di due o tre parole in italiano storto ("Scarpe utilizzabile", "Carta unto"): un embedding calcolato lì discrimina male. Con un documento per oggetto il modello riconosce l'oggetto e la variante la sceglie il codice | Accettata |
| D108 | Le **destinazioni entrano nel testo indicizzato**; la risposta però si legge dal payload strutturato | Decisione di Stef. Il rischio di due verità che divergono è chiuso dalla ricostruzione totale: indice e database nascono dallo stesso comando | Accettata |
| D109 | Le regole di categoria restano **corte e separate**, una per voce, con la polarità dentro la frase | Un testo lungo che mescola ammessi ed esclusi produce un embedding medio che non somiglia a nulla. E l'embedding non conosce il campo `polarita`: senza il "non" nel testo, un divieto si cerca come un'ammissione | Accettata |
| D110 | Un documento per destinazione esiste ma **non si indicizza**: serve a spiegare la risposta di livello 2 | Utile come contesto, inutile come unità di ricerca | Accettata |
| D105 | La correzione per condizione guarda anche le voci **affini**, non solo gli omonimi della voce scelta | A Torino il modello ha scelto "Scatole in cartone o cartoncino" mentre "Cartone da pizza" era fra i candidati: gli omonimi della voce scelta erano vuoti e nessuna correzione scattava | Accettata |
| D106 | Poche **equivalenze fra condizioni**, verificate sui dati dei due comuni: unto ≈ sporco, vuoto ≈ senza residuo | Napoli scrive "unto", Torino "sporco": lo stesso stato con parole diverse. Restano un elenco corto e controllato, non un dizionario di sinonimi generico | Accettata |
| D103 | Le parole dell'utente diventano **domande per l'indice**, non solo contesto per il modello | Chi scrive "cartone della pizza unto" ha appena detto cosa cercare. Prima quel testo arrivava solo al modello, e una descrizione precisa non aiutava il recupero | Accettata |
| D104 | Nel riconoscimento, ciò che dice l'utente **vince** sull'impressione del modello | Davanti a un cartone della pizza il modello ha risposto "scatola", ignorando l'utente. L'utente l'oggetto ce l'ha in mano, il modello vede una fotografia | Accettata |
| D101 | Se l'utente dichiara una condizione, la scelta fra voci omonime la fa il **codice**, non il modello | "È unto" manda il cartone nell'organico e quello pulito nella carta: la differenza fra le due risposte è l'intero scopo dell'applicazione, e il modello aveva scelto la variante sbagliata | Accettata |
| D102 | Il confronto fra condizione e testo dell'utente usa la radice delle parole e tiene conto della negazione | L'utente scrive al plurale e la condizione è al singolare ("non utilizzabili" contro "non utilizzabile"); e "unto" non deve risultare menzionato in "non è unto" | Accettata |
| D100 | Non si chiede una condizione già nota, né si ripete una domanda a cui l'utente ha risposto | L'utente aveva scritto "cartone della pizza unto" e l'agente chiedeva comunque "unto oppure pulito?"; rispondendo, la stessa domanda tornava identica. Un assistente che non ascolta è peggio di uno che non sa | Accettata |
| D93 | Il chiarimento riguarda solo gli omonimi della voce **scelta** | Chiedere "utilizzabile o non utilizzabile?" dopo aver scelto "Stivali" confonde: quella condizione apparteneva a "Scarpe", un'altra voce presente fra i candidati | Accettata |
| D91 | Il chiarimento viene tenuto solo se è davvero una domanda (almeno dieci caratteri e un punto interrogativo) | Il campo è facoltativo e il modello lo riempie comunque: ha risposto "0", che mostrato all'utente sarebbe incomprensibile | Accettata |
| D87 | I prefissi di EmbeddingGemma **restano attivi**: misurato, non supposto | Con i prefissi 10 sonde su 14, senza 9; "tetrapak" si trova solo con i prefissi. L'ipotesi che Ollama li applicasse già da sé è smentita dai numeri | Accettata |
| D88 | Preposizioni e articoli si tolgono dalla ricerca lessicale; "non" resta | "cartone della pizza unto" falliva perché "dell" compare in "Polvere dell'aspirapolvere": la ricerca in AND trovava quel documento e non ripiegava su OR. "non" invece distingue "Scarpe utilizzabile" da "Scarpe non utilizzabile" | Accettata |
| D89 | Ogni formulazione porta fra i candidati i propri **primi due** risultati, con un tetto di 12 candidati | Con otto classifiche la fusione premia chi compare in molte. Due posizioni e non una perché la misura lo ha mostrato: "calzatura" trova "Scarpe utilizzabile" al secondo posto, dietro "Laccio per scarpe". Il tetto evita di allungare il prompt della scelta, che su CPU si paga | Accettata |
| D92 | Fra le formulazioni c'è **oggetto più categoria** ("sandalo calzatura") | Una parola sola e ambigua recupera rumore ("Salse", "Sdraio", "Cuffia"): la categoria dà al modello di embedding il contesto che gli manca | Accettata |
| D86 | Il retrieval si misura con le **sonde**: domande note e scheda attesa, con la posizione raggiunta da ciascun metodo | Guardando i primi cinque risultati non si sa se la scheda giusta sia sesta o assente. Senza quel dato ogni modifica al recupero è un tentativo alla cieca | Accettata |
| D84 | Sinonimi e categoria sono **obbligatori** nello schema di uscita del riconoscimento | Lasciati facoltativi il modello li omette, e la ricerca perde il ponte col vocabolario della fonte: è successo alla prima prova con la ciabatta | Accettata |
| D85 | La descrizione passata alla scelta include categoria e sinonimi, e il prompt dichiara la categoria **vincolante** | Senza, un nome ambiguo viene reinterpretato: davanti a "ciabatta" il modello ha risposto "è un tipo di pane" e ha scelto una busta per alimenti | Accettata |
| D83 | Il modello dichiara il **tipo di corrispondenza** (stesso oggetto, sinonimo, categoria, solo materiale, nessuna) e l'agente scarta le ultime due | Non ci si affida alla prosa né alla buona volontà: il modello si impegna su un'etichetta e la politica la applica il codice. La regola sta nell'agente, non nell'adattatore Ollama, così vale per qualunque modello | Accettata |
| D80 | L'indice si interroga con **più formulazioni** della stessa domanda (solo oggetto; oggetto più materiali), fuse con RRF | I materiali nella stessa domanda trascinano la ricerca verso ciò che è *fatto di* quel materiale: "sandalo gomma plastica tessuto" restituisce gomme da masticare e righelli, e il sandalo sparisce | Accettata |
| D81 | Il prompt di scelta vieta la corrispondenza per solo materiale e dichiara che "nessuna voce" è una risposta corretta | Davanti a un sandalo il modello aveva scelto "molletta in plastica da bucato", motivandolo con il materiale condiviso: indicare il contenitore sbagliato è peggio che ammettere di non sapere | Accettata |
| D79 | Modello di visione predefinito: **gemma3:4b**, non Gemma 4 | Su questa installazione gemma4 (e2b ed e4b) non interpreta le fotografie: stessa immagine, stesso codice, gemma3:4b descrive "una Adidas slide blu con tre strisce bianche" e gemma4 "un modulo standardizzato". Il modello resta un parametro del `.env`: quando la sua parte visiva funzionerà, si torna indietro cambiando una riga | Accettata |
| D78 | Le immagini vengono ridimensionate e ricodificate (RGB, JPEG, lato lungo 1024) prima dell'invio | Il modello le rimpicciolisce comunque: mandarle intere costa byte e non aggiunge dettaglio. La conversione in RGB elimina inoltre canali alfa e scale di grigio, che possono essere interpretati male | Accettata |
| D77 | Il canale immagine si verifica con immagini dal **contenuto noto**: tre colori pieni e una divisa a metà, con domanda sulla posizione | Davanti a una foto non si distingue "vede male" da "non vede". Una sola domanda sul colore però si può indovinare: tre colori e una posizione no | Accettata |
| D76 | La confidenza restituita dal modello viene normalizzata in 0-1 | I modelli rispondono spesso in percentuale ("100"): senza normalizzare, ogni soglia sarebbe inutile | Accettata |
| D74 | Il contesto per il secondo giro torna al client ed è opaco | Backend senza stato, come deciso per il prototipo: niente sessioni da gestire e scadere | Accettata |
| D69 | L'autorecupero accetta le prime 3 posizioni, non solo la prima | Le fonti contengono quasi sinonimi ("Televisore a tubo catodico" e "TV a tubo catodico") che si contendono legittimamente la testa della classifica. Fuori dalle prime posizioni, invece, c'è un vero disallineamento | Accettata |
| D68 | Un controllo che fallisce deve dire **cosa** è fallito | L'autorecupero segnalava `29/30` senza indicare quale scheda: un avviso che non permette di agire costringe a indagare a mano ogni volta | Accettata |
| D67 | La polarità è parte della risposta: una regola `escluso` si presenta come "NO <contenitore>" | Mostrare solo il nome della destinazione ribalta il significato: "Cartoni per bevande → imballaggi in plastica" leggeva come un'indicazione quando è un divieto | Accettata |
| D56 | Il vettorizzatore è dietro un'interfaccia (`Vettorizzatore`) | Permette i test senza rete e il cambio di modello senza toccare la ricerca | Accettata |
| D57 | Un vettore si ricalcola solo se il testo della scheda è cambiato (impronta SHA-256) | Il calcolo è la parte lenta della pipeline: rieseguire dopo una modifica parziale deve costare poco | Accettata |
| D58 | Prompt distinti per documento e interrogazione, come previsto da EmbeddingGemma | Il modello è addestrato con quei prefissi: usarli migliora il recupero e non costa nulla | Accettata |
| D52 | La ricerca riduce ogni termine alla radice togliendo la vocale finale alle parole lunghe | Con i trigrammi il termine deve essere una sottostringa: "bicchiere" non troverebbe "Bicchieri". È l'alternativa allo stemming, che FTS5 non offre per l'italiano | Accettata |
| D53 | Ricerca prima in AND, poi in OR se non trova nulla | La precisione viene prima, ma nessun candidato è peggio di candidati imperfetti: la scelta finale è comunque del modello fra opzioni reali | Accettata |
| D54 | Delle regole si indicizza solo `testo`, non `dettaglio` | Per gli esclusi di Torino il dettaglio è la frase intera: indicizzarla renderebbe ogni oggetto escluso raggiungibile con le parole di tutti gli altri | Accettata |
| D49 | I metadati delle destinazioni (canale, colore, flussi) stanno in `data/riferimento/destinazioni.csv`, versionato | Erano cablati in uno script dimostrativo: sono dati curati a mano, come le trascrizioni, e vanno trattati come tali | Accettata |
| D50 | Il caricamento verifica che ogni destinazione usata sia dichiarata **e** che ogni destinazione dichiarata sia usata | Il primo controllo blocca i dati zoppi, il secondo impedisce al file di riferimento di divergere dai dati. Entrambi si controllano solo sui comuni presenti | Accettata |
| D51 | `demo.py` rimosso, sostituito da `carica.py` | La dimostrazione dello schema su un campione non serve più ora che esiste il caricamento vero | Accettata |
| D48 | La coerenza della documentazione è verificata dai test, non dalla memoria | Un promemoria si dimentica; un test rosso blocca. I test coprono solo ciò che è verificabile meccanicamente: il resto resta responsabilità di chi scrive | Accettata |
| D47 | Lo slug di Torino deriva dal nome della voce, non dalla posizione nel PDF | Le decisioni restano valide anche se l'estrazione cambia l'ordine delle voci | Accettata |
| D43 | La corrispondenza scheda/frazione → destinazione è dichiarata esplicitamente, in un punto solo, e verificata contro le destinazioni che compaiono nelle voci | I nomi non coincidono ("Carta e Cartone" nella frazione, "Carta e Cartoncino" nelle voci): una regola agganciata a un contenitore inesistente non verrebbe mai raggiunta dalla ricerca | Accettata |
| D44 | Le celle e gli elenchi delle regole **non** si spezzano in oggetti singoli | "Piatti, bicchieri e bicchierini da caffè in plastica anche sporchi": separare perderebbe la qualificazione comune, lo stesso errore corretto in D27b. Trigrammi ed embedding lavorano bene sul testo intero | Accettata |
| D41 | I dati presenti nella fonte ma non estraibili si trascrivono a mano in un CSV versionato, con `origine: trascrizione_manuale` | Affidabile ma non riproducibile da uno script: va distinto da ciò che l'estrattore ricava da solo, e se domani la fonte lo pubblica come testo si sa quali righe sostituire | Accettata |
| D42 | Le **assenze verificate** si registrano come dato | "Questa frazione non pubblica esclusioni" è un'informazione, diversa da "non le abbiamo ancora cercate": spegne l'avviso solo dove è stato fatto il controllo | Accettata |
| D38 | A Torino il ruolo di ogni riga è dato dal **font**, non dalla posizione (Bold 12 titolo, Light 8 celle, Medium 8 frase delle esclusioni) | Più robusto delle coordinate: regge le schede con impaginato diverso | Accettata |
| D39 | Le frasi del riquadro si classificano in *elenco* ("X, Y e Z NON vanno...") e *avvertenza* ("Non gettare l'olio negli scarichi"); una forma non riconosciuta fa fallire l'estrazione | Solo la prima elenca oggetti esclusi; separare anche la seconda produrrebbe esclusioni inventate | Accettata |
| D40 | Una cella più lunga di 120 caratteri rivela un paragrafo, non una griglia: la scheda non produce ammessi | Farmaci, Oli esausti e Ingombranti sono schede descrittive senza elenco di oggetti | Accettata |
| D33 | Un controllo segnala le frazioni con ammessi ma nessun escluso, distinguendo se esiste un'immagine informativa | Una fonte muta può essere un markup non gestito o un limite reale della fonte: vanno distinti | Accettata |

### Valutazione

| # | Decisione | Motivazione | Stato |
|---|---|---|---|
| D173 | I casi vivono in **tre insiemi separati** (`regressioni`, `campione`, `assenti`), un file per insieme, e ognuno ha le sue misure: le regressioni si leggono pass/fail, il campione in percentuale, gli assenti con le astensioni | Le regressioni sono, per costruzione, i punti in cui il sistema aveva già sbagliato: una percentuale calcolata lì misura la storia dei difetti, non il sistema. Fino alla v0.42.0 il numero pubblicato era esattamente quello. È D172 portato alle sue conseguenze: non si mescolano attese di autorità diverse, e nemmeno scopi diversi | Accettata |
| D174 | Le attese del campione vengono dal **database**; a mano si scrive solo la **domanda**, e non può mai coincidere col nome della voce | Per una voce del dizionario la risposta giusta *e'* la fonte: riscriverla a mano aggiunge solo occasioni di sbagliare (il frullatore, D171). Ciò che una macchina non può inventare è come una persona chiama l'oggetto. La regola anti-tautologia ha un test, e alla prima compilazione ha preso tre casi su cinquantadue: erano le vecchie sonde "giornale", "bicchiere di vetro", "bicchieri di vetro" | Accettata |
| D175 | Il campione è **stratificato** su comune, canale e numero di alternative, con **seme fisso** e quota minima di uno per strato | Il sistema non si comporta allo stesso modo ovunque: gli errori osservati sono tutti su canali diversi dalla raccolta ordinaria. Una proporzione pura cancellerebbe il ritiro a domicilio, che è una voce su ventisette ed è dove il sistema ha sbagliato due volte. Il seme fisso permette di dire, in una relazione, di quale campione si parla | Accettata |
| D176 | La risposta si misura con due numeri: **`contenitore_corretto`** (nessuna destinazione fuori dalle attese) e **`copertura`** (quante delle attese sono state dette), al posto dell'uguaglianza esatta degli insiemi | Sono due errori che si riparano in punti diversi e pesano diversamente: mandare qualcuno nel cassonetto sbagliato è un danno, perdere il ritiro a domicilio è un disagio. Con l'uguaglianza esatta la risposta del microonde — vera ma incompleta — contava come "Organico", che è tutt'altra cosa | Accettata |
| D177 | Il recall si legge come **curva** (`@1`, `@k/2`, `@k`) e la **posizione media è rimossa** | La media era calcolata sui soli casi trovati, quindi peggiorava quando una modifica faceva finalmente uscire un documento difficile in settima posizione: una metrica che punisce i miglioramenti. La curva usa lo stesso dato e dice la cosa utile, cioè se il problema è l'indice o l'ordinamento | Accettata |
| D178 | Un caso può avere **attese vuote** se dichiara `livello_atteso: 3`, e le due astensioni si leggono **in coppia** | Il difetto classico di un RAG è rispondere comunque, e senza casi negativi non ha un numero. L'attesa vuota dev'essere una dichiarazione e non una riga scritta a metà, da cui il vincolo sul livello. La coppia serve perché l'astensione corretta, da sola, si massimizza tacendo sempre: un sistema muto non è prudente | Accettata |
| D179 | Ogni esecuzione salvata porta la **configurazione che l'ha prodotta**, e `--confronta` avvisa se le due non coincidono | Senza, si confronta una run a `k=8` con una a `k=12` e si legge la differenza come merito della modifica. Si riusa `agente.configurazione()`, lo stesso oggetto che forma la versione dell'app nelle tracce: valutazione e osservabilità restano allineate per costruzione. L'avviso non blocca, perché a volte confrontare due configurazioni è proprio ciò che si vuole | Accettata |
| D180 | Il recupero dell'agente diventa **pubblico** (`recupera`), e le **sonde spariscono** | La valutazione chiamava `_recupera`, un metodo privato: una dipendenza che nessuno dichiara si rompe in silenzio al primo refactoring. Le sonde misuravano una versione più debole della stessa cosa (attesa come sottostringa, nessuna destinazione): le loro 28 domande, che erano il pezzo costoso, sono diventate casi del campione. Stessa logica di D111 | Accettata |
| D181 | Le foto si valutano **due volte** — dal riconoscimento vero e dall'oggetto dichiarato — e i tempi si riportano come **p50/p90 col rango più vicino** | Un giro solo direbbe che la risposta è sbagliata, non da dove viene l'errore; il secondo giro costa `rispondi` e non `analizza`, cioè secondi contro minuti. Sui tempi la media di dieci foto veloci e una lenta descrive una situazione che non è capitata a nessuno, e il rango più vicino garantisce che il numero pubblicato sia un tempo davvero cronometrato | Accettata |
| D182 | Ogni esecuzione della valutazione è anche una **run MLflow**, in un esperimento separato da quello delle conversazioni, e non è mai bloccante | I file JSON bastano per confrontare due esecuzioni, non per guardare la serie storica di dieci. L'esperimento separato perché le tracce sono osservazioni di ciò che è successo a un utente, le run sono misure ripetibili su un dataset fermo: insieme renderebbero illeggibili entrambe le liste. Non bloccante per D116: una misura non si perde perché manca un servizio di osservabilità | Accettata |
| D183 | I documenti si arricchiscono con **dati della fonte** — il canale quando non è la raccolta ordinaria, i flussi di materiale che il testo non nomina già, e le regole di categoria che nominano l'oggetto — e **mai con descrizioni generate da un modello** | I documenti oggetto sono corti (57 caratteri di media) ed è il caso in cui l'espansione rende di più. Farla scrivere a un modello però sbaglierebbe due volte: direbbe che il bicchiere di vetro è riciclabile, che a Napoli è falso, mettendo nel testo indicizzato una frase che contraddice la fonte (contro D9); e renderebbe "Bicchiere di vetro" e "Bottiglia in vetro" **più simili fra loro**, mentre il difetto da combattere è proprio la confusione fra vicini. L'arricchimento dalla fonte fa l'opposto: al bicchiere aggancia "Nel contenitore Vetro NON va: Bicchieri", che è la frase per cui quella voce non sta nel vetro. Si spegne con `ECOSCAN_ARRICCHIMENTO=no`, perché una modifica al recupero che non si può confrontare con la propria assenza non si sa se ha funzionato | Accettata |
| D184 | La registrazione di una valutazione **non è best-effort**: ignora `ECOSCAN_MLFLOW_ATTIVO`, ripiega su un archivio locale se il server non risponde, e se non riesce nemmeno lì **ferma il comando con errore** | D116 dice che il tracciamento non deve mai bloccare, ed è giusto per le conversazioni: una traccia persa non fa danno, l'utente ha avuto la sua risposta. Una misura è un'altra cosa — si prende una volta, dopo minuti di CPU, e se non viene registrata è persa. Le tre regole seguono da lì. In più: l'esito si salva **sempre** anche su file, senza dover ricordare `--salva`, e `--prova-mlflow` scrive una run minuscola per rispondere in un secondo alla domanda "è il server o è il mio codice?" | Accettata |
| D185 | Ogni caso di valutazione lascia una **traccia** su MLflow, agganciata alla run della misura, con i tag su cui si filtra (caso, insieme, comune, diagnosi, posizione) | Le percentuali dicono *quanti* casi vanno male; la traccia dice *perché quel caso* è andato male — quali domande sono state poste all'indice, quali documenti sono usciti e in che ordine, cosa ha scelto il modello e cosa ha scartato la politica dei materiali. È la stessa traccia di una conversazione vera, quindi si legge con gli stessi occhi. La run si apre **prima** dei casi perché una traccia creata dentro una run le resta agganciata (`mlflow.sourceRun`, verificato su un server vero): registrando alla fine, le tracce resterebbero nell'esperimento senza legame con la misura che le ha prodotte | Accettata |
| D186 | Una procedura può **specializzarsi sulla destinazione**: la riga con la destinazione vince, quella senza resta come ripiego | D166 attacca la procedura al canale, ed è giusto per quasi tutto: nove coppie invece di 902 voci. Ma `contenitore_dedicato` raccoglie farmaci, pile, abiti e olio esausto, che si conferiscono in quattro modi diversi: la procedura generica li elencava tutti e quattro, e per una cintura di pelle diceva anche che l'olio va portato in una bottiglia chiusa. Informazione non richiesta in una risposta non è generosità, è rumore che toglie credito a quella richiesta. Specializzando solo dove serve — sette righe in più — l'economia di D166 resta | Accettata |
| D187 | Il **chiarimento si misura nelle due direzioni**, con un insieme fatto di coppie: lo stesso oggetto senza la condizione (deve chiedere) e con la condizione (non deve) | `domanda_dovuta` da sola si massimizza chiedendo sempre, che è il difetto opposto e altrettanto fastidioso — la stessa ragione per cui le astensioni si leggono in coppia (D178). Le coppie sono un vincolo del dataset, non una buona intenzione: un test fallisce se una voce compare in una direzione sola. Le due diagnosi restano separate perché si riparano in punti diversi: una domanda mancata è una condizione che il codice non ha visto fra le varianti, una di troppo è un testo dell'utente che non è stato letto | Accettata |
| D188 | L'agente chiede anche **di che materiale è**, quando fra i candidati ci sono voci omonime di materiali diversi che portano in contenitori diversi e il riconoscimento non ha dichiarato il materiale | È D73 applicato al materiale invece che allo stato. Il chiarimento nasceva solo dalle **condizioni** di una voce, quindi "bicchiere" a Napoli — di vetro (Non Riciclabile) o di plastica (Plastica e Metalli) — non produceva nessuna domanda: il modello ne sceglieva uno e l'utente non sapeva che la risposta dipendeva da un'informazione che non aveva dato. Nei due dizionari le famiglie di omonimi distinte dal materiale sono **37**. Si chiede solo quando la domanda cambierebbe la risposta: due materiali almeno, con destinazioni diverse | Accettata |
| D189 | Gli omonimi si riconoscono **dai documenti**, confrontando il loro nucleo — il nome senza materiali né parole di servizio — e non dalla domanda dell'utente | `nomina_l_oggetto` pretende che la domanda contenga tutte le parole del nome: è giusto per preferire il documento specifico (D-piu_specifico) e troppo stretto qui, perché "tagliere della cucina" non nomina "Tagliere in legno" e la domanda non nascerebbe. Il confronto fra nuclei è per **inclusione**, così "Vaschette in alluminio" e "Vaschette alimentari in plastica" restano la stessa cosa detta con una parola in più. La famiglia si ancora al documento **scelto**: senza, un candidato qualunque di un altro materiale farebbe nascere una domanda che non c'entra con la risposta | Accettata |
| D190 | La risposta a una domanda sul materiale finisce nei **materiali** del riconoscimento, non nello stato; e una risposta accompagnata da una domanda dovuta è **provvisoria**, quindi non si misura come definitiva | `continua` metteva sempre la risposta nello stato: giusto finché si chiedevano solo le condizioni, inutile per un materiale — il filtro guarda `materiali` e le formulazioni cercano "oggetto + materiale" (D164), quindi la domanda avrebbe cambiato la risposta solo per caso. Sulla misura: l'agente che dice "probabilmente X, ma dimmi di che materiale è" ha fatto la cosa giusta, e pretendere che X sia già la risposta completa lo punirebbe per questo | Accettata |
| D191 | La domanda si giudica **solo quando era in gioco**: se ha risposto una voce diversa da quella che il caso aveva in mente, `chiarimento_corretto` vale `None` e il caso esce dal denominatore | Prima esecuzione con il modello, 25/09: undici mancate domande, di cui **dieci** erano risposte arrivate da un'altra voce — «Barattolo in vetro» per i contenitori di crema, «Tende in stoffa» per le pantofole, «Barattolo in latta» per un piatto. Quelle voci avevano una variante sola e niente da chiedere: contarle come domande mancate dava la colpa al chiarimento di un difetto della **scelta**. Con l'attribuzione corretta `domanda_dovuta` passa da 54,2% a **92,9%**, e il difetto vero — la scelta che prende il documento sbagliato — compare nel suo blocco | Accettata |

### Transform

| # | Decisione | Motivazione | Stato |
|---|---|---|---|
| D24 | Le parentesi vanno classificate, non trattate in modo uniforme | Superata da D25, che ne precisa i significati | Superata da D25 |
| D25 | Le parentesi hanno 5 significati: condizione, sinonimo, esempi, codice materiale, materiale/provenienza | "(40)" è un codice, "(tetrapak)" un sinonimo, "(in Grandi Quantità)" una condizione | Accettata |
| D26 | Le condizioni si estraggono anche fuori dalle parentesi, ovunque nel nome | "Cartone **pulito** per pizze" (carta) vs "Cartone **unto** per pizze" (organico) | Accettata |
| D27 | Le voci composte si separano solo con criteri prudenti; ogni separazione è marcata `da_revisionare` | La virgola indica composizione, condizione o elenco di contesti | Accettata |
| D27b | Mai separare su " o ", né quando la qualificazione sta solo a destra, né sulle locuzioni fisse | " o " indica materiali alternativi ("Guanti in pelle o lana"); "Pentola e padella in acciaio" è un oggetto solo | Accettata |
| D28 | Deduplicazione insensibile a singolare/plurale; destinazioni diverse = conflitto segnalato, mai risolto in automatico | "Assorbente"/"Assorbenti" sono la stessa voce; una contraddizione della fonte non va nascosta | Accettata |
| D28b | Il codice materiale fa parte della chiave di deduplicazione | "Simbolo FOR (50)" e "Simbolo FOR (51)" hanno destinazioni diverse | Accettata |
| D29 | Le voci non reali si scartano per nome | Il dizionario pubblico contiene "Test di esempio" con tre destinazioni | Accettata |
| D30 | Motore del Transform unico, regole per comune in un `Profilo` | "usa e getta" è locuzione fissa a Napoli e condizione a Torino | Accettata |
| D31 | Le parentesi che elencano materiali o provenienza sono condizioni | "Involucro cioccolatini (alluminio)" e "(plastica argentata)" hanno destinazioni diverse | Accettata |

---

## Questioni aperte

Ordinate per priorità.

1. **Regole di categoria.**
   - **Chiuso su entrambi i comuni** (110 regole nel normalizzato).
   - *Napoli*: 5 esclusioni per il Vetro estratte, 6 per l'Umido trascritte a mano dall'immagine, Plastica e Carta verificate come prive di esclusioni.
   - *Torino*: **fatto in v0.6.0**. 10 schede, 30 ammessi, 27 esclusi. Da fare: portare queste regole nel livello normalizzato e collegarle alle destinazioni.
2. ~~Esclusioni mancanti per Umido, Plastica e Carta (Napoli)~~ **Chiuso**: Stef ha letto le tre immagini. Solo l'Umido ha una sezione di esclusioni (6 voci + un avviso generale), trascritte in `data/sorgenti/manuale/napoli_esclusioni.csv`. Plastica e Carta non pubblicano esclusioni: registrate come assenze verificate.
3. **BM25 sparso in Qdrant** (FastEmbed, stemmer italiano): sostituirebbe il trucco della radice con uno stemming vero e permetterebbe la fusione RRF interamente lato Qdrant. FTS5 resta come termine di paragone nella valutazione.
4. ~~**Valutazione**: set di foto etichettate e misura del retrieval~~ **Chiuso in v0.43.0**: recupero, scelta, astensione e tempi hanno i loro numeri, su tre insiemi di casi separati ([valutazione.md](valutazione.md)). Restano due cose, entrambe di lavoro e non di codice: **scattare le venti foto** le cui etichette sono già scritte, e far crescere il campione oltre i 63 casi con `ecoscan-campiona`.
5. ~~**Procedure di smaltimento complesse.**~~ **Chiuso in v0.41.0**: procedura per canale in `data/sorgenti/manuale/procedure.csv`, presentazione a passi, alternative ordinate per sforzo, livello 3 che indica dove chiedere. Resta il contenuto: indirizzi, orari e recapiti mancano, e la colonna `da_verificare` li elenca — dipende dalla questione 6.
6. **Dove andare, a Napoli.** Le isole ecologiche e gli ecopunti sono destinazioni con un indirizzo che il sistema oggi non conosce: la fonte ASIA li pubblica su pagine separate da quelle del dizionario. Serve un terzo estrattore e una tabella `luogo`. Vedi le note sotto.
7. ~~Pagine "Non riciclabile" e "Altre raccolte" di Napoli~~ **Chiuso**: sono davvero prive di elenchi, hanno solo una frase di invito. Non è un difetto dell'estrattore.
8. **Serving**: indici FTS5 a trigrammi, embedding, ricerca ibrida con RRF.
8. **Dove conferire**: 363 voci su 584 a Napoli rimandano a isole ecologiche o ecopunti. Prima o poi l'agente deve dire *dove* si trovano.
9. **Opuscolo PDF di Napoli** (`Asia_Opuscolo_A5_new-1.pdf`): mai consultato, potrebbe contenere regole assenti dal sito.

---

## Annotazioni

Cose imparate che non sono decisioni, ma che conviene ricordare.

- **L'asterisco di Napoli non rimanda a niente.** Sei voci lo portano nel nome ma nessuna pagina ha una nota corrispondente: è un residuo tipografico della fonte, verificato il 12/09/2026. Registrato nelle decisioni, così non lo si ricerca una seconda volta.
- **I conflitti sono una diagnosi del Transform, non dei dati.** Su 902 voci, tutti e 6 i conflitti iniziali erano difetti delle regole: separazioni sbagliate, materiale letto come sinonimo, codice escluso dalla chiave. Corretti quelli, restano zero. Le due fonti, dove si sovrappongono, sono internamente coerenti.
- **Le due fonti hanno difficoltà speculari.** A Torino l'ostacolo è l'estrazione (destinazione codificata in colori e icone), ma i dati sono puliti. A Napoli l'estrazione è facile e i dati sono sporchi. La scelta di due formati complementari ha dato il contrasto giusto.
- **ASIA pubblica poche esclusioni, e quasi solo come grafica.** Testo solo per il Vetro; dentro l'immagine per l'Umido; per Plastica e Carta non esistono proprio. Torino ne pubblica 27 contro le 11 di Napoli: la stessa informazione, con profondità molto diversa. Una fonte può essere incompleta *per come è pubblicata*, non per come la leggiamo: il controllo che distingue i due casi è ciò che ha permesso di capirlo in un giro solo.
- **Le esclusioni spiegano il dizionario.** La pagina del vetro di Napoli esclude bicchieri, piatti, pirofile e lastre: esattamente le voci che nel dizionario finiscono nel non riciclabile. Ciò che sembrava incoerenza è una regola dichiarata.
- **Divergenze fra comuni utili da citare**: bicchiere di vetro (Napoli non riciclabile, Torino vetro); tappo di sughero (Napoli organico, Torino centro di raccolta o organico); pentole e padelle (Napoli plastica e metalli, Torino centro di raccolta). Una convergenza: il vetro dei profumi non è riciclabile in entrambi.
- **Due comuni nominano lo stesso stato con parole diverse.** Napoli scrive "unto", Torino "sporco": una correzione basata sul confronto letterale funziona in un comune e non nell'altro. È il tipo di differenza che si scopre solo provando entrambi.
- **Le informazioni dell'utente vanno usate in tutti i punti in cui servono, non in uno solo.** Il testo "è unto" veniva passato al modello di visione e alla scelta, ma non alla ricerca: le domande poste all'indice erano "scatola", "cartone", "confezione". Un dato raccolto e non usato è peggio di un dato mancante, perché sembra di averlo già sfruttato.
- **Togliere una domanda senza correggere la scelta peggiora le cose.** Smesso di chiedere "unto o pulito?", il sistema ha cominciato a rispondere "Carta e Cartoncino" a chi aveva scritto "è unto": prima l'errore era visibile, dopo no. Una decisione che cambia la risposta non va lasciata al modello se i dati bastano a prenderla.
- **Chiedere ciò che è già stato detto vanifica la conversazione.** Il chiarimento nasceva dai dati (omonimi con destinazioni diverse) senza guardare ciò che l'utente aveva scritto né lo stato visto nella foto. E `continua` ricalcolava la domanda da zero, quindi la riproponeva identica: un giro senza uscita.
- **I nomi degli oggetti sono ambigui, e il modello sceglie il senso sbagliato.** "Ciabatta" in italiano è una calzatura e un tipo di pane: il modello ha imboccato la seconda strada e ha scelto "busta per alimenti", dichiarando pure la corrispondenza come "sinonimo". La categoria, resa obbligatoria e mostrata anche nella scelta, chiude quella strada.
- **Un campo facoltativo in uno schema di uscita è un campo che il modello ometterà.**
- **Una misura troppo indulgente è peggio di nessuna misura.** La sonda dichiarava che "calzatura" trovava "Scarpe" al primo posto; l'agente, con la stessa domanda, mostrava "Laccio per scarpe". Erano lo stesso risultato: il confronto per sottostringa accettava la parola dentro un altro oggetto. Un banco di prova che promuove risultati sbagliati indirizza il lavoro nella direzione opposta a quella giusta.
- **Due delle quattro sonde fallite erano sbagliate io.** Mi aspettavo "Cartone unto per pizze", ma il Transform sposta la condizione in fondo e il testo indicizzato è "Cartone per pizze unto". Un banco di prova va verificato contro i dati veri, altrimenti misura sé stesso.
- **Il vocabolario del modello e quello della fonte non coincidono.** Il modello riconosce "sandalo", il dizionario di ASIA elenca "Scarpa", "Scarpe", "Pantofole di stoffa", "Stivali". Cercando "sandalo" da solo, la ricerca semantica ha restituito "Salse", "Sdraio" e "Scaldabagno": parole che somigliano nella forma, non nel significato. È il limite di una ricerca semantica su testi di una parola sola, e si risolve chiedendo al modello i sinonimi, che conosce.
- **Un riconoscimento giusto non basta: conta come si formula la domanda.** Gemma 3 ha riconosciuto correttamente "sandalo, gomma, plastica, tessuto", ma la ricerca con quella frase intera ha restituito gomme da masticare e righelli di plastica. Il riconoscimento era buono, il retrieval no.
- **Gemma 4 dichiara `vision` ma non interpreta le fotografie.** Supera le prove su immagini sintetiche semplici (un colore pieno, indovinabile) e fallisce su tutto il resto: tre colori su tre sbagliati, la domanda sulla posizione sbagliata, e davanti a qualsiasi foto risponde "un modulo" o "una griglia di blocchi". Gemma 3 da 4 miliardi di parametri, con **lo stesso codice e gli stessi byte**, descrive correttamente una ciabatta Adidas usurata e una bottiglia di acqua minerale. Il confronto fra due modelli sullo stesso ingresso è ciò che ha chiuso l'indagine.
- **Il modello non riceveva le immagini.** Foto diverse (una bottiglia, una ciabatta) producevano la stessa descrizione: "una griglia di blocchi con numeri e testo". Due descrizioni identiche per immagini diverse sono la prova che l'immagine non arriva; una sola descrizione sbagliata non lo sarebbe stata. Da qui prima `--descrivi` e poi `--diagnostica`, che usa un'immagine dal contenuto noto.
- **Un processo lungo senza avanzamento sembra rotto.** L'estrazione di Napoli dura 15 minuti e non stampava nulla: Stef l'ha giustamente creduta bloccata. Vale per ogni comando che superi qualche secondo.
- **In `.gitignore` non esistono commenti a fine riga.** `*.db  # nota` è un nome di file letterale: il database è finito in git per questo. Ora c'è un test che lo impedisce.
- **ASIA ha voci quasi gemelle con destinazioni diverse.** "Televisore a tubo catodico" va all'isola ecologica **o all'ecopunto elettrodomestici**, "TV a tubo catodico" solo all'isola; per lo schermo piatto invece le due versioni concordano. La deduplicazione non poteva accorgersene, perché i nomi differiscono e le destinazioni non coincidono. È emerso dall'autorecupero dell'indice vettoriale, cioè da un controllo tecnico che ha scoperto un problema di dati.
- **Le celle della scheda "Pile" di Torino non sono oggetti.** Sono formati di batteria ("C", "AA", "AAA", "D", "Button"): testi di una o due lettere, che nessun metodo di ricerca può distinguere. Non è un difetto dell'indice ma un limite della fonte, e la verifica ora lo segnala come nota invece di confonderlo con un errore.
- **Una regola di esclusione mostrata senza polarità dice l'opposto del vero.** Nella prima prova di ricerca, "Cartoni per bevande (tipo Tetra Pak®) → imballaggi_plastica" sembrava un'indicazione di conferimento, mentre è la riga che li **esclude** dalla plastica. Vale per ogni punto in cui una regola verrà mostrata all'utente o passata al modello.
- **Committare senza aver visto i test verdi è un errore anche quando la correzione è banale.** È successo con v0.21.0: il modulo non conteneva la costante che il test importava, e il commit è partito lo stesso. La riga dei test va letta, non lanciata e basta.
- **Un guasto silenzioso nel tracciamento è per definizione difficile da notare.** MLflow rispondeva 403 per la validazione dell'header Host, e il tracciamento restava spento: l'applicazione funzionava benissimo, e l'unico segno era una riga nei log del backend. È il prezzo di aver reso il tracciamento non bloccante, e va messo in conto guardando i log ogni tanto.
- **Un Dockerfile va costruito, non solo letto.** Mancava `COPY README.md`, che il `pyproject.toml` dichiara come `readme`: la costruzione del pacchetto falliva con un errore di hatchling che non nominava mai il Dockerfile. Ora due test leggono il pyproject e verificano che ogni file dichiarato sia copiato e non escluso dal `.dockerignore`.
- **I comandi vanno provati eseguendoli, non solo leggendoli.** `--diagnostica` usava una variabile definita più sotto: un errore che nessun test coglieva perché nessuno eseguiva quel ramo. Ora tre test lanciano `main()` con la diagnostica sostituita da una finta.
- **Un test che dipende dall'ambiente di chi lo esegue non è un test.** `test_il_file_env_viene_letto` passava da me e falliva sul portatile di Stef, perché ereditava le variabili della macchina. Ora l'ambiente del sottoprocesso viene ripulito di tutte le `ECOSCAN_*`.
- **Il riconoscimento giusto non basta.** Nel caso della forchetta il modello aveva visto l'acciaio e l'aveva perfino scritto nel motivo: il guasto era a valle, fra recupero e scelta. Prima di ritoccare i prompt conviene guardare dove si rompe davvero la catena.
- **Un filtro va provato sui dati veri, non sugli esempi che lo hanno ispirato.** Il primo filtro sul materiale scartava "Scatolette per tonno" perché leggeva il nome del contenitore ("Plastica e Metalli") come materiale dell'oggetto. Applicarlo agli undici candidati reali di `/cerca` l'ha mostrato in un secondo.
- **La provenienza si perdeva nel Transform.** Il grezzo di Napoli ha l'URL di ogni voce e quello di Torino la pagina del PDF: nessuno dei due arrivava al livello normalizzato, e le risposte di livello 1 restavano senza fonte pur avendola a disposizione.
- **Cambiare il payload dei documenti costringe a rivettorizzare.** Aggiungere fonte e riferimento agli oggetti significa rilanciare `ecoscan-vettorizza`, non solo `ecoscan-carica`: l'indice porta una copia del payload.
- **Il client di MLflow riprova per minuti un server spento anche sul registro dei prompt**, non solo sulle run: i limiti di attesa ora stanno in una funzione sola (`limita_attese`), usata sia dal tracciatore sia da `ecoscan-prompt`.
- **Uno span aperto fuori da un turno diventa una traccia a sé.** `rispondi`, chiamato dalla valutazione, avrebbe riempito l'esperimento di tracce orfane di solo retrieval: gli span si registrano solo dentro `analizza` e `continua`.
- **Server MLflow e client erano a dieci versioni di distanza** (3.6.0 contro 3.16.1) senza che nulla se ne accorgesse: con le run non serviva nulla di recente, con le tracce sì.
- **Trappole già incontrate, da non ripetere**: i nodi di testo frammentati di Elementor; il match di "ecc" dentro "appare**cc**hi"; gli slug che finiscono con un numero che è un codice materiale e non un contatore; un test che passava solo perché la fixture era più semplice della realtà.

---

## Cronologia

### v0.48.1 — 25/09/2026

**Prima esecuzione della domanda sul materiale, e tre difetti da correggere.** Quarantanove
casi, 34 secondi l'uno. Il meccanismo funziona — tredici domande su quattordici dove era in
gioco — ma il numero grezzo diceva 54,2%, e la colonna `scelto`, aggiunta il giorno prima,
ha spiegato perché.

**1. L'attribuzione era sbagliata** (D191). Delle undici mancate domande, **dieci** erano
risposte arrivate da un'altra voce: «Barattolo in vetro» invece di «Contenitori creme»,
«Tende in stoffa» invece di «Pantofole di stoffa», «Barattolo in latta» per un piatto.
Quelle voci hanno una variante sola: non c'era niente da chiedere. Il difetto è della
**scelta**, e ora la misura lo dice — le risposte arrivate da un'altra voce hanno un blocco
loro nell'uscita, e `domanda_dovuta` si calcola dove la domanda era giudicabile: **92,9%**.

**2. La famiglia di omonimi era troppo larga.** Per dei gusci di polistirolo l'agente ha
chiesto «carta oppure plastica?»: il confronto per inclusione faceva di «Polistirolo
espanso: gusci e barre **da imballaggio**» un parente di «Cartone **da imballaggio**». Ora
la **testa** del nome dev'essere la stessa — in italiano l'oggetto viene per primo e le
qualificazioni seguono — e l'inclusione vale solo per il resto.

**3. Il materiale nella domanda dell'utente non veniva letto.** A «capsule di plastica del
caffè» l'agente chiedeva «metallo oppure plastica?», perché guardava solo i `materiali` del
riconoscimento e non le parole scritte. Ora guarda anche quelle.

**4. L'accordo di genere**, il contratto lasciato in rosso ieri: «è tutta unta» non
corrispondeva a «unto». Le condizioni ora si confrontano con una radice più corta (quattro
lettere invece di cinque), che è quanto basta per genere e numero senza far collidere parole
diverse. Funziona anche con «untissimo», e la negazione resta negazione: «non è unto» non
vale «unto».

**Cosa resta, ed è la cosa grossa**: in dieci casi su quarantanove la scelta ha preso un
documento sbagliato pur avendo quello giusto fra i candidati (`recall@1` 89,8%). Non è un
difetto del chiarimento: è il prompt di scelta, o le politiche del codice. È la prossima
decisione, e ora ha un numero.

### v0.48.0 — 25/09/2026

**L'agente chiede anche di che materiale è** (D188–D190). Era il buco più grosso rimasto nel
chiarimento, e la misura di ieri lo lasciava fuori: il dubbio nasceva solo dalle
**condizioni** di una voce, mai dall'**identità** dell'oggetto. Così "bicchiere" a Napoli —
che può essere di vetro (Non Riciclabile) o di plastica (Plastica e Metalli) — riceveva una
risposta secca, scelta dal modello, senza che l'utente sapesse che dipendeva da
un'informazione che non aveva dato. Nei due dizionari le famiglie di omonimi distinte dal
materiale sono **37**.

Due cautele, perché una domanda di troppo è fastidiosa quanto una mancata: si chiede solo se
i materiali in gioco sono almeno due **e portano in contenitori diversi** (alluminio e latta
a Napoli finiscono entrambi in Plastica e Metalli: chiedere costerebbe un giro per niente), e
solo se il riconoscimento il materiale non l'ha già dichiarato — a quel punto tocca al filtro
dei materiali, che esiste dalla v0.37.0.

**Gli omonimi si riconoscono dai documenti** (D189). Il primo tentativo usava
`nomina_l_oggetto`, che pretende che la domanda contenga tutte le parole del nome: con
"tagliere della cucina" la domanda non nasceva. Ora si confronta il **nucleo** dei nomi —
quello che resta togliendo materiali e parole di servizio — per inclusione, e la famiglia si
ancora al documento scelto.

**La risposta va dove serve** (D190). `continua` metteva la risposta dell'utente sempre nello
`stato`: per un materiale non sarebbe servita a niente, perché il filtro guarda `materiali` e
le formulazioni cercano "oggetto + materiale" (D164). Ora ci finisce, e il secondo giro è
deterministico.

**Due conseguenze sulla misura.** Una risposta accompagnata da una domanda dovuta è
**provvisoria** e non entra nelle metriche della risposta: l'agente ha detto "probabilmente
X, ma dimmi di che materiale è", e pretendere che X fosse già completa lo punirebbe per aver
fatto la cosa giusta. E l'esito dice ora **quale voce ha risposto**: senza, un caso che si
aspettava una voce e ne ha trovata un'altra sembra un difetto della domanda invece che della
scelta — è quello che è successo il 25/09 con "medicinali", dove ha risposto `Medicinale`
(una variante sola, niente da chiedere) invece di `Farmaci`.

**Dataset**: `chiarimenti.jsonl` passa da 29 a **49 casi**, con dieci nuove coppie sul
materiale (bicchiere, tagliere, gruccia, imbuto, cucchiaio, piatto, posate, vaschetta,
caraffa). Le attese sono state verificate contro il codice prima di scriverle, ed è così che
è saltato fuori il limite di `nomina_l_oggetto`.

### v0.47.0 — 25/09/2026

**Il chiarimento ha finalmente un numero** (D187). Era l'unica decisione di progetto
caratteristica del sistema — chiedere invece di indovinare (D73) — senza una misura: si
poteva solo dire che funzionava avendolo provato a mano.

Ora è un insieme suo, `chiarimenti.jsonl`, **29 casi a coppie**: quattordici oggetti presi
dalle voci che hanno due varianti in conflitto, ciascuno provato due volte — una senza
dichiarare la condizione, dove l'agente deve chiedere, e una dichiarandola, dove deve
rispondere e basta. Due metriche da leggere insieme, `domanda_dovuta` e `domanda_inutile`,
e due diagnosi separate perché si riparano in punti diversi.

**La metrica ha trovato un difetto prima ancora di girare col modello.** Scrivendo le attese
ho verificato caso per caso cosa fa `scegli_variante`, e una non tornava: a «è tutta unta»
l'agente chiede lo stesso, perché la condizione nella fonte si chiama `unto` e il confronto
è letterale — l'accordo di genere lo manda a vuoto. Vale anche per «untissimo»; «è sporco»
invece funziona, perché sta nella tabella delle equivalenze.

Quel caso è rimasto nel dataset **come contratto, e oggi fallisce**: descrive cosa il
sistema deve saper fare, non cosa sa fare. È lo stesso ruolo che avevano i casi nati dagli
errori del 18/09, con la differenza che questo è stato trovato scrivendo il metro invece
che sbattendoci contro in produzione.

### v0.46.1 — 25/09/2026

**Corretto: per una cintura di pelle la risposta parlava di olio esausto.** Segnalato da
Stef provando `cintura di pelle` a Torino. La destinazione era giusta (contenitore abiti), i
passi no: spiegavano *tutti* i contenitori dedicati — «farmaci in farmacia, pile dal
tabaccaio, abiti nei cassonetti, olio esausto nei punti attrezzati» — e si portavano dietro
la nota dell'olio.

La causa è nei dati e non nel modello: la procedura è attaccata al **canale** (D166), e sotto
`contenitore_dedicato` stanno quattro contenitori che si usano in quattro modi diversi. Ora
una procedura può dichiarare una destinazione e specializzarsi (D186): sette righe nuove —
abiti, farmaci e pile per Napoli, più olio esausto per Torino — e la riga generica resta come
ripiego per i contenitori che non hanno istruzioni proprie. Dove non c'è specializzazione,
la generica ha smesso di elencare: dice "cerca il contenitore dedicato a questo tipo di
rifiuto", che è vero per tutti.

Tre test nuovi: la procedura degli abiti non può nominare olio, farmaci, pile o tabaccai;
la riga generica deve restare come ripiego; e ogni contenitore dedicato presente nei dati
deve avere la sua procedura, così un contenitore nuovo non eredita in silenzio quella
generica.

**Nota sul caso stesso**: la risposta è arrivata dal livello 1, non dal livello 2 come mi
aspettavo. Torino ha una voce `Abiti` (contenitore abiti oppure centro di raccolta) e il
modello ha scelto quella dichiarando `categoria`, che è corretto — la cintura è coperta anche
dalla regola "Scarpe e cinture", ma la voce è una risposta altrettanto vera e più completa.

### v0.46.0 — 25/09/2026

**Ogni caso lascia la sua traccia** (D185). Finora una valutazione produceva otto numeri e
un elenco di diagnosi: abbastanza per sapere *dove* intervenire, non per capire *perché* un
caso preciso è andato storto. Ora ogni caso apre una traccia MLflow con dentro tutto il
percorso — le domande poste all'indice, i documenti usciti con il loro ordine, i documenti
scartati per materiale, la scelta del modello con il suo motivo — e i tag su cui filtrare:
`caso`, `insieme`, `comune`, `diagnosi`, `recuperato`, `posizione`, `livello`, `atteso`.

Nell'interfaccia si aprono **dalla run**: la run della misura si apre prima dei casi, e una
traccia creata mentre una run è in corso le resta agganciata. Verificato su un server vero
prima di scriverlo, non dedotto dalla documentazione.

Il tracciatore punta allo stesso archivio della run — compreso quello locale di ripiego —
altrimenti misura e tracce finirebbero in due posti diversi. E come per la misura (D184),
`attivo=True`: le tracce di una valutazione non sono osservabilità facoltativa. Si
disattivano con `--senza-tracce`, che resta utile quando si vuole solo il numero.

**Da sapere leggendole**: nella modalità completa il recupero compare due volte per caso —
una per misurare il tetto su entrambi i livelli, una eseguita dalla cascata vera. È il
prezzo di misurare il recupero indipendentemente dalla risposta, e la traccia lo rende
visibile invece di nasconderlo.

### v0.45.0 — 19/09/2026

**Una valutazione non si perde più.** Il problema era di principio, non di codice: la
registrazione seguiva D116 — non bloccante, silenziosa in caso di guasto — che è la regola
giusta per le *tracce delle conversazioni* e quella sbagliata per una *misura*. Una traccia
persa non fa danno; una misura persa costa minuti di CPU e non si ripete uguale. Da qui
D184, e tre comportamenti nuovi:

1. **`ECOSCAN_MLFLOW_ATTIVO` non vale più qui.** Governa le conversazioni. L'unico modo di
   non registrare una valutazione è chiederlo, con `--senza-mlflow`;
2. **se il server non risponde, la run si scrive in locale**, in
   `data/valutazione/mlflow-locale.db`, che è un archivio MLflow vero e si apre con
   `mlflow ui --backend-store-uri sqlite:///…`. SQLite e non una cartella di file perché
   dalla 3.x MLflow **rifiuta** il vecchio file store: verificato provando, il ripiego
   scritto per primo non funzionava;
3. **se non riesce nemmeno lì, il comando si ferma con errore.** Lasciar credere che la
   misura sia al sicuro da qualche parte è il difetto peggiore dei tre.

**L'esito si salva sempre su file**, in `data/valutazione/esecuzioni/<data>-<modalità>.json`,
anche senza `--salva`: una misura non deve dipendere dall'essersi ricordati di un'opzione.
`--salva` resta per darle un nome che si ricorda. Vale anche per `ecoscan-valuta-foto`.

**`--prova-mlflow`** scrive una run minuscola in un esperimento a parte e riferisce: serve a
rispondere in un secondo alla domanda "è il server o è la valutazione?", senza rieseguire
novantadue casi per scoprirlo.

**Verificato con un server vero**, non per ragionamento: la scrittura passa (parametri,
metriche e allegato), il ripiego locale funziona, e il percorso "non si può scrivere da
nessuna parte" si ferma con un messaggio invece che con una traccia grezza. È così che è
saltato fuori il difetto del file store, che nessuna lettura del codice avrebbe mostrato.

### v0.44.1 — 19/09/2026

**L'avanzamento c'è anche senza modello.** Era attivo solo nella modalità completa, con la
motivazione che l'altra "gira in secondi": falso. `--senza-modello` calcola un embedding per
ogni formulazione di ogni caso — fino a sette domande per due livelli — e su CPU diventano
minuti in cui non si vede niente. Ora ogni caso stampa contatore, esito, secondi per caso e
tempo stimato alla fine; su un terminale vero la riga si riscrive, quando l'uscita è
rediretta su file se ne stampa una ogni dieci. In testa ci sono anche le impostazioni in
uso e la composizione del dataset, e in coda la durata totale.

L'avanzamento viene chiamato **dopo** ciascun caso, non prima: così la riga dice com'è
andato invece di annunciare cosa sta per fare, e un fallimento si vede passare invece di
aspettare il riepilogo.

**La registrazione su MLflow non fallisce più in blocco.** Parametri, metriche e allegato
si scrivono in tre passaggi protetti uno per uno: se l'allegato non passa, le metriche
restano comunque scritte e l'uscita dice cosa è andato e cosa no. Prima un errore su
qualunque dei tre faceva dichiarare "esecuzione non registrata" anche quando due terzi
erano stati salvati.

E soprattutto: **ogni esito viene detto**. MLflow spento lo dichiara (prima restituiva
`False` in silenzio), un server irraggiungibile stampa il motivo e come accenderlo, e a
registrazione riuscita si stampa il **link diretto alla run**. L'esperimento
`ecoscan-valutazione` è separato da `ecoscan-chat`, e senza link la prima domanda è sempre
"ma dove è finita?".

### v0.44.0 — 19/09/2026

**Arricchimento dei documenti, dalla fonte** (D183). I documenti oggetto passano da 57 a
101 caratteri di media e 650 su 875 guadagnano almeno una frase, tutta ricavata dai dati
che c'erano già:

- il **gesto**, quando non è il cassonetto sotto casa: "Si prenota il ritiro a domicilio",
  "Si porta al centro di raccolta". Per la raccolta ordinaria non si dice, perché sarebbe
  la stessa frase su metà del corpus (D167);
- i **flussi di materiale**, ma solo le parole che il testo non ha già: è ciò che dà a
  "Numero Verde Gratuito" la parola *ingombrante* e a "Ecoisole RAEE R4" le parole
  *apparecchiatura elettrica*, che i loro nomi non contengono;
- le **regole di categoria che nominano l'oggetto**, con un criterio stretto: tutte le
  parole significative del nome devono comparire nella regola, contando anche il nome del
  contenitore, e le voci dal nome di una parola sola non si agganciano mai (con un token
  solo "Carta" prendeva sette regole, compresa una sui fondi di caffè). 48 voci su 902.

La terza è quella che vale: al `Bicchiere di vetro` di Napoli aggancia *"Nel contenitore
Vetro NON va: Bicchieri"*, mentre a `Bottiglia in vetro` aggancia *"Nel contenitore Vetro
va: Bottiglie"*. Due voci che prima differivano per una parola ora divergono anche nella
spiegazione — l'opposto di quello che avrebbe fatto una descrizione generata, che le
avrebbe descritte entrambe come oggetti di vetro trasparente.

**Scartata la versione generativa**, che era la proposta iniziale: una descrizione scritta
da un modello direbbe che il vetro si ricicla, il che a Napoli è falso, e finirebbe nel
testo che legge il modello di scelta. La regola arriva dai dati (D9) o non è una regola.

**Da misurare.** `ECOSCAN_ARRICCHIMENTO=no` riproduce l'indice della v0.43.0. Il confronto
si fa con `--senza-modello` in pochi secondi, e la soglia è decisa prima: `recall@8` deve
salire di almeno 4 punti, `recall@1` non deve scendere, le 18 regressioni devono restare
verdi e i casi assenti non devono iniziare a trovare candidati.

**Campione a 63 casi** (+15): illuminazione, bioplastica, cristallo, medicinali, lenti a
contatto e altri, scelti dove il campione era più sottile — contenitore dedicato, raccolta
itinerante, voci con più destinazioni (ora 15 su 63).

**Corretto.** La registrazione su MLflow falliva sempre: `recall@1` contiene una chiocciola
e MLflow ammette nei nomi solo alfanumerici, `_ - . : /` e spazi. Rifiutando quel nome
rifiutava **l'intera** scrittura — una chiamata sola, una transazione sola — quindi la run
veniva creata e restava vuota. La conversione (`recall@8` → `recall_at_8`) avviene solo al
confine con MLflow: dentro il progetto il nome resta quello che si legge in letteratura.

**Numeri.** 92 casi (18 + 63 + 11), 519 test verdi.

### v0.43.0 — 19/09/2026

**La valutazione smette di misurare la propria storia** (D173–D175). Fino a ieri i numeri
venivano da diciotto casi nati tutti da errori osservati: preziosi come rete di sicurezza,
inutili come stima, perché per costruzione stanno dove il sistema aveva già sbagliato. Ora
i casi sono in **tre insiemi separati**, con tre letture diverse: 18 regressioni (pass/fail),
**48 casi di campione** estratti dal dizionario e stratificati per comune, canale e numero
di alternative, **11 casi assenti** in cui la risposta giusta è non rispondere.

Il campione nasce da `ecoscan-campiona`, che pesca dal database con un seme fisso e scrive
una bozza con l'attesa **già compilata** e la domanda vuota: l'attesa la sa la fonte, la
domanda la sa solo una persona. Delle 48 domande, 23 vengono dalle vecchie sonde (erano il
pezzo costoso, già scritto a mano) e 25 sono nuove. Tre erano tautologie — la domanda
coincideva col nome della voce — e le ha prese il test, non l'occhio.

**Due errori diversi, due numeri diversi** (D176). `contenitore_corretto` dice se qualche
destinazione proposta era fuori dalle attese; `copertura` dice quante delle attese sono
state dette. Con l'uguaglianza esatta di prima, la risposta del microonde — "isola
ecologica", vera ma senza il ritiro a domicilio — era sbagliata esattamente quanto
"Organico". Non lo è: la prima fa fare più strada, la seconda manda nel cassonetto
sbagliato.

**Curva di recall al posto della posizione media** (D177). La media era calcolata sui soli
casi trovati e peggiorava quando un documento difficile cominciava finalmente a uscire, in
settima posizione. Ora si leggono `recall@1`, `recall@4` e `recall@8` — stesso dato, letto
in modo che distingua "l'indice non ce l'ha" da "ce l'ha ma lo ordina male".

**Casi negativi** (D178). `Caso.valido` accetta attese vuote se il caso dichiara
`livello_atteso: 3`, e due nuove metriche misurano l'astensione nelle due direzioni.
Scriverli ha richiesto di verificare ogni assenza sui dati: "pneumatico" sembrava assente e
la voce si chiama `Pneumatici`; "violino" è assente a Torino ma non a Napoli, che ha
`Strumento musicale`. Un caso negativo sbagliato è l'errore del frullatore al contrario.

**Le condizioni della misura viaggiano con la misura** (D179). Ogni esecuzione salvata
porta data, `k`, modalità, composizione del dataset e la configurazione dell'agente;
`--confronta` avvisa in testa se le due esecuzioni non sono confrontabili.

**Foto e tempi** (D181). `ecoscan-valuta-foto` esegue ogni foto due volte — dal
riconoscimento vero e dall'oggetto dichiarato — e la differenza fra i due numeri è il costo
del modello di visione, isolato. Riporta anche p50 e p90 di riconoscimento e risposta: è il
numero che il README elencava dalla v0.29 e che non era mai stato preso. Le venti etichette
sono già scritte, con le attese dal database: mancano le foto.

**Una run per esecuzione** (D182). Esperimento `ecoscan-valutazione`, separato da
`ecoscan-chat`, non bloccante: serve alla serie storica, che dieci file JSON non danno.

**Rimosso.** Le sonde (`db/sonda.py`, `sonde.csv`, `ecoscan-sonda`): misuravano una
versione più debole del recupero, con l'attesa come sottostringa e senza destinazioni. Il
metodo `_recupera` dell'agente diventa `recupera`, perché la valutazione lo chiamava
essendo privato (D180).

**Numeri.** 77 casi in tutto (18 + 48 + 11), 20 foto etichettate, 511 test verdi.

### v0.42.0 — 18/09/2026

**Rimosso il riscontro dell'utente**, per intero: i pulsanti 👍👎 e il modulo del pollice giù nell'interfaccia, la rotta `POST /riscontro`, lo schema `Riscontro`, il metodo del client, il registro `data/riscontri.jsonl` e la conversione `caso_da_riscontro`.

**La valutazione torna a una sorgente sola** (D172). Sparisce `data/valutazione/da_riscontri.jsonl`, con il campo `origine` e la regola "vince il manuale": restano i casi scritti a mano in `casi.jsonl`. Il codice della valutazione si accorcia e, soprattutto, il numero che produce torna a significare una cosa sola.

**Perché è una semplificazione e non una perdita.** Il meccanismo dei riscontri prometteva di far crescere il dataset da sé, ma un dataset vale quanto vale l'autorità delle sue attese: un'attesa che nessuno ha esaminato fa più danno di un caso mancante, perché fa "correggere" un sistema che funziona. Lo avevamo visto un'ora prima con il caso `frullatore`, scritto in fretta e sbagliato — e quello l'avevo scritto io, con il dizionario sotto gli occhi. Diciotto attese di cui rispondiamo valgono più di duecento di cui non sappiamo niente.

Se servirà una seconda sorgente — casi derivati dagli alias del dizionario, casi estratti dalle tracce — starà in un file suo e con una sua percentuale: mescolare attese di autorità diversa in un numero solo lo rende illeggibile. L'impalcatura si rifà in un pomeriggio; il dataset avvelenato no.

**Superficie in meno**: una rotta (da nove a otto), uno schema, due file di dati, circa 150 righe fra codice e test.

**Test.** 481 (erano 498): i 17 in meno sono quelli del riscontro, non copertura persa altrove.

### v0.41.2 — 18/09/2026

**Prima esecuzione vera della valutazione**, e ha trovato tre cose — due nel sistema di misura, una nei dati.

**Il divano di Torino è risolto** senza averlo toccato: le formulazioni essenziali di v0.41.0 lo portano in posizione 1. È la prova che quella correzione era strutturale e non un cerotto, perché il caso è stato scritto dopo.

**"0.0% livello di evidenza atteso" era una bugia della misura.** Senza modello il livello non viene mai determinato, e `livello_corretto` confrontava `None` con l'atteso restituendo `False` per ogni caso. Ora restituisce `None` quando non lo sappiamo, e la misura si omette. Una metrica che mente è peggio di una che manca, perché la si legge.

**"corretto" senza modello non era corretto**: significava solo "documento trovato". Diagnosi rinominata in "documento recuperato (la risposta non è stata valutata)".

**Il frullatore non era un errore del sistema, era un errore mio** (D171). Avevo scritto il caso con le destinazioni di "Elettrodomestici", ma ASIA ha una voce `Frullatore` che manda alle Ecoisole RAEE R4, il raggruppamento dei piccoli elettrodomestici: il sistema dava la risposta *più specifica e più giusta*, e la valutazione la contava come recupero fallito. Esattamente il rischio dichiarato in `valutazione.md` — "un caso con l'attesa sbagliata rende il sistema peggiore mentre sembra migliorarlo" — verificatosi entro un giorno.

Da qui la correzione utile: quando un caso fallisce, l'uscita mostra ora **dove portavano i documenti trovati**. Se l'attesa non compare in quell'elenco, quasi sempre è l'attesa a essere sbagliata. Senza quella riga, un'attesa sbagliata e un recupero fallito sono indistinguibili nella modalità più veloce.

**Test.** 498.

### v0.41.1 — 18/09/2026

**Caso del divano.** Due prove sulla stessa foto, due difetti diversi e speculari.

**Napoli: l'etichetta mentiva.** Recupero e scelta erano perfetti — il documento scelto era proprio "Divani", con la sua pagina su ASIA — ma il modello ha dichiarato `categoria` ("il divano rientra nella categoria mobile"), e la presentazione introdotta in v0.40.2 ha ripetuto fedelmente: *"il comune non elenca proprio questo oggetto, ma la categoria a cui appartiene"*. Falso, e falso proprio mentre citava la pagina del divano. È il difetto simmetrico di quello del microonde: lì l'etichetta era troppo generosa, qui troppo modesta.

La correzione (D170) non tocca il prompt: il codice **verifica** l'etichetta con `nomina_l_oggetto`, la stessa funzione che già promuove il documento specifico. Se il documento nomina l'oggetto — e "Divani" nomina "divano", plurale compreso — la corrispondenza è `stesso_oggetto`, comunque il modello l'abbia chiamata. La direzione opposta richiede il senso delle parole e resta al prompt.

**Torino: un recupero fallito, non una categoria.** La voce **"Divani"** esiste anche nel Rifiutologo AMIAT, con *due* destinazioni: centro di raccolta **e rifiuti ingombranti**, cioè il ritiro a domicilio. Non è stata recuperata, e la risposta è arrivata da "Arredi in legno, ferro o plastica" — difendibile come categoria, ma senza il ritiro a casa, che per un divano è l'unica opzione praticabile senza un furgone.

Da notare: la prova è stata fatta con una versione precedente alle formulazioni essenziali (v0.41.0), che è proprio la modifica che dovrebbe far uscire "Divani" per la domanda "divano". Va rimisurata prima di concludere.

**Aggiunti al dataset**: divano a Torino, divano a Napoli, materasso a Torino.

**Test.** 494.

### v0.41.0 — 18/09/2026

**Formulazioni: essenziali e aggiuntive** (D164, D165). L'elenco unico ordinato per specificità si era rotto due volte nello stesso punto — la domanda che serviva stava in fondo e il tetto la tagliava. Ora quattro domande **entrano sempre** (oggetto, oggetto+categoria, categoria da sola, oggetto+materiale) e i sinonimi riempiono ciò che resta, con il tetto a 7. Verificato sui tre casi noti: forchetta, sandalo e microonde ottengono tutti la domanda che gli mancava. I materiali nella domanda estesa si fermano a due.

**Procedure di smaltimento** (D166–D169). Per un terzo del dizionario di Napoli la risposta "va in X" era vera e insufficiente: 195 voci finiscono in un'isola ecologica, 86 a un ecopunto itinerante, 57 chiedono una prenotazione telefonica. La procedura si attacca al **canale** — nove coppie (comune, canale) scritte a mano in `data/sorgenti/manuale/procedure.csv`, non 902 voci — e arriva all'utente come passi numerati.

Quando i canali sono più d'uno (115 voci a Napoli) diventano **alternative ordinate per sforzo**: prima ciò che si fa da casa, poi ciò che chiede di spostarsi. La raccolta ordinaria non si spiega quando ce n'è un'altra da spiegare.

**Il livello 3 smette di dire solo "non lo so"** e indica il centro di raccolta: non è indovinare la destinazione, è dire dove si chiede.

**Cosa manca di proposito.** Nessun indirizzo, nessun orario, nessun recapito: sono dati che il progetto non ha ancora estratto, e una procedura verosimile ma sbagliata manda una persona a un cancello chiuso. La colonna `da_verificare` li elenca voce per voce, ed è la lista di lavoro per quando i luoghi entreranno nei dati (questione aperta 6).

**Non serve rigenerare nulla** per le procedure: è un file nuovo, letto a runtime. Restano da rigenerare i dati per le cinque revisioni sui nomi.

**Test.** 489 (erano 462): procedure, formulazioni essenziali, presentazione a passi, e due controlli che impediscono a una procedura di promettere orari o numeri di telefono che non abbiamo.

### v0.40.2 — 18/09/2026

**Caso del microonde** (Napoli). La risposta era quasi giusta e la citazione era falsa: il sistema rispondeva "Isola Ecologica Estesa oppure Ecopunto Elettrodomestici" citando **"Bistecchiera elettrica"**, e scriveva "il comune elenca proprio questo oggetto". Tre cose insieme:

1. **Recupero fallito.** Nel dizionario di Napoli esistono "Elettrodomestici", "Apparecchiature elettriche ed elettroniche" e "Forno": nessuna delle tre è uscita. Fra i candidati c'erano una bistecchiera e tre voci di stoviglie e barattoli — il trascinamento verso i materiali già visto con il sandalo (D80), qui aggravato da quattro materiali dichiarati (acciaio, vetro, plastica, metallo).
2. **Un fratello passato per categoria.** "Bistecchiera elettrica" non contiene il microonde: sono due figli di "Elettrodomestici". Il prompt definisce `categoria` come "la voce è la categoria a cui l'oggetto appartiene", e il modello l'ha usata per una relazione fratello–fratello. D162 chiude il buco con un controesempio esplicito.
3. **La presentazione affermava più di quanto il sistema sapesse.** "Il comune elenca proprio questo oggetto" vale solo per `stesso_oggetto`; con `categoria` o `sinonimo` va detto che il comune elenca *la categoria*. Una frase che dice il falso è peggio di una risposta approssimativa, perché toglie all'utente il motivo per dubitare.

**Conseguenza pratica**: la risposta perdeva il **Numero Verde Gratuito**, cioè il ritiro a domicilio — per un microonde l'opzione più utile delle tre.

**Aggiunto al dataset di valutazione**: microonde, lavatrice, frullatore. Il caso del microonde è la prima diagnosi `RECUPERO_FALLITO` nata da un uso vero.

**Qualità dei nomi**: l'indagine ha trovato un quinto nome mutilato che i controlli non prendevano, "Giocattolo di grosse dimensioni o elettrico" → **"Giocattolo o elettrico"**. Congiunzione seguita da un *aggettivo*, non da una preposizione: controllo aggiunto, revisione applicata. 5 su 902, e i falsi positivi restano zero ("Pentole e padelle", "Vetro e lattine", "Olio e grasso animale" passano).

**Test.** 459: il prompt rifiuta i fratelli con un controesempio, la presentazione distingue i tre tipi di corrispondenza, il quinto controllo sui nomi.

### v0.40.0 — 18/09/2026

**Valutazione del recupero.** `ecoscan-valuta` esegue un dataset di casi e produce, oltre alle percentuali, una **diagnosi per caso**: la tabella 2×2 (documento recuperato sì/no × risposta giusta sì/no) dice se la prossima ora di lavoro va sul prompt di scelta o sull'indice. Il recall@k si legge come tetto alla correttezza finale (D153): se il documento non esce, nessun prompt può rimediare. La modalità `--senza-modello` misura solo quel tetto e gira in secondi invece che in minuti. Documentato in [valutazione.md](valutazione.md), con le motivazioni teoriche, le metriche scartate e i limiti dichiarati. 12 casi scritti a mano per cominciare, compresi quelli nati dagli errori osservati (forchetta d'acciaio, sandalo, ciabatta).

**Il riscontro alimenta il dataset.** Il pollice su/giù non è più solo un registro: quando porta un'attesa diventa un caso rieseguibile (D155). Dopo un pollice giù l'interfaccia chiede **dove andava davvero**, scegliendolo fra i contenitori del comune, e il motivo separa i due difetti che si riparano in punti diversi — un "non ha capito che oggetto è" non diventa un caso, perché il riconoscimento è proprio ciò che i casi tengono fermo (D156).

**Cache del riconoscimento** (D158). Decoratore di `ModelloVisione`: la stessa foto con lo stesso testo non si guarda due volte. Verificato: quattro richieste con tre foto identiche e una diversa fanno due chiamate vere al modello. In memoria, non su disco: un riconoscimento è il giudizio di una versione di un prompt.

**Qualità dei nomi** (D159). I nomi mutilati dalla normalizzazione ("Stovaglie in materiale", "Tovaglioli di carta o di cibo") non sono un difetto estetico: il nome finisce nel testo indicizzato e nel confronto con l'oggetto riconosciuto, quindi un nome rotto è un documento che il recupero non trova mai — un problema di retrieval travestito da problema di dati. Sette controlli grammaticali stretti; su 902 voci ne segnalano 4, tutte e quattro corrette con una revisione manuale. Il controllo è dentro il Transform, quindi d'ora in poi la rottura si segnala da sé.

**Ricerca testuale** (D160). Rotta `/domanda` e campo di testo senza foto: chi sa come si chiama l'oggetto salta il passaggio lento. Stessa cascata, stessa scelta, stesse tracce.

**Legenda dei contenitori** (D161). Nell'interfaccia, l'elenco completo dei contenitori del comune raggruppato per canale: dà all'utente il vocabolario del sistema prima che legga una risposta, e dichiara i limiti di ciò che l'assistente può indicare.

**Revisioni manuali**: 36 (erano 32), le 4 nuove sono i nomi corretti. **Serve rigenerare i dati**: `uv run ecoscan-transform && uv run ecoscan-carica && uv run ecoscan-regole && uv run ecoscan-carica && uv run ecoscan-vettorizza`.

**Test.** 449 (erano 382): valutazione, cache, qualità dei nomi, `/domanda`, riscontro arricchito, legenda, e due controlli statici sull'interfaccia — le chiamate interne rispettano le firme, e nessuna funzione resta mai chiamata.

### v0.39.0 — 18/09/2026

**Corretto, seguito del caso forchetta.** Con il v0.37.0 la risposta era giusta — Plastica e Metalli — ma arrivava dal **livello 2**, la regola generale del contenitore. La traccia ha mostrato perché: al livello 1 "Stoviglie in metallo" era regolarmente fra i candidati, e il modello rispondeva "nessuna". Il recupero funzionava; a rinunciare era la scelta.

**Modificato.** Prompt di scelta alla versione 8, con due regole nuove (D151, D152): una voce dal nome collettivo copre ogni oggetto dell'insieme ed è una corrispondenza buona, non un ripiego; "nessuna" vale quando l'elenco parla d'altro, non quando la voce è più larga dell'oggetto.

**Perché il concetto di "categoria" non bastava.** C'era già, ma i suoi esempi erano tutti specifico→generico dello stesso tipo di oggetto: sandalo→"Scarpe", teglia→"Pentole e padelle". Il passo forchetta→"Stoviglie" è diverso, è membro→insieme, e il modello non lo faceva da solo.

**Da verificare su foto vera**: se la risposta passa al livello 1, il prompt basta. Se il modello continua a rinunciare, la leva successiva sta nei dati — alias `Forchetta; Coltello; Cucchiaio; Posate` sulla voce `stoviglie-in-metallo` — e chiede di rigenerare e rivettorizzare.

**Non serve rigenerare nulla**: cambia solo il testo di un prompt.

**Test.** 382 (erano 380): le due regole nuove nel prompt e la sua versione.

### v0.38.0 — 18/09/2026

**Aggiunto.** `docs/architettura.md`: il documento da cui partire per orientarsi. In undici sezioni: la regola che tiene insieme il progetto, i quattro livelli dei dati, la catena ETL, il percorso di una risposta con i quattro passaggi, la mappa di tutti i moduli, le regole di dipendenza con i test che le verificano, i punti di sostituzione, l'osservabilità, i test, la configurazione, e come si aggiorna il documento stesso.

**Aggiunto.** Due test che lo tengono allineato (D150): uno fallisce se un modulo di `src/ecoscan/` non è citato nella mappa, l'altro se il documento non nomina la versione corrente. È la stessa idea già applicata a diario e glossario: un test rosso si nota, un promemoria no.

**Nessun cambiamento al codice.**

**Test.** 380 (erano 378).

### v0.37.0 — 18/09/2026

**Corretto un errore osservato su foto vera.** Una forchetta d'acciaio riceveva "Non Riciclabile" citando la voce "Forchetta in plastica". Il riconoscimento aveva funzionato — il modello aveva scritto "realizzata in acciaio inossidabile" nel motivo della scelta — e il guasto stava tutto dopo. Erano tre difetti sovrapposti, e servivano tutti e tre gli interventi.

**Misurato prima di correggere.** Con `/cerca` su Napoli: "forchetta" non porta "Stoviglie in metallo" fra i primi dieci; "forchetta acciaio" sì, in nona posizione. La risposta giusta era nei dati per due strade — la voce "Stoviglie in metallo" e la regola "posate in metallo" — e nessuna delle due veniva raggiunta.

**Aggiunto.** `materiali.py`: otto famiglie di materiali con le parole che compaiono davvero nei dizionari dei due comuni, e la regola che dichiara incompatibili due famiglie disgiunte. Un documento che tace sul materiale non viene mai escluso, e uno che ne nomina più d'uno è compatibile con ciascuno.

**Aggiunto.** I candidati di un altro materiale vengono tolti prima della scelta (D147): il modello non vede più il documento sbagliato, invece di doverlo rifiutare. Lo scarto è registrato nello span del recupero.

**Corretto durante la verifica.** Il primo filtro scartava anche "Scatolette per tonno", perché leggeva "Va in **Plastica** e Metalli" come materiale dell'oggetto: il confronto ora guarda il nome del documento (D148), e le famiglie conoscono i plurali. Emerso applicando il filtro ai candidati veri di `/cerca`, non ragionandoci sopra.

**Modificato.** La formulazione "oggetto + materiale" sale in terza posizione fra le domande poste all'indice (D149), dove il tetto di cinque non la taglia più.

**Modificato.** Prompt di scelta alla versione 7: il materiale della descrizione è vincolante quanto la categoria, con l'esempio della forchetta.

**Non serve rigenerare nulla**: non cambiano né lo schema, né i documenti, né l'indice.

**Test.** 378 (erano 364): le famiglie di materiali, la regola di incompatibilità con i suoi casi limite, il caso della forchetta da un capo all'altro dell'agente, il modello ostinato che non può più dare la risposta sbagliata, il salvataggio quando lo scarto svuoterebbe l'elenco, la posizione della formulazione col materiale, e una regressione sui candidati reali di Napoli.

### v0.36.0 — 17/09/2026

**Architettura.** Il recupero diventa un oggetto con un'interfaccia (D145). `Recupero` è un `Protocol` con un nome e un metodo `candidati(domande, comune, livello, k)`; `RecuperoQdrant` è l'unica implementazione di oggi, con la ricerca semantica e l'aggancio esatto dei codici materiale divisi in due metodi privati.

**Cambia la firma dell'agente**, per la prima volta da quando esiste: `Agente(recupero, modello, k=..., tracciatore=...)` invece di `Agente(qdrant, vettorizzatore, modello, ...)`. L'agente non importa più nulla da Qdrant. `Risorse` costruisce il recupero e lo passa sia all'agente sia alla rotta `/cerca`.

**Nelle tracce** il parametro `modello_embedding` diventa `recupero` (D146), quindi la prima risposta dopo l'aggiornamento crea un LoggedModel nuovo: è corretto, la configurazione è cambiata davvero.

**Nessuna ricerca ibrida**, per scelta: questo giro prepara il posto dove metterla, non la mette.

**Test.** 366 (erano 364): l'agente che risponde con un recupero in memoria, senza Qdrant né embedding, e la configurazione che dichiara quale ricerca era in uso.

### v0.35.0 — 17/09/2026

**Refactoring, a comportamento invariato.** Nessuna funzione nuova per l'utente: gli stessi 363 test di prima passano, e il Transform rigenerato produce file **identici byte per byte** a quelli di prima (verificato con l'impronta SHA-256 dei due `*_voci.jsonl`).

**API.** `crea_app` era una funzione di 112 righe: le rotte si registrano ora per area (`rotte_stato`, `rotte_agente`, `rotte_ricerca`, `rotte_riscontro`), e le dipendenze comuni — risorse correnti, controllo del comune, contesto valido — stanno in un oggetto `Dipendenze` (D143). La validazione del contesto era ripetuta in tre rotte con lo stesso messaggio: ora è un metodo solo.

**Agente.** `_scegli_nel_livello` si è diviso in `_recupera` e `_scegli`; la cascata fra livello 1 e 2 è `_cascata`; da `_componi` sono usciti `_piu_specifico` e `_chiarimento`. Riconoscimento, comune, parole dell'utente e "ho già chiesto" viaggiano in un oggetto `Richiesta` (D144), che porta anche la soglia di affidabilità: `_componi` passa da otto parametri a quattro.

**Transform.** `trasforma_voce` (56 righe, 15 rami) è diventata una sequenza di passaggi con un nome ciascuno — asterisco, parentesi, locuzioni, condizioni inline, voci composte — che lavorano su un oggetto `Estratti`.

**Caricamento.** `carica` si è divisa per tabella (`_inserisci_comuni`, `_inserisci_destinazioni`, `_inserisci_voci`, `_inserisci_regole`, `_inserisci_decisioni`), e regole e decisioni passano da `executemany` invece che da un ciclo di `execute`.

**Tracciamento e frontend.** `_prepara` si è divisa in `_e_ora_di_riprovare`, `_connetti` e `_collega_versioni`; `nota_fonte` ha estratto `provenienza`; `principale` ha estratto `mostra_conversazione` e `gestisci_invio`.

**Pulizia.** Cinque import morti, un elemento duplicato in un insieme di invarianti (`TE/OF`), due `zip` senza `strict`, due parametri che nessuno usava (`db` nella sonda, `cliente` in `chiedi`).

**Aggiunto.** Ruff configurato nel `pyproject.toml` ed eseguito come test (D142).

**Test.** 364 (erano 363): il linter. Nessun test esistente è stato modificato, ed è la garanzia che il comportamento non sia cambiato.

### v0.34.0 — 17/09/2026

**Aggiunto.** Il modulo `condizioni.py`: riconosce se una condizione è uno stato dell'oggetto, una quantità o un'utenza, e da lì scrive la frase e compone la domanda (D140). Spariscono "Vale se è: piccole quantità" e il pulsante "Utenza domestica" in risposta a "com'è il tuo oggetto?". Le condizioni di tipo diverso restano separate: "Vale per grandi quantità e per utenza domestica".

**Misurato.** Sui dati veri: 147 condizioni su 142 voci; 15 di quantità, 5 di utenza, 1 sola clausola di ammissibilità. Da qui D140 (vale la pena) e D141 (non vale la pena).

**Da revisionare a mano.** Cinque voci hanno più di una condizione e tre meritano una decisione: il cartone da pizza di Torino con la clausola, i tovaglioli di carta di Torino dove "bagnati o unti" è diventato "bagnato E unto", e le stoviglie monouso di Napoli con il nome normalizzato mutilato in "Stovaglie in materiale".

**Test.** 363 passati (erano 353): nuovo `test_condizioni.py` e i casi della presentazione e del chiarimento.

### v0.33.1 — 17/09/2026

**Rimosso.** L'avanzamento per fasi introdotto in v0.33.0 (D137, D138, D139): il modulo `agente/avanzamento.py`, le tre rotte a flusso e il riquadro di stato nella chat. Durante l'attesa torna lo spinner unico.

**Invariato.** Tutto il resto della v0.31.0: etichette leggibili, provenienza delle voci, riconoscimento visibile, correzione, citazione della fonte.

### v0.32.1 — 17/09/2026

**Rimosso.** La ricerca per parti separabili introdotta in v0.32.0 (D134, D135). La prima foto vera su cui è stata provata — un piatto con una forchetta appoggiata sopra — ha mostrato che il caso non era quello previsto: forchetta e piatto sono due oggetti distinti, non un oggetto con parti separabili, e il prompt chiede al modello di descriverne uno solo. La funzione non copriva il caso frequente e costava una ricerca e una chiamata al modello per parte.

**Deciso.** Le foto con più oggetti restano fuori portata (D136), in attesa di affrontare il riconoscimento di più oggetti distinti senza raccogliere anche lo sfondo.

**Invariato.** Tutto il resto della v0.31.0: etichette leggibili, provenienza delle voci, riconoscimento visibile, correzione, citazione della fonte.

### v0.31.0 — 17/09/2026

**Aggiunto.** Le destinazioni hanno un'etichetta leggibile (D128), esposta dalla nuova rotta `/destinazioni` e usata dal frontend: l'utente non legge più `carta_e_cartone` ma "Carta e cartone". Le risposte continuano a portare il nome interno, che resta la chiave dei dati.

**Aggiunto.** Fonte e riferimento su ogni voce (D129): il Transform li prende dal grezzo (URL della pagina a Napoli, pagina del Rifiutologo a Torino), il caricamento li conserva e i documenti oggetto li portano nel payload. Una risposta di livello 1 ora dice da dove viene, e se la fonte è una pagina il frontend ne fa un link.

**Aggiunto.** Il riconoscimento della foto si mostra prima della risposta (D130), con i dettagli visti e quanto l'assistente è sicuro.

**Aggiunto.** Rotta `/correggi` (D131): l'utente dichiara qual è l'oggetto e si rifanno solo ricerca e scelta, senza rileggere la foto. Nel frontend è il riquadro "Non è un/una …?". La correzione è un turno della stessa conversazione anche nelle tracce.

**Aggiunto.** Il chiarimento porta le sue opzioni (D132) e l'interfaccia ne fa pulsanti; la risposta inviata a `/continua` resta la stessa di prima.

**Modificato.** "Come ci sono arrivato" mostra la citazione del documento scelto, il motivo della scelta e le voci scartate (D133); la tabella dei punteggi resta annidata dentro, per chi sviluppa. La risposta dichiara il documento scelto (`scelto_id`), senza il quale non si poteva citare nulla.

**Modificato.** Dopo una risposta con più varianti si vedono anche i rami non scelti ("se è pulito → Carta e cartone · **se è unto → Organico** ✓").

**Da rilanciare dopo l'aggiornamento.** `ecoscan-transform`, `ecoscan-regole`, `ecoscan-carica` e `ecoscan-vettorizza`: cambiano sia lo schema sia il payload dei documenti.

**Test.** 352 passati (erano 329): etichette e provenienza nel caricamento e nei documenti, rotte `/destinazioni` e `/correggi`, opzioni e documento scelto nell'agente, correzione come turno tracciato, e nel frontend traduzione delle etichette, riconoscimento, citazione, alternative e link della fonte.

### v0.30.0 — 17/09/2026

**Sostituito.** Il tracciamento passa dalle run alle tracce di MLflow Tracing (D123). Ogni turno (`analizza`, `continua`) è una traccia con input e output completi; dentro, uno span LLM per il riconoscimento, uno RETRIEVER e uno LLM per la scelta a ogni livello provato. I tempi per fase non si misurano più a mano: sono le durate degli span.

**Aggiunto.** Le foto come allegati delle tracce (D124), con il content type letto dai byte e l'impronta accanto. Si spengono con `ECOSCAN_MLFLOW_FOTO=no`.

**Aggiunto.** La sessione: `analizza` genera `id_conversazione` e lo mette nel contesto, `continua` lo rilegge (D125). Un contesto senza identificativo, da un client vecchio, apre una conversazione nuova invece di fallire.

**Aggiunto.** La versione dell'applicazione come LoggedModel con i parametri significativi (modelli, `k`, soglia di confidenza, lato massimo, prefissi, keep_alive, prompt), e il collegamento alle tracce delle versioni dei prompt pubblicate (D126). Gli stessi parametri stanno anche nei tag `param.*`, per filtrare la lista delle tracce.

**Modificato.** `ecoscan-prompt --pubblica` è idempotente: non crea una versione nuova se nel registro c'è già un prompt con la stessa impronta.

**Modificato.** Dopo un guasto il tracciatore riprova dopo `ECOSCAN_MLFLOW_RIPROVA` secondi (60 di norma), invece di restare spento fino al riavvio del backend.

**Rimosso.** La run per richiesta, `Traccia` con parametri, metriche ed etichette, le durate misurate a mano. `/cerca` resta non tracciata: serve alla diagnosi e mescolerebbe prove e conversazioni.

**Infrastruttura.** Immagine del server MLflow allineata al client, v3.16.1 (D127).

**Test.** `test_tracciamento.py` riscritto su un archivio MLflow locale (SQLite in una cartella temporanea): 20 test su input e output del turno, allegato della foto, documenti del retrieval, sessione condivisa, LoggedModel riusato, prompt collegati, e sul fatto che né un MLflow spento né un errore dell'agente vengano nascosti o blocchino la risposta. Un test in `test_docker.py` confronta la versione dell'immagine del server con quella del lock.

### v0.29.2 — 12/09/2026

**Corretto.** Dal container il tracciamento non funzionava: MLflow, dalla 3.5, valida l'header `Host` per difendersi dal DNS rebinding e accetta di norma solo localhost e indirizzi privati, mentre il backend lo chiama con il nome del servizio Docker. Aggiunto `--allowed-hosts` con `mlflow:5000`.

**Aggiunto.** Un test che confronta l'indirizzo con cui il backend chiama MLflow e l'elenco degli host consentiti: sono due righe dello stesso file che devono essere d'accordo, e prima non lo erano.

### v0.29.1 — 12/09/2026

**Corretto.** La costruzione dell'immagine falliva: `pyproject.toml` dichiara `readme = "README.md"` e il Dockerfile non copiava quel file. L'errore arrivava da hatchling e non nominava il Dockerfile, quindi era poco leggibile.

**Aggiunto.** Due test che leggono il `pyproject.toml` e verificano che i file dichiarati (readme, pacchetti) siano copiati nell'immagine e non esclusi dal `.dockerignore`.

### v0.29.0 — 12/09/2026

**Aggiunto.** `docker/Dockerfile` e i servizi `backend` e `frontend` nel compose. Un'immagine sola, costruita con `uv sync --frozen` perché le versioni siano quelle provate in sviluppo, e due comandi diversi. Il database arriva da un volume in sola lettura: l'ETL resta un lavoro da riga di comando.

**Aggiunto.** Il servizio `ollama` sotto il profilo `completo`: in sviluppo il modello sta sull'host, dove è già scaricato e resta caricato in memoria fra un riavvio e l'altro dei container; per la consegna basta `docker compose --profile completo up -d`.

**Modificato.** `ecoscan-frontend` accetta `--indirizzo`: dentro un container serve ascoltare su tutte le interfacce, non solo su localhost.

**Test.** 10 controlli sul compose, che non avviano container ma verificano che il file dica ciò che intendiamo: indirizzi dei servizi, sola lettura sul database, attesa di un backend *sano* e non solo partito, immagini fissate a una versione.

### v0.28.0 — 12/09/2026

**Sonde riscritte.** Da 16 a 28, con attese verificate contro i documenti reali (un test lo controlla, perché due sonde erano già fallite per un'attesa scritta a memoria). Tre famiglie: codici materiale ("PAP 21", "ALU 41", "C/PAP 84"), parafrasi d'uso ("la scatoletta del tonno", "il flacone del detersivo", "pile del telecomando") e controlli facili.

**Aggiunto.** `osservabilita/tracciamento.py`: una run MLflow per richiesta, con parametri (comune, modelli, versione dei prompt, impronta della foto), metriche (livello di evidenza, candidati, confidenza, **tempi per fase**) ed etichette (oggetto, tipo di corrispondenza, chiarimento, destinazioni). Delle foto si registra solo l'impronta.

**Aggiunto.** `osservabilita/prompt_registrati.py` e il comando `ecoscan-prompt`: elenca i prompt con versione e impronta, e li pubblica nel registro di MLflow.

**Aggiunto.** Il servizio `mlflow` nel `docker-compose`, con database e artefatti su volume.

**Corretto prima ancora di sbagliare.** Il primo test ha bloccato l'esecuzione per cinque minuti: il client MLflow riprovava a lungo. Un tracciamento non bloccante deve fallire in fretta, e ora rinuncia dopo tre secondi e un tentativo. 10 test, fra cui uno che verifica che l'avviso compaia una volta sola.

### v0.27.1 — 12/09/2026

**Risultato del recupero.** Con i documenti nuovi, "Cartone per pizze. Se è pulito va in Carta e Cartoncino; se è unto va in Organico" è il primo risultato con 0.609: il recupero sul caso che ci aveva fatto penare per sei giri funziona.

**Corretto.** Il modello sceglieva comunque "Cartone da imballaggio". Tre interventi: i candidati arrivano ordinati per somiglianza; se un documento nomina proprio l'oggetto riconosciuto vince sul generico, e la preferenza la applica il codice; il confronto fra nomi ignora preposizioni e articoli, perché "cartone della pizza" e "Cartone per pizze" differiscono solo per quelli.

**Corretto.** Il chiarimento chiedeva "grandi quantità oppure nessuna condizione?": le varianti senza condizione non si nominano più, e se resta una sola alternativa non si chiede.

### v0.27.0 — 12/09/2026

**Rimosso.** Tutta la ricerca lessicale e la fusione: `db/indicizza.py` (schede, FTS5 a trigrammi, riduzione alla radice, parole di servizio), la funzione `fondi_rrf`, la garanzia sui primi risultati di ogni formulazione, il tetto sui candidati, il comando `ecoscan-indicizza`, e con loro `condizioni_in_gioco`, `affini` e `scegli_per_condizione`, che erano toppe rese inutili dalla nuova struttura.

**Sostituito.** I documenti sono indicizzati su Qdrant con il loro payload; la ricerca è una sola query semantica filtrata per comune. I codici materiale si agganciano in modo esatto con un'espressione regolare: era l'unico caso in cui il lessicale vinceva.

**Semplificato l'agente.** Il modello sceglie l'**oggetto**, il codice sceglie la **variante** in base alla condizione dichiarata, e se non è dichiarata si chiede. Il recupero passa da dieci classifiche fuse a una ricerca per formulazione, unite senza duplicati.

**Test.** Riscritti su un ambiente condiviso in `tests/conftest.py` che costruisce database, documenti e indice. 303 test.

### v0.26.0 — 12/09/2026

**Aggiunto.** `db/documenti.py` e il comando `ecoscan-documenti`: la nuova unità da indicizzare. 996 documenti sui due comuni (877 oggetti, 106 regole, 13 destinazioni), con testo scritto in italiano leggibile e payload strutturato.

Esempi di ciò che viene generato:

    Cartone per pizze. Se è pulito va in Carta e Cartoncino; se è unto va in Organico.
    Cartone da pizza. Se è pulito va in carta e cartone; se è sporco va in organico, ma solo se compostabile certificato.
    Scarpe. Se non è utilizzabile va in Non Riciclabile; se è utilizzabile va in Contenitore Abiti Usati.
    Simbolo GL o GLS. Codici del materiale sull'imballaggio: 70, 71, 72. Va in Vetro.
    Nel contenitore carta e cartone NON va: carta con residui di cibo.

**Cura del testo.** Le frasi sono state corrette leggendo il risultato su casi reali: negazioni in italiano ("se non è utilizzabile", non "se è non utilizzabile"), clausole di ammissibilità separate dagli aggettivi ("ma solo se compostabile certificato"), quantità come clausole ("ma solo in piccole quantità"), nomi tecnici resi leggibili (`carta_e_cartone` → "carta e cartone"), varianti indistinguibili unite, varianti con la stessa destinazione non ripetute.

**Contraddizioni.** Quando la fonte dà destinazioni diverse per lo stesso caso, il documento lo dichiara nel testo invece di scegliere. 16 test.

### v0.25.1 — 12/09/2026

**Risultato a Napoli.** Con la foto e "è unto" il riconoscimento dà "cartone della pizza" con stato "unto", e la risposta è "Cartone per pizze unto → Organico". Il percorso completo funziona.

**Corretto (emerso a Torino).** Lo stesso caso dava "carta e cartone": il modello aveva scelto la voce generica "Scatole in cartone o cartoncino" mentre "Cartone da pizza" era fra i candidati, e la correzione per condizione guardava solo gli omonimi della voce scelta, che erano zero. Ora guarda anche le voci **affini**, cioè quelle che condividono parole con l'oggetto riconosciuto.

**Aggiunto.** Un elenco corto di equivalenze fra condizioni (unto ≈ sporco, vuoto ≈ senza residuo), perché i due comuni nominano lo stesso stato con parole diverse.

**Modificato.** Prompt di scelta alla versione 6: fra una voce che nomina proprio l'oggetto e una generica va scelta la specifica; se la descrizione indica uno stato e una voce lo riporta, è quella.

### v0.25.0 — 12/09/2026

**Diagnosi.** Con la foto di un cartone della pizza e il testo "è unto", l'agente rispondeva "Carta e Cartoncino". La causa non era nelle condizioni ma a monte: il modello aveva riconosciuto **"scatola"**, e le domande poste all'indice erano "scatola", "cartone", "confezione". Le parole dell'utente non arrivavano al recupero.

**Corretto.** Il testo dell'utente diventa una domanda per l'indice, da solo e unito all'oggetto riconosciuto.

**Modificato.** Prompt di riconoscimento alla versione 4: ciò che dice l'utente vince sull'impressione del modello, sia per il nome dell'oggetto sia per lo stato. Aggiunta anche la regola di preferire il nome preciso a quello generico ("cartone della pizza", non "scatola").

### v0.24.2 — 12/09/2026

**Corretto.** Con la foto di un cartone unto e il testo "è unto", l'agente rispondeva "Carta e Cartoncino": il modello sceglieva la variante "pulito" e, non essendoci più il chiarimento, l'errore passava in silenzio. Ora, se l'utente dichiara una condizione, la variante la sceglie il codice fra le voci omonime.

**Aggiunto.** Il confronto fra condizione e testo usa la radice delle parole e tiene conto della negazione: "non utilizzabile" si riconosce in "scarpe non utilizzabili", mentre "unto" non si riconosce in "non è unto".

### v0.24.1 — 12/09/2026

Due difetti emersi dalla prima conversazione vera nel frontend, con un cartone della pizza unto.

**Corretto.** L'agente chiedeva "è unto oppure pulito?" anche quando l'utente lo aveva già scritto nel messaggio, o quando il modello lo aveva visto nella foto. Ora la domanda si fa solo se la condizione non è già determinata da ciò che si sa.

**Corretto.** Rispondendo al chiarimento, `continua` ricalcolava la domanda e la riproponeva identica: l'utente restava in un giro senza uscita. Dopo una risposta la domanda non si ripete.

### v0.24.0 — 12/09/2026

**Aggiunto.** Frontend a chat in Streamlit (`frontend/`) e comando `ecoscan-frontend`. Si allega la foto dal campo unico in basso, come negli assistenti più diffusi; la risposta arriva come messaggio, con il livello di evidenza spiegato a parole e la fonte in nota. Quando l'agente chiede un chiarimento, la risposta dell'utente prosegue la conversazione tramite `/continua`, senza rileggere la foto. Due bottoni raccolgono il riscontro.

**Struttura.** Tre moduli: `cliente.py` (unico punto di contatto col backend, con messaggi d'errore che dicono cosa fare), `presentazione.py` (da risposta dell'API a testo leggibile) e `app.py` (interfaccia). 14 test sui primi due; l'interfaccia non si prova, ma le parti che si sbagliano davvero sì.

### v0.23.0 — 12/09/2026

**Aggiunto.** Le API del backend (`api/`) e il comando `ecoscan-api`. Sei rotte: `/analizza` (foto, comune, testo facoltativo), `/continua` (risposta a un chiarimento, senza rileggere la foto), `/cerca` (solo testo, per valutazione e diagnosi), `/comuni`, `/salute` (stato di database, Qdrant e Ollama) e `/riscontro`. Documentazione interattiva su `/docs`.

**Scelte.** Backend senza stato: il contesto torna al client e viene rimandato. Database in sola lettura. Schemi Pydantic separati dai tipi interni dell'agente. Risorse costruite una volta all'avvio, perché aprire una connessione per richiesta ricaricherebbe anche il modello.

**Test.** 12 test con risorse finte: database in memoria, Qdrant in-process, modello programmabile. Nessun container, nessuna rete, nessun modello scaricato.

**Verifica.** La ciabatta ora funziona: l'agente sceglie "Scarpe utilizzabile" dichiarando "categoria", e il chiarimento sulle condizioni è pertinente alla voce scelta.

### v0.22.0 — 12/09/2026

**Risultato.** Il recupero sulla ciabatta funziona: fra i candidati compaiono "Scarpe utilizzabile", "Scarpe non utilizzabile" e "Stivali". Sonde a 14 su 16; la formulazione "oggetto più categoria" porta "sandalo calzatura" al secondo posto, mentre "sandalo" da solo resta fuori.

**Corretto.** Il chiarimento veniva calcolato su tutti i candidati: dopo aver scelto "Stivali" chiedeva "utilizzabile o non utilizzabile?", condizione che apparteneva a "Scarpe". Ora si guardano solo gli omonimi della voce scelta.

**Modificato.** Prompt di scelta alla versione 5: fra voci della stessa famiglia va scelta quella che **contiene** l'oggetto, non un oggetto diverso della stessa famiglia. Per un sandalo la voce giusta è "Scarpe", non "Stivali"; l'esempio è preso dall'errore osservato.

### v0.21.1 — 12/09/2026

**Corretto.** La v0.21.0 era stata committata con un test rosso: la funzione di fusione non aveva ricevuto il tetto sul numero di candidati, e il test che lo verificava falliva sull'import. Funzione riscritta, 283 test verdi.

### v0.21.0 — 12/09/2026

**Misurato onestamente.** Con le attese corrette: 12 sonde su 14, e "calzatura" trova davvero "Scarpe utilizzabile", ma al **secondo** posto. Restano fuori "sandalo" e "ciabatta", parole singole e ambigue che recuperano rumore.

**Corretto.** La garanzia copriva solo il primo risultato di ogni formulazione: per questo "Scarpe utilizzabile" non compariva fra i candidati dell'agente pur essendo seconda. Ora ne copre due, con un tetto di 12 candidati per non allungare il prompt della scelta.

**Aggiunto.** Una formulazione che unisce oggetto e categoria ("sandalo calzatura"), subito dopo quella con il solo oggetto. Due sonde nuove la misurano.

### v0.20.2 — 12/09/2026

**Corretto (errore di misura).** La sonda confrontava per sottostringa: cercando "Scarpe" accettava "Laccio per scarpe", che è un altro oggetto. Tre sonde su quattordici erano falsi positivi. Ora la tabella mostra **quale scheda** ha soddisfatto l'attesa e, quando fallisce, qual era il primo risultato; le attese su "Scarpe" sono state rese precise.

**Corretto.** Il chiarimento veniva mostrato anche quando non era una domanda: il modello aveva risposto "0". Ora si tiene solo se contiene un punto interrogativo ed è abbastanza lungo.

**Risultato delle sonde dopo le correzioni della v0.20.1**: 12 su 14 trovate, i cartoni della pizza al primo posto in entrambi i comuni. Restano fuori "sandalo" e "ciabatta".

### v0.20.1 — 12/09/2026

Tutto nato dal primo giro di sonde.

**Misurato.** I prefissi di EmbeddingGemma servono: 10 sonde su 14 con, 9 senza, e "tetrapak" si trova solo con i prefissi. L'ipotesi che Ollama li applicasse già da sé è smentita.

**Corretto (errore nelle sonde).** Due sonde attendevano "Cartone unto per pizze", ma il testo indicizzato è "Cartone per pizze unto": il Transform sposta la condizione in fondo. Non erano fallimenti del recupero.

**Corretto.** Preposizioni e articoli venivano usati come termini di ricerca: "cartone della pizza unto" falliva perché "dell" compare in "Polvere dell'aspirapolvere", quindi la ricerca in AND trovava qualcosa e non ripiegava su OR. "non" resta un termine, perché distingue le condizioni.

**Corretto.** Con otto classifiche da fondere, una scheda trovata al primo posto da una sola formulazione poteva restare fuori dai candidati: è il caso di "calzatura", che trova "Scarpe" al primo posto. Ora ogni formulazione porta almeno il proprio primo risultato.

### v0.20.0 — 12/09/2026

**Aggiunto.** `ecoscan-sonda`: 14 domande note con la scheda attesa (in `data/riferimento/sonde.csv`), e per ognuna la posizione raggiunta da lessicale, semantico e ibrido. Gira in pochi secondi perché non usa il modello di visione, quindi si può ripetere a ogni modifica del recupero. È il primo pezzo di valutazione, limitato al retrieval.

**Aggiunto.** `ECOSCAN_PREFISSI_EMBEDDING`: permette di indicizzare senza i prefissi di EmbeddingGemma. Serve a verificare un sospetto preciso, cioè che Ollama li applichi già da sé e che i nostri li duplichino, peggiorando il recupero. Non è una correzione: è il modo per misurare quale configurazione funziona.

**Osservato.** Dopo la correzione dei prompt il riconoscimento della ciabatta è perfetto ("sandalo", sinonimi "ciabatta, calzatura", categoria "calzatura"), ma il recupero continua a fallire: cercando "calzatura" il primo risultato è "Laccio per scarpe" e "Scarpe utilizzabile" non compare. Il problema è ora isolato nella ricerca semantica su testi brevi.

### v0.19.1 — 12/09/2026

Tre difetti emersi dalla prova sulla ciabatta, dove la risposta è stata "Organico" con la motivazione "la ciabatta è un tipo di pane".

**Corretto.** `sinonimi` e `categoria` erano facoltativi nello schema di uscita e il modello li ha omessi: ora sono obbligatori.

**Corretto.** La descrizione passata al passaggio di scelta non conteneva categoria né sinonimi. Il modello poteva quindi reinterpretare l'oggetto: è il bug che ha permesso alla ciabatta di diventare pane.

**Modificato.** Prompt di riconoscimento alla versione 3, con la regola sui nomi ambigui e l'esempio della ciabatta; prompt di scelta alla versione 4, con la categoria dichiarata vincolante.

### v0.19.0 — 12/09/2026

**Modificato.** Il prompt di riconoscimento passa alla versione 2: il modello produce anche **sinonimi** e **categoria** dell'oggetto, che diventano formulazioni aggiuntive per la ricerca. Per un sandalo: "ciabatta, scarpa, calzatura". È la correzione del difetto emerso nella prova sulla ciabatta, dove la ricerca su "sandalo" restituiva "Salse", "Sdraio" e "Scaldabagno".

**Modificato.** Il prompt di scelta passa alla versione 3: il modello deve dichiarare il **tipo di corrispondenza** fra cinque etichette. L'agente scarta `solo_materiale` e `nessuna`, qualunque numero il modello abbia indicato. La politica sta nell'agente e non nell'adattatore Ollama, così vale anche per modelli futuri: il primo tentativo l'aveva messa nel posto sbagliato, e un test con un modello finto l'ha rivelato.

### v0.18.0 — 12/09/2026

Correzioni nate dalle prime due prove complete su foto reali: la bottiglia funziona, la ciabatta no.

**Modificato.** L'indice viene interrogato con **due formulazioni** invece di una: solo oggetto e stato, poi oggetto con i materiali. Le classifiche vengono fuse con RRF, così una voce trovata da entrambe sale. Con la sola frase estesa "sandalo gomma plastica tessuto" i materiali dominavano e nessuna calzatura compariva fra i candidati.

**Modificato.** Il prompt di scelta passa alla versione 2: vieta esplicitamente di scegliere una voce che condivide solo il materiale, e dichiara che rispondere "nessuna voce" è corretto e utile. Davanti a un sandalo il modello aveva scelto "molletta in plastica da bucato", motivandolo con il materiale.

**Misurato.** Con `keep_alive` attivo i tempi sono scesi: recupero e scelta da 180 a circa 20 secondi, riconoscimento sui 55. Il riconoscimento resta il passaggio dominante.

### v0.17.0 — 12/09/2026

**Deciso.** Il modello di visione predefinito diventa `gemma3:4b`. Gemma 4, in entrambe le varianti provate, non interpreta le fotografie su questa installazione.

**Prove raccolte.** Stessa foto, stessa preparazione (768×1024, 58 KB), stesso codice: `gemma3:4b` riconosce "una Adidas slide blu scuro con tre strisce bianche e suola usurata"; `gemma4:e2b` risponde "un modulo standardizzato composto da righe e colonne". Sulla diagnostica, Gemma 4 sbaglia i tre colori pieni e la domanda sulla posizione: la risposta "rosso" della prima prova era indovinata, ed è il motivo per cui la diagnostica era stata resa più severa.

**Conseguenza per il progetto.** Il modello è un parametro del `.env`, non un pezzo dell'architettura: quando la parte visiva di Gemma 4 funzionerà, si torna indietro cambiando una riga. La pipeline, i prompt e la valutazione restano gli stessi.

### v0.16.2 — 12/09/2026

**Corretto.** `--diagnostica` si interrompeva subito: il blocco usava `modello` prima che venisse creato. Il nome del modello si risolve ora subito dopo la lettura degli argomenti, così la diagnostica non dipende dal resto della preparazione e gira anche senza database.

**Aggiunto.** Tre test che eseguono davvero `main()` con la diagnostica sostituita da una finta: verificano che parta senza database, che rispetti `--modello` e che esca con codice 1 quando il canale non funziona.

### v0.16.1 — 12/09/2026

**Accertato.** La dimensione dell'immagine **non** è la causa: a 2048, 1024 e 512 pixel il modello descrive sempre "una griglia di quadrati", e a 256 non risponde affatto.

**Modificato.** La diagnostica è ora più difficile da superare per caso: tre colori pieni invece di uno, più un'immagine divisa a metà con una domanda sulla **posizione** del colore. Un solo test sul colore si poteva indovinare.

**Aggiunto.** `--modello` sul comando di prova, per confrontare due modelli senza toccare la configurazione. È il modo per stabilire se il difetto sia di `gemma4:e2b` o dell'installazione.

### v0.16.0 — 12/09/2026

**Accertato.** Il canale immagine funziona: Ollama 0.34, `gemma4:e2b` dichiara `vision`, e l'immagine di tinta unita viene riconosciuta. Il guasto sta quindi fra l'immagine di prova (64 pixel, 178 byte) e le foto vere (megapixel, megabyte).

**Aggiunto.** `agente/immagini.py`: prima dell'invio le immagini diventano JPEG RGB con lato lungo 1024. È ciò che il modello farebbe comunque, ma sotto il nostro controllo, e toglie di mezzo canali alfa e scale di grigio. 8 test.

**Aggiunto.** `ecoscan-analizza --foto ... --scalini`: descrive la **stessa** foto a 2048, 1024, 512 e 256 pixel. Se le descrizioni diventano sensate sotto una certa misura, il problema è la dimensione; se restano assurde a ogni misura, la dimensione non c'entra e va cercato altrove. `--descrivi` mostra ora formato, dimensioni e peso di ciò che parte davvero.

### v0.15.3 — 12/09/2026

**Aggiunto.** `ecoscan-analizza --diagnostica`: tre controlli sul canale immagine, cioè versione di Ollama, `capabilities` dichiarate dal modello (deve comparire `vision`) e una prova con un PNG di tinta unita generato a mano, chiedendo di che colore è. È la prova decisiva: nessun modello che riceve un'immagine tutta rossa risponde "griglia di blocchi". 3 test verificano che il PNG generato sia valido, CRC compresi, per non incolpare il modello di un difetto nostro.

**Stato.** Le prove di Stef hanno mostrato che il modello **non riceve le immagini**: due foto molto diverse producono la stessa descrizione generica. La diagnostica serve a stabilire se il problema sia la versione di Ollama, il modello senza capacità di visione, o il passaggio dell'immagine.

### v0.15.2 — 12/09/2026

Correzioni nate dalla prima prova su una foto reale, che ha dato un riconoscimento sbagliato ("schema" per una ciabatta) e 262 secondi di attesa.

**Aggiunto.** Modalità diagnostica `ecoscan-analizza --foto ... --descrivi`: chiede al modello una descrizione libera dell'immagine, senza schema e senza i nostri prompt. Distingue due guasti molto diversi: un modello che vede male e un modello che l'immagine non la riceve.

**Aggiunto.** `keep_alive` nelle richieste a Ollama (30 minuti di norma, configurabile). L'agente fa fino a tre chiamate al modello e senza questo parametro ognuna può ricaricare il modello da disco.

**Corretto.** La confidenza tornava come `100.00`: i modelli rispondono in percentuale. Ora viene normalizzata in 0-1, altrimenti la soglia sotto cui si dichiara "non riconosciuto" non scatterebbe mai.

**Migliorato.** La risposta conserva i candidati di **tutti** i livelli provati, non solo dell'ultimo: se la scelta cade sul livello 2, si vede anche cosa era stato scartato al livello 1.

### v0.15.1 — 12/09/2026

**Aggiunto.** Comando `ecoscan-analizza`: prova l'agente su una foto vera, stampando riconoscimento, candidati con la loro provenienza (lessicale, semantica o entrambe), risposta e **tempi per fase**. Con `--oggetto` si salta il modello di visione e si parte da una descrizione scritta, utile per provare retrieval e scelta senza aspettare Gemma. 8 test sui controlli d'ingresso e sulla presentazione, fra cui uno che verifica che una regola di esclusione si legga come divieto.

### v0.15.0 — 12/09/2026

**Aggiunto.** Il pacchetto `agente/`: tipi (`Riconoscimento`, `Candidato`, `Scelta`, `Risposta`), modello di visione dietro un'interfaccia con implementazione Ollama a output strutturato, recupero dei candidati per livello di evidenza arricchiti dal relazionale, e l'orchestrazione. 24 test con un modello finto programmabile e la ricerca vera.

**Aggiunto.** I prompt come file versionati in `src/ecoscan/prompt/`, con versione e impronta; ogni risposta porta nel contesto le etichette dei prompt usati e il nome del modello.

**Scelte di flusso.** La cascata prova prima le voci (livello 1) e poi le regole di categoria (livello 2); se nessuna delle due produce una scelta, la risposta è di livello 3 e dichiara che il comune non copre l'oggetto. Il chiarimento si attiva quando i candidati contengono omonimi con destinazioni diverse: è un segnale nei dati, non un'intuizione del modello.

**Rifinitura dei test.** Il vettorizzatore finto è passato in `tests/conftest.py`, perché ora lo usano sia i test dell'indice sia quelli dell'agente.

### v0.14.3 — 12/09/2026

**Modificato.** L'autorecupero accetta le prime 3 posizioni invece della sola prima: i quasi sinonimi presenti nelle fonti si contendono legittimamente la testa della classifica. Il test che verifica il controllo è stato reso più severo (il vettore viene invertito, non scambiato) e la sua fixture allargata, perché con poche schede il controllo non poteva fallire e il test non provava nulla.

**Scoperto grazie all'autorecupero.** Napoli ha voci quasi gemelle con destinazioni diverse: "Televisore a tubo catodico" prevede anche l'ecopunto elettrodomestici, "TV a tubo catodico" no. Registrato in `qualita_dati.md`: non è deduplicabile e non è un errore nostro, ma una contraddizione della fonte che l'agente dovrà mostrare.

### v0.14.2 — 12/09/2026

**Corretto.** L'autorecupero diceva `29/30` senza indicare quale scheda avesse fallito e cosa avesse trovato al suo posto. Ora le mancate sono elencate con testo cercato e testo ottenuto.

**Aggiunto.** La verifica segnala quante schede hanno un testo più corto di 4 caratteri, con esempi: sono le celle della scheda "Pile" di Torino ("C", "AA", "D"), formati di batteria che nessun metodo di ricerca può distinguere. È un limite della fonte, non dell'indice, e viene mostrato come nota.

### v0.14.1 — 12/09/2026

Tutte correzioni emerse dalle prime ricerche sui dati reali.

**Corretto.** Il codice materiale non finiva nel testo indicizzato: "Simbolo GL o GLS" era identico per i codici 70, 71 e 72, e le tre voci erano indistinguibili. È anche la causa del `29/30` nell'autorecupero. Ora il codice fa parte del testo, ed è per giunta la sigla che si legge sull'imballaggio.

**Corretto.** Le regole venivano mostrate con la sola destinazione, quindi un'esclusione sembrava un'indicazione: ora compaiono come `NO <contenitore>` o `SI <contenitore>`.

**Corretto.** L'autorecupero segnalava come errore il pari merito fra schede con testo identico, che invece è corretto.

**Corretto.** Versione di `qdrant-client` allineata al server del `docker-compose` (1.12), per togliere l'avviso di incompatibilità. Tolto dal payload l'identificatore, già presente come id del punto.

### v0.14.0 — 12/09/2026

**Aggiunto.** `ecoscan-vettorizza --verifica`: sette controlli sull'indice vettoriale (numero di punti contro schede, conteggi per comune e livello, identificatori allineati, dimensione dei vettori, campi del payload, assenza della destinazione dal payload) più l'**autorecupero** su un campione. 3 test, fra cui uno che scambia due vettori lasciando i conteggi intatti: solo l'autorecupero se ne accorge.

### v0.13.2 — 12/09/2026

**Corretto.** `test_il_file_env_viene_letto` falliva sul portatile di Stef e passava qui: il sottoprocesso ereditava le variabili `ECOSCAN_*` della macchina. Ora l'ambiente del test viene ripulito, così il risultato dipende dal file e non da come è configurato il computer.

**Corretto.** Il caricamento del `.env` ignorava una riga quando la variabile esisteva già nell'ambiente **anche se vuota**: `override=False` non distingue i due casi. Ora una variabile vuota conta come assente. Aggiunto un test di regressione.

### v0.13.1 — 12/09/2026

**Aggiunto.** Configurazione centralizzata: `src/ecoscan/configurazione.py` legge le impostazioni dal file `.env` alla radice (modello versionato in `.env.example`, caricato da `percorsi.py` prima di ogni altro modulo). Le variabili d'ambiente vere restano prioritarie. I comandi stampano le impostazioni in uso, compresa la modalità di Qdrant. 7 test, fra cui uno che verifica che ogni variabile letta dal codice sia documentata nel modello.

**Perché.** Impostare `ECOSCAN_QDRANT` a mano vale per una finestra sola: dimenticarlo avrebbe indicizzato i vettori nella cartella locale invece che nel container, senza nessun errore visibile.

### v0.13.0 — 12/09/2026

**Modificato.** Vettori migrati da SQLite a **Qdrant**. `db/vettorizza.py` riscritto: collezione `schede`, vettore denso da EmbeddingGemma, payload con comune, livello, tipo e testo, filtro per comune applicato dentro la query. Il client si configura con `ECOSCAN_QDRANT`: un URL punta al server, un percorso attiva la modalità in-process usata dai test. Aggiunto `docker-compose.yml` con il servizio Qdrant e il relativo healthcheck. 10 test, nessuna dipendenza da Docker o dalla rete.

**Perché.** La scelta precedente (BLOB in SQLite più ricerca esaustiva in NumPy) era difendibile sul piano prestazionale ma non su quello architetturale, e per un progetto universitario conta che la tecnologia sia appropriata al problema. Il guadagno concreto è il filtro per comune dentro la ricerca: il vincolo D7 smette di dipendere dalla disciplina di chi scrive la query.

**Verificato prima di decidere.** La modalità locale di `qdrant-client` regge filtro sul payload, vettori sparsi e fusione RRF nativa, quindi i test restano veloci e senza infrastruttura. Limiti: è una reimplementazione Python, apre la cartella in esclusiva e non ha dashboard.

### v0.12.0 — 12/09/2026

**Aggiunto.** Terzo e ultimo passaggio del Load: `db/vettorizza.py` e comando `ecoscan-vettorizza`. Embedding delle schede con EmbeddingGemma su Ollama, ricerca semantica esaustiva in NumPy, fusione RRF con l'indice lessicale. Il vettorizzatore sta dietro un'interfaccia, così i test girano senza rete. 10 test.

**Corretto.** `data/ecoscan.db` era finito in git: in `.gitignore` il commento a fine riga (`*.db  # ...`) rendeva il pattern un nome di file letterale. Database tolto dal tracciamento e aggiunto un test che rifiuta i commenti a fine riga.

**Allineato.** Adottata la copia del progetto di Stef, con il grezzo di Napoli (584 voci) ora versionato. Indice lessicale completo: 1072 schede (902 voci, 64 alias, 106 regole).

### v0.11.0 — 12/09/2026

**Aggiunto.** Livello di serving lessicale: `db/indicizza.py` e comando `ecoscan-indicizza`. Costruisce le **schede** (una voce genera una scheda per il nome con le sue condizioni e una per ogni alias; ogni regola ammessa o esclusa ne genera una) e le indicizza con FTS5 a trigrammi. Ricerca filtrata per comune, con filtro opzionale per livello di evidenza. 14 test.

**Osservato provando la ricerca sui dati reali.** Tre correzioni sono nate dalle prove, non dal progetto: senza riduzione alla radice "bicchiere di vetro" non trovava "Bicchieri di vetro"; la ricerca in solo AND restituiva zero risultati troppo spesso; indicizzare il `dettaglio` delle regole faceva emergere "lampadine" cercando "ceramica", perché la frase intera è condivisa da tutti gli esclusi della stessa scheda.

**Limite noto.** A Torino "tetrapak" non trova nulla: la fonte scrive "Tetra Pak" con lo spazio, e con i trigrammi la sottostringa non combacia. A Napoli funziona perché esiste l'alias. È esattamente il caso che la ricerca semantica dovrà coprire.

### v0.10.1 — 12/09/2026

**Corretto.** L'estrazione di Napoli non dava segno di vita per 15 minuti e sembrava bloccata. Ora stima in anticipo quante pagine mancano davvero (distinguendo cache e scaricamenti) e stampa l'avanzamento ogni 25 voci con il tempo residuo.

**Annotato.** Il grezzo di Napoli conviene versionarlo, come già quello di Torino: chi parte da un clone pulito non deve ripagare i 15 minuti di scaricamento.

### v0.10.0 — 12/09/2026

**Aggiunto.** Load relazionale: `db/carica.py` e comando `ecoscan-carica`. Ricostruzione totale del database a ogni esecuzione, con due controlli che bloccano il caricamento invece di produrre dati zoppi (destinazione usata ma non dichiarata; destinazione dichiarata ma mai usata). Schema riscritto sui dati normalizzati reali: comune, flusso, destinazione con alias e flussi, voce con condizioni e alias, destinazioni alternative ordinate, regola, decisione di revisione, traccia del caricamento. 12 test.

**Aggiunto.** `data/riferimento/destinazioni.csv`: canale, colore e flussi delle 27 destinazioni dei due comuni. Erano cablati in `demo.py`, che è stato rimosso.

**Verificato sul database.** Il caso dei due livelli di evidenza a Torino: "Cartone da pizza" con condizione *pulito* va nella carta, con *sporco* + *solo se compostabile certificato* nell'organico; e la regola di categoria esclude dalla carta "carta con residui di cibo".

### v0.9.1 — 12/09/2026

**Aggiunto.** `tests/test_documentazione.py`: sette controlli che impediscono alla documentazione di restare indietro (versione presente nella cronologia e nello stato, comandi e moduli documentati, decisioni numerate senza buchi e con uno stato valido, termini essenziali nel glossario). Il primo giro ha subito trovato quattro moduli mai citati: è nata la mappa dei moduli nel README.

**Pulizia.** Rimossa la costante `NEGAZIONE` in `transform_comune.py`, non più usata dopo il passaggio alla gestione della negazione dentro le condizioni inline. Verificato che non esistono altre funzioni o costanti pubbliche mai richiamate.

### v0.9.0 — 12/09/2026

**Verificato.** Catena completa eseguita da Stef sui dati reali. Numeri definitivi dell'ETL, con cui è stata allineata tutta la documentazione:

| | Voci grezze | Normalizzate | Regole | Decisioni manuali | Conflitti | Da revisionare |
|---|---|---|---|---|---|---|
| Napoli | 584 | 578 | 50 | 16 | 0 | 0 |
| Torino | 324 | 324 | 60 | 16 | 0 | 0 |

902 voci normalizzate, 110 regole di categoria, 32 decisioni manuali (3,5%). Napoli: 84 voci con almeno una condizione, 28 alias, 20 codici materiale. Torino: 58 con condizione, 36 alias.

**Osservato.** Le condizioni ricavate da materiale e provenienza (D31) producono etichette poco uniformi: "alluminio", "plastica o tessuto", "sabbia/segatura", "di finestre e porte", "contenitori vuoti in plastica metallo". Distinguono correttamente le voci, ma come vocabolario sono grezze. Da valutare dopo il Load, misurando se influiscono sul retrieval.

### v0.8.1 — 12/09/2026

**Chiuso.** Le sei decisioni aperte di Napoli: Stef ha verificato che l'asterisco nel nome non rimanda ad alcuna nota nella pagina. È un residuo tipografico della fonte, non un'informazione perduta. Decisioni portate a `conferma` con la motivazione e la data della verifica.

**Aggiunto.** Due test di igiene sulle decisioni: nessuna può restare `da_decidere`, e ognuna deve avere una motivazione scritta.

**Risultato.** 902 voci normalizzate, 32 decisioni manuali (3,5%), 0 voci da revisionare, 0 conflitti.

### v0.8.0 — 12/09/2026

**Aggiunto.** Meccanismo di revisione manuale (`revisioni.py`) e file `data/revisioni/napoli.csv` e `torino.csv`. Il Transform legge le decisioni e le applica: `non_separare` disattiva la separazione già in fase di trasformazione, le altre azioni agiscono sulla voce prodotta. Una decisione su uno slug inesistente ferma l'esecuzione. 10 test.

**Deciso.** Torino: 16 decisioni, di cui 3 separazioni annullate ("Foglie e fiori secchi", "Termometri digitali e a mercurio", "Polistirolo per alimenti e piccoli imballaggi") e la nota a piè di pagina degli oli vegetali agganciata come avvertenza. Nessuna voce resta da revisionare. Napoli: 10 decisioni prese, 6 lasciate aperte come `da_decidere` (le voci con asterisco).

**Modificato.** Lo slug di Torino ora deriva dal nome della voce invece che dalla posizione nel PDF.

### v0.7.0 — 12/09/2026

**Aggiunto.** `normalizza_regole.py` e comando `ecoscan-regole`: porta le regole di categoria dal grezzo al normalizzato collegandole alle destinazioni dei rispettivi comuni. Torino: 60 regole (30 ammessi, 27 esclusi, 3 note) su 9 destinazioni. Un controllo verifica che ogni destinazione citata esista fra quelle usate dalle voci, e l'esecuzione si ferma se compare una scheda senza corrispondenza. 7 test.

**Deciso.** I testi delle regole non si spezzano in oggetti singoli (D44): sarebbe lo stesso errore di separazione già corretto sulle voci composte.

### v0.6.1 — 12/09/2026

**Aggiunto.** Modulo `trascrizioni.py` e file `data/sorgenti/manuale/napoli_esclusioni.csv`: le esclusioni dell'Umido, leggibili solo dentro un'immagine, sono state trascritte a mano da Stef e vengono unite alle regole estratte con `origine: trascrizione_manuale`. Registrate come **assenze verificate** anche Plastica e Carta, che non pubblicano esclusioni: l'avviso ora si accende solo dove il controllo non è stato fatto. 5 test.

**Corretto.** `.gitignore`: `data/sorgenti/` escludeva anche le trascrizioni manuali, che sono lavoro nostro. Ora l'esclusione è per contenuto (`data/sorgenti/*`) con eccezione della cartella `manuale/`.

### v0.6.0 — 12/09/2026

**Aggiunto.** Estrattore delle regole di categoria di Torino (`extract_torino_regole.py`, comando `ecoscan-torino-regole`): 10 schede dalle pagine 8-12, 30 oggetti ammessi e 27 esclusi. Il ruolo di ogni riga è dedotto dal font; le due schede affiancate sono separate per colonna; le celle sono ricostruite raggruppando le righe per centro orizzontale. 12 test nuovi.

**Osservato.** Le frasi del riquadro hanno due forme: elenco ("Scontrini, carta forno... NON vanno conferiti nella carta!") e avvertenza imperativa ("Non gettare l'olio negli scarichi"). Solo la prima elenca oggetti esclusi. Farmaci, Oli esausti e Rifiuti ingombranti sono schede descrittive, senza griglia di oggetti.

### v0.5.1 — 12/09/2026

**Scoperto.** L'estrazione delle esclusioni funziona, ma la fonte le pubblica come testo solo per il Vetro: su Umido, Plastica e Carta non esiste alcuna sezione "NO" e le esclusioni sono disegnate dentro un'immagine. Le pagine "Non riciclabile" e "Altre raccolte" sono davvero prive di elenchi.

**Aggiunto.** Rilevamento delle immagini informative (`info-*.png`) nel livello grezzo e messaggio che distingue "fonte senza esclusioni testuali" da "markup non gestito". 2 test.

### v0.5.0 — 12/09/2026

**Corretto.** Le pagine frazione di Napoli non producevano nessuna regola di esclusione. Causa: ammessi ed esclusi hanno markup diverso (`<strong>` sotto un'immagine i primi, elenco puntato i secondi) e il parser cercava solo i `<strong>`. La raccolta ora dipende dalla polarità. Gli elenchi di navigazione sono esclusi, e le intestazioni "SI"/"NO" non finiscono più fra le note.

**Aggiunto.** Controllo che segnala le frazioni con ammessi ma senza esclusi, e conteggi per frazione nell'output dell'estrazione. 5 test sulla struttura reale della pagina del Vetro.

**Deciso con Stef** (vedi D12, D34-D37): corpus testuale con query multimodale, nessuna descrizione visiva per ora, SQLite con sqlite-vec invece di un vector database, Load a ricostruzione totale in tre passaggi.

### v0.4.1 — 12/09/2026

**Documentazione.** Introdotti `docs/diario.md` (questo file) e `docs/glossario.md`. Il diario ha inglobato `CHANGELOG.md` e `docs/decisioni.md`, che sono stati rimossi: cronologia, decisioni, questioni aperte e annotazioni stanno ora in un unico posto. `fonti.md` e `qualita_dati.md` restano separati perché sono cataloghi di riferimento, non cronologia.

### v0.4.0 — 12/09/2026

**Aggiunto.** Transform di Torino (`transform_torino.py`), profilo delle 324 voci: 0 conflitti, 16 voci da revisionare. Il comando `ecoscan-transform` accetta `--comune {napoli,torino,tutti}` e legge sia JSONL sia CSV. 19 test nuovi sui casi reali di Torino.

**Modificato.** Il Transform è ora diviso in motore comune (`transform_comune.py`) e profili per comune: le regole che cambiano tra fonti stanno in un `Profilo`. Le voci normalizzate portano il campo `comune`. Le parentesi che elencano materiali o provenienza sono classificate come condizioni.

### v0.3.1 — 12/09/2026

**Corretto.** Cinque difetti emersi eseguendo il Transform sulle 574 voci reali, che producevano conflitti falsi, ora azzerati: separazione su " o "; separazione quando la qualificazione sta solo a destra ("Pentola e padella in acciaio"); locuzione fissa "usa e getta" separata; "(grosse Quantità)" senza "in" non riconosciuta come condizione; "(contenitori vuoti in Vetro)" classificata come sinonimo; codice materiale fuori dalla chiave di deduplicazione; refuso della fonte "biodegratabile".

**Aggiunto.** 12 test di regressione sui falsi composti reali.

### v0.3.0 — 12/09/2026

**Aggiunto.** Transform di Napoli e comando `ecoscan-transform`: normalizzazione dei nomi, classificazione delle parentesi, condizioni anche fuori dalle parentesi, separazione prudente delle voci composte, deduplicazione con segnalazione dei conflitti. 37 test su casi reali.

**Corretto.** La voce di prova `test-di-esempio` viene scartata. Il controllo `slug_duplicato` produceva falsi positivi sulle voci "Simbolo". Il controllo su "ecc" faceva match dentro "apparecchi".

### v0.2.2 — 12/09/2026

**Corretto.** Rimosso `descrizioni_destinazioni` dalle voci: il parser non lo popolava mai e il dato appartiene alla destinazione.

**Modificato.** `info_nello_slug` è segnalato come risolto quando l'informazione è già nel campo avvertenza, che è pulito.

### v0.2.1 — 12/09/2026

**Aggiunto.** Comando `ecoscan-ispeziona`: riepiloga il grezzo di Napoli senza riscaricare nulla.

**Confermato.** Estrazione completa di Napoli: 584 voci, tutte con destinazione, strategia "parentesi" al 100%, nessuna discordanza con l'indice, 6 pagine frazione.

### v0.2.0 — 12/09/2026

**Modificato.** Passaggio a **uv**: `pyproject.toml` e `uv.lock` al posto di `requirements.txt` e `pytest.ini`. Codice riorganizzato come package `src/ecoscan`. Tre comandi installabili.

**Aggiunto.** `ecoscan/percorsi.py` con radice del progetto e override `ECOSCAN_RADICE`.

### v0.1.1 — 12/09/2026

**Corretto.** Le destinazioni nelle pagine voce risultavano sempre vuote: i nodi di testo sono frammentati, ora si legge il testo aggregato degli elementi. Il dettaglio delle regole non veniva raccolto quando separato da un `<br>`.

**Aggiunto.** Secondo passaggio di estrazione con ripiego sul vocabolario di destinazioni; diagnostica per strategia e discordanze con l'indice.

### v0.1.0 — 11/09/2026

**Aggiunto.** Estrattore Torino (324 voci dal Rifiutologo AMIAT 2025), estrattore Napoli, schema SQLite a tre livelli con script dimostrativo, 17 test, documentazione di fonti, decisioni e qualità dei dati.

### Prima del repo

Scelta dell'idea e architettura iniziale (con un altro assistente). Revisione dell'architettura, scelta del modello per l'hardware, progettazione del retrieval ibrido e dei livelli di evidenza. Confronto fra Milano, Torino, Roma e Firenze e scelta di Torino.
