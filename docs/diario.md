# Diario di progetto — EcoScan Local

File unico di riferimento per capire **cosa è stato fatto, perché, e cosa resta da fare**.
Ha inglobato i precedenti `CHANGELOG.md` e `docs/decisioni.md`.

Altri documenti, che restano separati perché sono cataloghi di riferimento e non cronologia:
- [fonti.md](fonti.md) — da quali documenti e URL provengono i dati
- [qualita_dati.md](qualita_dati.md) — catalogo dei difetti di ciascuna fonte e come sono trattati
- [glossario.md](glossario.md) — significato dei termini usati qui

## Come si aggiorna

Va aggiornato **a ogni cambiamento sostanziale**, non a ogni riga di codice. In pratica:

- una **modifica** entra in "Cronologia" quando cambia il comportamento del sistema o i dati prodotti;
- una **decisione** entra nella tabella quando fissa una regola che vincola il lavoro futuro. Le decisioni non si cancellano: quando cadono, restano con stato "superata da Dn";
- una **questione aperta** si aggiunge quando si scopre un problema che non si risolve subito, e si toglie quando è chiusa;
- un'**annotazione** serve per ciò che non è né decisione né modifica, ma che servirà ricordare (es. una scoperta sui dati, una trappola in cui si è già caduti).

---

## Stato attuale (v0.4.0, 12/09/2026)

| Componente | Stato |
|---|---|
| Estrattore Torino (PDF) | Completo: 324 voci dall'elenco A-Z |
| Estrattore Napoli (HTML) | Completo: 584 voci dal dizionario, 6 pagine frazione |
| Transform Napoli | Eseguito: 574 voci normalizzate, 0 conflitti, 15 da revisionare |
| Transform Torino | Eseguito: 324 voci normalizzate, 0 conflitti, 16 da revisionare |
| Schema dati (SQLite) | Definito e verificato con Torino completo e un campione di Napoli |
| Regole di categoria — Napoli | Estrattore corretto: ammessi ed esclusi. Da rieseguire per aggiornare il grezzo |
| Regole di categoria — Torino | **Da fare**: pagine 8-12 del PDF mai estratte |
| Revisione manuale | **Da fare**: 31 voci segnalate |
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
| D33 | Un controllo fallisce se una frazione ha ammessi ma nessun escluso | Una fonte muta è quasi sempre un markup non gestito, non una fonte davvero priva di esclusioni | Accettata |

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
   - *Napoli*: **risolto in v0.5.0**. Resta da rieseguire `ecoscan-napoli` (la cache HTML rende l'operazione immediata) e verificare i conteggi per frazione.
   - *Torino*: pagine 8-12 del PDF, mai estratte. Gli esclusi sono **una frase in prosa** nel riquadro "I RIFIUTATI" ("Medicinali, pile, oli... NON vanno gettati nel..."), da spezzare su virgole e congiunzioni. Due frazioni per pagina: serve la divisione per colonna già usata per l'elenco A-Z. Il riquadro va identificato dalla frase ("NON vanno", "NON sono", "NON rientrano"), non dall'etichetta, che cambia.
2. **Revisione manuale di 31 voci** (15 Napoli, 16 Torino). Serve prima un meccanismo: le decisioni vanno in file CSV versionati (`data/revisioni/<comune>.csv`) che il Transform applica in coda, altrimenti si perdono a ogni riesecuzione.
3. **Asterischi.** 6 voci a Napoli (insetticida, trielina, smalto, solventi, spray, sostanze chimiche etichettate T e/o F: sono rifiuti pericolosi) e 1 a Torino rimandano a note non estratte. Per Torino la nota è nel PDF a pagina 21; per Napoli va cercata sul sito.
4. **Caricamento del normalizzato nello schema SQLite.** Finora provato solo con un campione.
5. **Pagine "Non riciclabile" e "Altre raccolte" di Napoli**: zero regole anche fra gli ammessi. Con il nuovo estrattore si saprà se erano un problema di markup o se sono davvero prive di elenchi.
6. **Serving**: indici FTS5 a trigrammi, embedding, ricerca ibrida con RRF.
7. **Valutazione**: set di foto etichettate e metriche (riconoscimento, destinazione per comune, latenza su CPU). Mai iniziata, ed è ciò che distingue un prototipo da un lavoro difendibile.
8. **Dove conferire**: 363 voci su 584 a Napoli rimandano a isole ecologiche o ecopunti. Prima o poi l'agente deve dire *dove* si trovano.
9. **Opuscolo PDF di Napoli** (`Asia_Opuscolo_A5_new-1.pdf`): mai consultato, potrebbe contenere regole assenti dal sito.

---

## Annotazioni

Cose imparate che non sono decisioni, ma che conviene ricordare.

- **I conflitti sono una diagnosi del Transform, non dei dati.** Su 898 voci, tutti e 6 i conflitti iniziali erano difetti delle regole: separazioni sbagliate, materiale letto come sinonimo, codice escluso dalla chiave. Corretti quelli, restano zero. Le due fonti, dove si sovrappongono, sono internamente coerenti.
- **Le due fonti hanno difficoltà speculari.** A Torino l'ostacolo è l'estrazione (destinazione codificata in colori e icone), ma i dati sono puliti. A Napoli l'estrazione è facile e i dati sono sporchi. La scelta di due formati complementari ha dato il contrasto giusto.
- **Le esclusioni spiegano il dizionario.** La pagina del vetro di Napoli esclude bicchieri, piatti, pirofile e lastre: esattamente le voci che nel dizionario finiscono nel non riciclabile. Ciò che sembrava incoerenza è una regola dichiarata.
- **Divergenze fra comuni utili da citare**: bicchiere di vetro (Napoli non riciclabile, Torino vetro); tappo di sughero (Napoli organico, Torino centro di raccolta o organico); pentole e padelle (Napoli plastica e metalli, Torino centro di raccolta). Una convergenza: il vetro dei profumi non è riciclabile in entrambi.
- **Trappole già incontrate, da non ripetere**: i nodi di testo frammentati di Elementor; il match di "ecc" dentro "appare**cc**hi"; gli slug che finiscono con un numero che è un codice materiale e non un contatore; un test che passava solo perché la fixture era più semplice della realtà.

---

## Cronologia

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
