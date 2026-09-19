# La valutazione

> Aggiornato alla **v0.44.1**.

Questo documento spiega **cosa misura** il sistema di valutazione, **perché** misura quelle
cose e non altre, **come** si usa e **come si leggono** i numeri che produce.

---

## 0. Il quadro, in una pagina

La valutazione è fatta di due strumenti, con due costi e due ritmi diversi.

| strumento | cosa misura | costo | quando si lancia |
|---|---|---|---|
| `ecoscan-valuta --senza-modello` | il **recupero**: il documento giusto esce dall'indice? | secondi | a ogni modifica di indice, formulazioni, `k` |
| `ecoscan-valuta` | recupero **+ scelta**: la risposta finale è quella attesa? | minuti | prima di chiudere una modifica |
| `ecoscan-valuta-foto` | tutto, **partendo dalla foto**, più i tempi su CPU | 20-40 minuti | una volta per rilascio |

Un terzo comando, `ecoscan-campiona`, non misura: prepara il dataset estraendo voci dal
database.

Ciò che viene misurato, in tutto, sono **otto numeri**:

| gruppo | numeri | risponde a |
|---|---|---|
| recupero | `recall@1`, `recall@4`, `recall@8` | il documento giusto arriva al modello? E in che posizione? |
| risposta | `contenitore_corretto`, `copertura` | manda qualcuno nel posto sbagliato? Perde un'alternativa? |
| astensione | `astensione_corretta`, `astensione_a_sproposito` | sa dire "non lo so" quando è giusto, e solo allora? |
| costo | `riconoscimento_p50/p90`, `corrette_dalla_foto` | quanto costa la visione, in secondi e in punti persi? |

E quello che **non** viene misurato, dichiarato qui una volta per tutte: la qualità della
spiegazione, l'usabilità dell'interfaccia, la correttezza dell'ETL (che ha i suoi test) e
la soddisfazione dell'utente.

---

## 1. Il problema: un errore, quattro cause possibili

Quando l'assistente dà una risposta sbagliata, l'errore può essere nato in quattro punti:

1. **il riconoscimento** — il modello di visione ha visto un oggetto che non c'era;
2. **il recupero** — il documento giusto non è arrivato fra i candidati;
3. **la scelta** — il documento c'era, ma il modello ne ha preso un altro;
4. **l'attesa** — il sistema aveva ragione e il caso torto.

Le prime tre si riparano in tre posti diversi e non si scambiano fra loro:

| difetto | dove si interviene |
|---|---|
| riconoscimento | prompt di riconoscimento, ridimensionamento delle foto, modello |
| recupero | formulazioni indicizzate, `k`, filtri, qualità dei nomi |
| scelta | prompt di scelta, politiche del codice (materiali, specificità) |

La quarta è la più insidiosa, perché non somiglia a un errore: somiglia a un numero. È
successa il 18/09 con il caso `frullatore` (D171), scritto con le destinazioni di
"Elettrodomestici" quando ASIA ha una voce `Frullatore` che manda ai piccoli RAEE. Il
sistema dava la risposta **più specifica e più giusta**, e la valutazione la contava come
errore. Da lì due contromisure permanenti: l'uscita mostra sempre dove portavano i
documenti trovati, e le attese del campione vengono dal database invece che dalla memoria
di chi scrive il caso.

Senza una misura, la diagnosi si fa a mano, un caso per volta: per **la forchetta
d'acciaio** (D78–D81) sono servite due sessioni di ricerche su `/cerca` per stabilire che
il documento giusto *usciva* e che quindi il difetto era nel prompt di scelta. Lo strumento
descritto qui fa quella diagnosi su tutti i casi in una volta.

---

## 2. La teoria: il recupero è un tetto

In un sistema RAG il generatore può usare solo ciò che il recupero gli passa. Se il
documento giusto non è fra i candidati, **nessun prompt, nessun modello più grande e nessuna
temperatura più bassa** possono produrre la risposta giusta se non per caso.

Formalmente: detta `R` la probabilità che il documento giusto sia fra i primi `k` candidati
(*recall@k*) e `C` la probabilità che la risposta finale sia corretta,

```
C ≤ R + (probabilità di indovinare per un'altra strada)
```

Il recall@k è quindi un **tetto** (*ceiling*). Ne discendono due conseguenze pratiche:

- **misurare solo la correttezza finale non dice dove intervenire.** Un 60% di risposte
  giuste può venire da un recupero al 95% con una scelta debole, o da un recupero al 62%
  con una scelta quasi perfetta. Sono due sistemi diversi che chiedono due lavori diversi;
- **il recupero si misura separatamente e costa poco.** Non richiede il modello: si eseguono
  le ricerche e si guarda se fra i candidati c'è un documento che porta dove doveva. Secondi
  invece di minuti.

C'è anche un motivo di metodo. Il modello di visione è **rumoroso e lentissimo su CPU**: se
a ogni esecuzione rileggessimo le foto, una differenza fra due esecuzioni potrebbe venire
dal recupero, dalla scelta *o* dal modello che quel giorno ha visto qualcosa di diverso —
tre cause per un solo effetto. Per questo un **caso parte dal riconoscimento, non dalla
foto**: fissando quel passaggio, ciò che resta misura solo recupero e scelta. È la stessa
ragione per cui nell'agente `analizza` e `rispondi` sono due metodi separati (D72).

Il riconoscimento non resta però senza misura: ha il suo strumento, `ecoscan-valuta-foto`
(§7), che gira di rado proprio perché costa.

### Le metriche scartate, e perché

- **precision@k** — non interessa. Al modello si passano `k` candidati comunque: candidati
  in più che non c'entrano costano qualche parola di prompt, non una risposta sbagliata;
- **MRR / nDCG** — assumono che la posizione conti in modo graduale. Qui il modello legge
  *tutti* i candidati insieme e ne sceglie uno: essere primo o quinto non cambia granché.
  La posizione serve come indizio diagnostico, non come obiettivo da ottimizzare;
- **la posizione media** — usata fino alla v0.42.0 e **rimossa**. Era una media calcolata
  sui soli casi trovati, quindi peggiorava quando una modifica faceva finalmente uscire un
  documento difficile in posizione 7. Una metrica che punisce i miglioramenti è peggio di
  nessuna metrica. Al suo posto c'è la curva `recall@1/@4/@8`, che usa lo stesso dato
  (`posizione`) per rispondere alla domanda utile: il documento esce, e quanto in alto;
- **la similarità media** — è un numero che si può migliorare senza migliorare niente.

### Cosa conta come "recuperato"

Un candidato conta se **porta a una delle destinazioni attese**, non se ha un certo `id`
(D154). In questi dizionari lo stesso oggetto compare spesso sotto nomi diversi ("Stoviglie
in metallo" e "Posate" possono essere due voci entrambe corrette), e all'utente interessa il
contenitore, non quale riga del regolamento è stata citata. Legare l'attesa all'`id` avrebbe
reso il dataset fragile a ogni rigenerazione dei dati.

---

## 3. Il dataset: tre insiemi, tre numeri

I casi stanno in `data/valutazione/casi/`, **un file per insieme**, e il nome del file è
l'origine del caso. Non si mescolano mai in una percentuale sola, perché hanno autorità e
scopi diversi (è D172 portato alle sue conseguenze).

| file | cosa contiene | quanti | come si legge |
|---|---|---|---|
| `regressioni.jsonl` | casi nati da errori osservati | 18 | **pass/fail**: 18 su 18 |
| `campione.jsonl` | campione stratificato del dizionario | 63 | **percentuali**: è la stima |
| `assenti.jsonl` | oggetti che il comune non copre | 11 | le due **astensioni** |

### Perché il campione esiste

Le regressioni sono preziose ma sono, per costruzione, i punti in cui il sistema aveva già
sbagliato: una percentuale calcolata lì misura la storia dei difetti, non il sistema. Fino
alla v0.42.0 il numero pubblicato era esattamente quello, e non stimava niente.

Il campione è estratto **dai dati**, con `ecoscan-campiona`, e stratificato su tre assi
perché il sistema non si comporta allo stesso modo ovunque:

| asse | strati | perché |
|---|---|---|
| comune | Napoli, Torino | due fonti con difetti speculari: metà e metà, non in proporzione alle voci |
| canale | ordinaria, centro di raccolta, itinerante, domicilio, contenitore dedicato | è dove sono nati tutti gli errori osservati (microonde, divano) |
| alternative | una destinazione, più di una | senza voci a più destinazioni la copertura non verrebbe mai messa alla prova |

Il canale di una voce è **il più faticoso** fra i suoi: una voce che si può buttare nel
sacco *oppure* portare al centro di raccolta, per la valutazione, è una voce da centro di
raccolta. È lì che la risposta deve spiegare qualcosa in più.

Gli strati piccoli hanno una quota minima di uno: una proporzione pura cancellerebbe il
ritiro a domicilio, che è una voce su ventisette ed è dove il sistema ha sbagliato.

L'estrazione è **riproducibile**: `--semina 42` fissa il generatore, quindi chiunque
rilanci lo stesso comando ottiene lo stesso campione. È ciò che permette di dire, in una
relazione, di quale campione si sta parlando.

### La divisione del lavoro, che è il punto

Per una voce del dizionario **l'attesa è la fonte**, e sta già nel database. Quello che una
macchina non può inventare è la **domanda**: come una persona nomina quell'oggetto. Quindi
il campionatore scrive la bozza con l'attesa già piena e `oggetto` vuoto:

```json
{"comune": "Napoli", "oggetto": "", "voce_fonte": "Vasetto in plastica per alimenti",
 "destinazioni_attese": ["Plastica e Metalli"], "livello_atteso": 1,
 "strato": {"canale": "raccolta_ordinaria", "alternative": 1}}
```

e il lavoro umano si riduce a riempire quella casella: `"il barattolo dello yogurt"`.

**La regola d'oro**: la domanda non deve mai essere il nome della fonte. Cercare "Cartone
per pizze" e trovare "Cartone per pizze" non misura il recupero, misura che l'indice esiste.
Se per una voce non viene in mente un modo diverso di dirla, quella voce non è un buon caso
e si cancella. Il test `test_nessuna_domanda_coincide_con_la_voce_da_cui_nasce` fa fallire
la suite se una domanda coincide con la sua voce: nella prima compilazione ne ha prese tre
("giornale", "bicchiere di vetro", "bicchieri di vetro"), che erano tautologie arrivate
dalle vecchie sonde.

Il campo `voce_fonte` resta nel caso: è ciò che permette di **ricontrollare un'attesa** in
dieci secondi invece di riaprire la fonte.

### Perché gli assenti esistono

Il difetto classico di un sistema RAG è rispondere comunque. Senza casi la cui risposta
giusta è il silenzio, quel difetto non ha un numero e resta invisibile. Un caso assente ha
`destinazioni_attese` vuote e `livello_atteso: 3`, ed è valido proprio per quella
dichiarazione: l'attesa vuota deve essere una scelta, non una riga scritta a metà.

Gli undici casi sono stati verificati uno per uno contro il database, e la verifica sta
nella nota. Due trappole incontrate mentre li scrivevo, che vale la pena ricordare:

- **"pneumatico" sembrava assente e non lo era**: la voce si chiama `Pneumatici`, al
  plurale. L'assenza va verificata sui dati, mai a memoria;
- **"violino" è assente a Torino ma non a Napoli**, che ha la voce `Strumento musicale`. Un
  oggetto non coperto in un comune può essere coperto nell'altro, e un caso negativo
  sbagliato è esattamente l'errore del frullatore al contrario: punirebbe il sistema per
  aver dato la risposta giusta.

Sono rimasti fuori di proposito i rifiuti pericolosi in cui il livello 3 sarebbe una
risposta *sbagliata* e non solo incompleta (amianto, fuochi d'artificio): mandarli al
centro di raccolta senza dirlo è un consiglio che non voglio far passare per corretto in
una metrica.

### Come si aggiunge un caso

**Ogni volta che si scopre un errore vero, il primo gesto è scriverlo in
`regressioni.jsonl`**: da quel momento in poi quella regressione non può ripassare
inosservata. Per allargare il campione, invece:

```bash
uv run ecoscan-campiona --n 30 --semina 7    # salta le voci già coperte
# si riempiono gli "oggetto" nella bozza, si cancellano le righe non riformulabili
# si accodano le righe compilate a data/valutazione/casi/campione.jsonl
```

---

## 4. Le metriche, una per una

### Recupero — `recall@1`, `recall@4`, `recall@8`

Frazione di casi in cui un documento che porta alla destinazione attesa si trova entro i
primi *n* candidati. Le tre soglie si derivano da `k`, quindi lanciando con `-k 20` la curva
si legge a 1, 10 e 20 invece di restare ferma a 8.

Si legge così:

| osservazione | diagnosi |
|---|---|
| `recall@8` basso | il documento non esce: formulazioni, nomi delle voci, indice |
| `recall@8` alto ma `recall@1` basso | esce ma tardi: ordinamento, prefissi di embedding, sinonimi |
| `recall@4 ≈ recall@8` | allargare `k` non serve, e si può dichiararlo |

Accanto c'è `recupero`, che è la stessa cosa senza vincolo di posizione ed è il numero che
si confronta con le esecuzioni precedenti alla v0.43.0.

### Risposta — `contenitore_corretto` e `copertura`

Fino alla v0.42.0 la risposta era giusta o sbagliata, per uguaglianza esatta degli insiemi.
Quella definizione confondeva due errori che si riparano in punti diversi e che pesano in
modo molto diverso per chi usa l'app:

| metrica | definizione | cosa protegge |
|---|---|---|
| `contenitore_corretto` | la risposta non è vuota **e** ogni destinazione proposta è fra le attese | non mandare nessuno nel cassonetto sbagliato |
| `copertura` | `|proposte ∩ attese| / |attese|`, mediata sui casi | non perdere un'alternativa comoda |

Il secondo è il difetto vero di microonde e divano: la risposta diceva "isola ecologica" ed
era **vera**, ma taceva il ritiro a domicilio. Con l'uguaglianza esatta era "sbagliata"
esattamente come dire "Organico", che è tutt'altra cosa.

`risposte_perfette` è la congiunzione dei due (contenitore giusto e nulla di perso), cioè la
vecchia metrica: resta perché il confronto fra esecuzioni ha bisogno di una nozione binaria
di "caso vinto".

### Astensione — `astensione_corretta` e `astensione_a_sproposito`

Si leggono **in coppia**, come precision e recall:

- `astensione_corretta` — dei casi non coperti, quanti hanno ricevuto un livello 3;
- `astensione_a_sproposito` — dei casi coperti, quanti hanno ricevuto un livello 3.

Il primo da solo si massimizza tacendo sempre, e un sistema muto non è prudente: è inutile.

### Livello — `livello_atteso`

La risposta viene dal livello di evidenza giusto (voce di dizionario contro regola di
categoria). Vale `None`, non `0`, quando non è stato misurato: senza modello il livello non
viene mai determinato, e la v0.41.2 riportava "0% di livelli corretti" su un'esecuzione in
cui il livello non era stato misurato affatto. **Una metrica che mente è peggio di una che
manca, perché la si legge.**

### Il principio comune ai denominatori

Ogni numero si calcola sul suo sottoinsieme: le percentuali della scelta sui casi in cui la
scelta è stata eseguita, le astensioni sui soli casi negativi, il recall sui soli casi con
un'attesa. Un numero che manca si nota; un numero calcolato su un denominatore sbagliato no.

---

## 5. Come si usa

```bash
# il tetto: solo recupero, nessun modello. Secondi.
uv run ecoscan-valuta --senza-modello

# la misura completa: recupero + scelta. Minuti, serve Ollama acceso.
uv run ecoscan-valuta

# un insieme o un comune per volta, o un k diverso
uv run ecoscan-valuta --insieme regressioni
uv run ecoscan-valuta --comune Napoli -k 12

# salva l'esecuzione, per confrontarla dopo una modifica
uv run ecoscan-valuta --senza-modello --salva data/valutazione/esecuzioni/prima.json
# ... si modifica il prompt, le formulazioni, k ...
uv run ecoscan-valuta --senza-modello --confronta data/valutazione/esecuzioni/prima.json
```

Il flusso che conviene, quando si lavora su una modifica:

1. `--senza-modello --salva prima.json` — il tetto attuale, in pochi secondi;
2. si applica la modifica (formulazioni, filtri, `k`, nomi);
3. `--senza-modello --confronta prima.json` — il tetto si è alzato?
4. solo se il tetto tiene, si esegue la misura completa con il modello.

---

## 6. Come si leggono i numeri

### La diagnosi caso per caso

È la parte azionabile, ed è una tabella 2×2 con una riga in più:

| | risposta giusta | manca un'alternativa | risposta sbagliata |
|---|---|---|---|
| **documento recuperato** | `corretto` | `contenitore giusto, manca un'alternativa` | **`il documento c'era, non è stato scelto`** |
| **documento non recuperato** | `corretto per un'altra strada` | — | `il documento non è stato recuperato` |

- **"c'era, non è stato scelto"** → il recupero ha fatto il suo. Si interviene sul **prompt
  di scelta** o sulle politiche del codice. È stata la diagnosi della forchetta;
- **"non è stato recuperato"** → il modello non poteva sceglierlo. Si interviene
  sull'**indice**: formulazioni, nomi, `k`. Toccare il prompt qui è tempo perso;
- **"manca un'alternativa"** → la risposta è vera ma incompleta. Si guarda la presentazione
  e le politiche che scelgono la variante, non il recupero;
- **"corretto per un'altra strada"** → la risposta è giusta ma il documento atteso non
  c'era: di solito una regola di categoria ha rimediato a un dizionario incompleto. È una
  correttezza fragile: va bene oggi, ma l'attesa del caso o i dati vanno guardati.

Per ogni caso fallito l'uscita stampa cosa era atteso, cosa è arrivato, **cosa è di troppo**
e **cosa manca**, e — quando la risposta è vuota — dove portavano i documenti trovati, con
l'avvertenza di controllare l'attesa prima di dare la colpa al recupero.

C'è anche il recupero spezzato **per comune e per canale**: la media dice "88%", lo strato
dice dove scrivere le prossime formulazioni.

### Il confronto fra due esecuzioni

`--confronta` elenca separatamente i **casi guadagnati** e i **casi persi**, non solo la
media. Una modifica che guadagna cinque casi e ne perde tre è un pareggio nella percentuale
e un problema nella realtà.

Ogni esecuzione salvata porta con sé un blocco `esecuzione` con data, `k`, modalità,
composizione del dataset e la configurazione completa dell'agente (modello, versioni dei
prompt con impronta). Se le due esecuzioni non sono state fatte nelle stesse condizioni, il
confronto lo dice in testa:

```
ATTENZIONE: le due esecuzioni non sono state fatte nelle stesse condizioni
    k: 8 -> 12
    prompt_scelta: scelta v8@a3f1 -> scelta v9@7c2d
```

Non blocca — a volte confrontare due configurazioni è proprio ciò che si vuole — ma
impedisce di attribuire alla modifica sbagliata una differenza che viene da `k`.

### Cosa si vede mentre gira

Ogni caso stampa una riga con contatore, esito, secondi per caso e tempo stimato alla
fine, e in testa ci sono le impostazioni in uso e la composizione del dataset. Vale anche
per `--senza-modello`: "gira in secondi" è vero solo con l'indice caldo, perché ogni caso
calcola un embedding per ogni formulazione — fino a sette domande per due livelli.

    Impostazioni: qdrant=http://localhost:6333 | modello=embeddinggemma | arricchimento=si …

    92 casi (18 regressioni, 63 campione, 11 assenti) · k=8 · solo recupero, nessun modello
    Preparo Qdrant e il vettorizzatore...
      [ 47/92] ok  Napoli · monitor del pc         0.8 s/caso · ~36 s alla fine

### La serie storica su MLflow

Ogni esecuzione diventa anche una **run** nell'esperimento `ecoscan-valutazione`, separato
da `ecoscan-chat` delle conversazioni: parametri (la stessa configurazione), metriche
(tutte quelle misurate) e l'esito completo come allegato. Serve a una cosa che i file JSON
non danno: la tabella di dieci esecuzioni fra due versioni, con i parametri accanto ai
numeri. Come tutto il tracciamento del progetto non è mai bloccante (D116): con MLflow
spento la valutazione stampa i suoi numeri, avvisa in una riga e finisce. Si spegne con
`--senza-mlflow`.

**Ogni esito viene detto**, perché una registrazione che non avviene e non lo dice è
peggio di un errore: si continua a cercare la run in una lista dove non è mai arrivata.
A registrazione riuscita l'uscita stampa il **link diretto**; se MLflow è spento o
irraggiungibile lo dichiara con il motivo. I tre passaggi — parametri, metriche, allegato —
sono protetti uno per uno, quindi un allegato che non passa non fa perdere le metriche.

---

## 7. Le foto: il costo del riconoscimento

`ecoscan-valuta-foto` è l'unico strumento che parte davvero dalla foto, e risponde alla
domanda che il taglio di §2 lascia fuori: **partendo da una foto vera, quante volte arriva
la risposta giusta?**

Per ogni foto esegue **due volte** la stessa richiesta:

1. **reale** — riconoscimento dalla foto, poi risposta. È il percorso dell'utente;
2. **ideale** — riconoscimento *dichiarato* nell'etichetta, poi risposta. Lo stesso percorso
   senza il modello di visione.

La differenza fra i due numeri è il **costo del riconoscimento**, isolato:

```
corrette dalla foto 68%   ·   corrette dall'oggetto vero 86%   ->   -18 punti di visione
```

Senza il secondo giro, una risposta sbagliata non direbbe se il modello ha visto male o se
il resto del sistema ha sbagliato. Con il secondo giro lo dice, e costa pochi secondi in più
per foto (è `rispondi`, non `analizza`). Le foto perse solo per la visione sono contate a
parte e marcate `VIS` nell'uscita.

**I tempi** si riportano come **mediana e p90**, mai come media: i tempi hanno code lunghe,
e la media di dieci foto veloci e una lenta descrive una situazione che non è capitata a
nessuno. Il percentile usa il metodo del rango più vicino, quindi il numero pubblicato è
sempre un tempo davvero cronometrato.

Le etichette stanno in `data/valutazione/foto/foto.jsonl` (versionate: dicono cosa il
sistema deve saper fare); le immagini in `data/valutazione/foto/immagini/` e **non sono
versionate**. Il file contiene già venti righe pronte, con le attese ricavate dal database:
basta scattare le foto con quei nomi. Fra queste ci sono tre coppie volute — lo stesso
oggetto nei due comuni, dove la risposta *deve* cambiare, e il cartone della pizza con e
senza il testo dell'utente, dove nel secondo caso l'agente deve chiedere invece di
indovinare.

Con i tre insiemi insieme si può scomporre la correttezza finale invece di riportare un
numero solo:

```
end-to-end (foto)  =  riconoscimento  ×  recupero  ×  scelta
```

ed è la frase che rende otto numeri un discorso.

---

## 8. Limiti dichiarati

- **il campione è piccolo** (63 casi). Un caso vale un punto e mezzo: le percentuali si leggono
  come indicatori di direzione, non come misure di precisione. Farlo crescere con
  `ecoscan-campiona` è il lavoro che rende più di ogni altro;
- **il campione non è bilanciato fra i comuni** (36 Napoli, 27 Torino), perché una parte
  viene dalle vecchie sonde, che erano napoletane. Le misure per comune vanno lette
  sapendolo;
- **le attese le abbiamo decise noi**, anche quando vengono dal database: è il database a
  dire dove va una voce, siamo noi a dire che *quella* voce è la risposta giusta per *quella*
  domanda. Un caso con l'attesa sbagliata rende il sistema peggiore mentre sembra
  migliorarlo — è già successo (§1);
- **una sola esecuzione per misura.** Il modello non è deterministico: due esecuzioni
  identiche possono differire di un caso o due. Le differenze piccole (uno-due casi) non si
  interpretano; la configurazione salvata serve almeno a garantire che non sia cambiato
  altro;
- **non si misura la qualità della spiegazione**, solo la destinazione. Una risposta giusta
  con una motivazione confusa conta come corretta;
- **i confronti con un'alternativa sono due soli**: `-k` da riga di comando e
  `ECOSCAN_ARRICCHIMENTO=no`, che riproduce l'indice della v0.43.0 e permette di misurare
  quanto vale l'arricchimento dei documenti. Le altre ablazioni (ricerca lessicale,
  formulazioni disattivate) sono state valutate e rimandate, per non aggiungere all'agente
  parametri che esistono solo per la valutazione.

---

## 9. Dove sta nel codice

| file | cosa fa |
|---|---|
| `valutazione/casi.py` | cos'è un caso, i tre insiemi, come si leggono e si scrivono |
| `valutazione/campiona.py` | `ecoscan-campiona`: estrazione stratificata e riproducibile dal database |
| `valutazione/esegui.py` | `ecoscan-valuta`: esecuzione, diagnosi, misure, confronto |
| `valutazione/foto.py` | `ecoscan-valuta-foto`: end-to-end, costo della visione, tempi |
| `osservabilita/valutazione_registrata.py` | ogni esecuzione come run di MLflow, non bloccante |
| `data/valutazione/casi/` | i tre insiemi di casi, versionati |
| `data/valutazione/foto/foto.jsonl` | le etichette delle foto (le immagini no) |

E i test che li sorvegliano: `test_valutazione.py` (metriche e diagnosi, più l'integrità
del dataset sul disco), `test_campiona.py` (riproducibilità e strati), 
`test_valutazione_foto.py` (scomposizione e percentili), `test_valutazione_registrata.py`
(MLflow spento non ferma la misura).
