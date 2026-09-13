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
| D2 | Modello base `gemma4:e2b`, `gemma4:e4b` come confronto in valutazione | Laptop con 16 GB di RAM, CPU Ryzen, nessuna GPU dedicata | Accettata |
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
| D12 | Un solo file SQLite: FTS5 + vettori con **sqlite-vec**, nessun vector database separato | ~3000 vettori a 256 dimensioni sono 3 MB: la ricerca esaustiva è sotto il millisecondo. Un indice approssimato serve a milioni di vettori, non a migliaia, e un container in più competerebbe per la RAM con il modello | Accettata |
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
3. **Serving**: indice FTS5 a trigrammi e vettori, da costruire sopra il livello relazionale.
4. ~~Pagine "Non riciclabile" e "Altre raccolte" di Napoli~~ **Chiuso**: sono davvero prive di elenchi, hanno solo una frase di invito. Non è un difetto dell'estrattore.
5. **Serving**: indici FTS5 a trigrammi, embedding, ricerca ibrida con RRF.
6. **Valutazione**: set di foto etichettate e metriche (riconoscimento, destinazione per comune, latenza su CPU). Mai iniziata, ed è ciò che distingue un prototipo da un lavoro difendibile.
7. **Dove conferire**: 363 voci su 584 a Napoli rimandano a isole ecologiche o ecopunti. Prima o poi l'agente deve dire *dove* si trovano.
8. **Opuscolo PDF di Napoli** (`Asia_Opuscolo_A5_new-1.pdf`): mai consultato, potrebbe contenere regole assenti dal sito.

---

## Annotazioni

Cose imparate che non sono decisioni, ma che conviene ricordare.

- **L'asterisco di Napoli non rimanda a niente.** Sei voci lo portano nel nome ma nessuna pagina ha una nota corrispondente: è un residuo tipografico della fonte, verificato il 12/09/2026. Registrato nelle decisioni, così non lo si ricerca una seconda volta.
- **I conflitti sono una diagnosi del Transform, non dei dati.** Su 902 voci, tutti e 6 i conflitti iniziali erano difetti delle regole: separazioni sbagliate, materiale letto come sinonimo, codice escluso dalla chiave. Corretti quelli, restano zero. Le due fonti, dove si sovrappongono, sono internamente coerenti.
- **Le due fonti hanno difficoltà speculari.** A Torino l'ostacolo è l'estrazione (destinazione codificata in colori e icone), ma i dati sono puliti. A Napoli l'estrazione è facile e i dati sono sporchi. La scelta di due formati complementari ha dato il contrasto giusto.
- **ASIA pubblica poche esclusioni, e quasi solo come grafica.** Testo solo per il Vetro; dentro l'immagine per l'Umido; per Plastica e Carta non esistono proprio. Torino ne pubblica 27 contro le 11 di Napoli: la stessa informazione, con profondità molto diversa. Una fonte può essere incompleta *per come è pubblicata*, non per come la leggiamo: il controllo che distingue i due casi è ciò che ha permesso di capirlo in un giro solo.
- **Le esclusioni spiegano il dizionario.** La pagina del vetro di Napoli esclude bicchieri, piatti, pirofile e lastre: esattamente le voci che nel dizionario finiscono nel non riciclabile. Ciò che sembrava incoerenza è una regola dichiarata.
- **Divergenze fra comuni utili da citare**: bicchiere di vetro (Napoli non riciclabile, Torino vetro); tappo di sughero (Napoli organico, Torino centro di raccolta o organico); pentole e padelle (Napoli plastica e metalli, Torino centro di raccolta). Una convergenza: il vetro dei profumi non è riciclabile in entrambi.
- **Trappole già incontrate, da non ripetere**: i nodi di testo frammentati di Elementor; il match di "ecc" dentro "appare**cc**hi"; gli slug che finiscono con un numero che è un codice materiale e non un contatore; un test che passava solo perché la fixture era più semplice della realtà.

---

## Cronologia

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
