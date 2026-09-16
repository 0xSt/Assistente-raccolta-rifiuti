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

## Stato attuale (v0.9.0, 12/09/2026)

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
| API FastAPI | Fatto: analizza, continua, cerca, comuni, salute, riscontro |
| Frontend a chat | Fatto: Streamlit, allegato immagine, chiarimenti, riscontro |
| MLflow, Docker | Da fare |
| Regole di categoria — Napoli | Completo per quanto la fonte pubblica: 38 ammessi, 11 esclusi (5 Vetro estratti + 6 Umido trascritti a mano), 2 assenze verificate |
| Regole di categoria — Torino | Estratte: 10 schede, 30 ammessi, 27 esclusi |
| Revisione manuale | **Completa**: 32 decisioni prese (16 per comune), 0 aperte, 0 voci da revisionare |
| Serving (FTS5, embedding, ricerca ibrida) | Da fare |
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
4. **Valutazione**: set di foto etichettate e misura del retrieval (lessicale, semantico, ibrido). È il passo che rende dicibile qualcosa di quantitativo.
5. ~~Pagine "Non riciclabile" e "Altre raccolte" di Napoli~~ **Chiuso**: sono davvero prive di elenchi, hanno solo una frase di invito. Non è un difetto dell'estrattore.
6. **Serving**: indici FTS5 a trigrammi, embedding, ricerca ibrida con RRF.
7. **Valutazione**: set di foto etichettate e metriche (riconoscimento, destinazione per comune, latenza su CPU). Mai iniziata, ed è ciò che distingue un prototipo da un lavoro difendibile.
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
- **I comandi vanno provati eseguendoli, non solo leggendoli.** `--diagnostica` usava una variabile definita più sotto: un errore che nessun test coglieva perché nessuno eseguiva quel ramo. Ora tre test lanciano `main()` con la diagnostica sostituita da una finta.
- **Un test che dipende dall'ambiente di chi lo esegue non è un test.** `test_il_file_env_viene_letto` passava da me e falliva sul portatile di Stef, perché ereditava le variabili della macchina. Ora l'ambiente del sottoprocesso viene ripulito di tutte le `ECOSCAN_*`.
- **Trappole già incontrate, da non ripetere**: i nodi di testo frammentati di Elementor; il match di "ecc" dentro "appare**cc**hi"; gli slug che finiscono con un numero che è un codice materiale e non un contatore; un test che passava solo perché la fixture era più semplice della realtà.

---

## Cronologia

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
