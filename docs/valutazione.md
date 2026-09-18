# La valutazione del recupero

> Aggiornato alla **v0.41.2**.

Questo documento spiega **perché** si misura il recupero, **cosa** si misura esattamente,
**come** si usa lo strumento e **come si leggono** i numeri che produce.

---

## 1. Il problema: un errore, tre cause possibili

Quando l'assistente dà una risposta sbagliata, l'errore può essere nato in tre punti diversi:

1. **il riconoscimento** — il modello di visione ha visto un oggetto che non c'era;
2. **il recupero** — il documento giusto non è arrivato fra i candidati;
3. **la scelta** — il documento c'era, ma il modello ne ha preso un altro.

Sono tre difetti che si riparano in tre modi diversi e che non si scambiano fra loro:

| difetto | dove si interviene |
|---|---|
| riconoscimento | prompt di riconoscimento, ridimensionamento delle foto, modello |
| recupero | formulazioni indicizzate, `k`, filtri, qualità dei nomi, ricerca ibrida |
| scelta | prompt di scelta, politiche del codice (materiali, specificità) |

Senza una misura, la diagnosi si fa a mano, un caso per volta. È esattamente quello che è
successo con **la forchetta d'acciaio** (D78–D81): sono servite due sessioni di ricerche
manuali su `/cerca` per stabilire che il documento giusto *usciva* dal recupero e che quindi
il difetto stava nel prompt di scelta. Lo strumento descritto qui automatizza quella
diagnosi e la esegue su tutti i casi insieme.

---

## 2. La teoria: il recupero è un tetto, non una misura a sé

In un sistema RAG il generatore può usare solo ciò che il recupero gli passa. Se il
documento giusto non è fra i candidati, **nessun prompt, nessun modello più grande e nessuna
temperatura più bassa** possono produrre la risposta giusta se non per caso.

Formalmente: detta `R` la probabilità che il documento giusto sia fra i primi `k` candidati
(*recall@k*) e `C` la probabilità che la risposta finale sia corretta,

```
C ≤ R + (probabilità di indovinare per un'altra strada)
```

Il recall@k è quindi un **tetto** (*ceiling*) alla correttezza complessiva. Ne discendono
due conseguenze pratiche:

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

### La metrica scelta, e quelle scartate

Si misura il **recall@k binario**: il documento giusto è fra i candidati, sì o no. Le
alternative sono state scartate per ragioni legate al dominio:

- **precision@k** — non interessa. Al modello si passano `k` candidati comunque: candidati
  in più che non c'entrano costano qualche parola di prompt, non una risposta sbagliata;
- **MRR / nDCG** — assumono che la posizione conti in modo graduale. Qui il modello legge
  *tutti* i candidati insieme e ne sceglie uno: essere primo o quinto non cambia granché.
  La posizione viene comunque registrata, ma come indizio diagnostico (se il documento
  giusto sta sempre ultimo, `k` è tirato), non come metrica di ottimizzazione;
- **la similarità media** — è un numero che si può migliorare senza migliorare niente.

### Cosa conta come "recuperato"

Un candidato conta se **porta a una delle destinazioni attese**, non se ha un certo `id`.
La scelta è deliberata: in questi dizionari lo stesso oggetto compare spesso sotto nomi
diversi ("Stoviglie in metallo" e "Posate" possono essere due voci entrambe corrette), e
all'utente interessa il contenitore, non quale riga del regolamento è stata citata. Legare
l'attesa all'`id` avrebbe reso il dataset fragile a ogni rigenerazione dei dati.

---

## 3. Il dataset: da dove vengono i casi

Un **caso** è un riconoscimento già avvenuto più la risposta attesa:

```json
{"comune": "Napoli", "oggetto": "forchetta", "materiali": ["acciaio"],
 "destinazioni_attese": ["Plastica e Metalli"], "livello_atteso": 1,
 "nota": "D78: sceglieva 'Forchetta in plastica'"}
```

Due sorgenti, stesso formato, file separati:

| file | origine | versionato | a cosa serve |
|---|---|---|---|
| `data/valutazione/casi.jsonl` | scritti a mano | sì | il contratto: cosa il sistema **deve** saper fare |
| `data/valutazione/da_riscontri.jsonl` | pollice su/giù degli utenti | no | un campione di cosa succede **davvero** |

Sono separati perché hanno autorità diversa: i primi li decidiamo noi e si discutono, i
secondi crescono da sé e possono contenere l'attesa sbagliata di un utente. Quando lo stesso
caso compare in entrambi, **vince il manuale**.

### Come un riscontro diventa un caso

Questo è il punto che rende il pollice su/giù qualcosa di più di un registro (`/riscontro` →
`caso_da_riscontro`):

- **pollice su** → l'attesa sono le destinazioni appena date. Fissa un comportamento giusto
  perché non regredisca;
- **pollice giù con l'alternativa** ("andava in Plastica e Metalli") → l'attesa è quella
  dell'utente. È il caso più prezioso, perché nasce da un errore vero;
- **pollice giù senza alternativa** → nessun caso. Sapere che una risposta è sbagliata senza
  sapere quale fosse quella giusta non si può rieseguire: resta nel registro grezzo;
- **pollice giù con motivo "non ha capito che oggetto è"** → nessun caso. Il difetto sta nel
  riconoscimento, cioè proprio nel passaggio che i casi tengono fermo.

Per questo l'interfaccia, dopo un pollice giù, chiede **dove andava davvero** scegliendolo
fra i contenitori del comune: è l'unica domanda che trasforma un giudizio in una misura.

I duplicati vengono scartati: dieci pollici su sullo stesso oggetto gonfierebbero le
percentuali senza misurare niente di nuovo.

---

## 4. Come si usa

```bash
# il tetto: solo recupero, nessun modello. Secondi.
uv run ecoscan-valuta --senza-modello

# la misura completa: recupero + scelta. Minuti, serve Ollama acceso.
uv run ecoscan-valuta

# un comune per volta, o un k diverso
uv run ecoscan-valuta --comune Napoli -k 12

# salva l'esecuzione, per confrontarla dopo una modifica
uv run ecoscan-valuta --salva prima.json
# ... si modifica il prompt, le formulazioni, k ...
uv run ecoscan-valuta --confronta prima.json
```

Il flusso che conviene, quando si lavora su una modifica:

1. `--senza-modello --salva prima.json` — il tetto attuale, in pochi secondi;
2. si applica la modifica (formulazioni, filtri, `k`, nomi);
3. `--senza-modello --confronta prima.json` — il tetto si è alzato?
4. solo se il tetto tiene, si esegue la misura completa con il modello.

I casi si aggiungono a mano in `data/valutazione/casi.jsonl`, una riga per caso. **Ogni volta
che si scopre un errore vero, il primo gesto è scriverlo lì**: da quel momento in poi quella
regressione non può ripassare inosservata.

---

## 5. Come si leggono i numeri

L'uscita ha due parti. Le misure:

| misura | cosa dice | cosa fare se è bassa |
|---|---|---|
| `recupero` | recall@k: il tetto | formulazioni, nomi, `k`, ricerca ibrida |
| `risposte_corrette` | quanto si arriva davvero | dipende dalla diagnosi, sotto |
| `livello_atteso` | la risposta viene dal livello giusto (solo con il modello) | cascata, soglie |
| `posizione_media` | dove sta il documento giusto | se cresce verso `k`, l'ordinamento è debole |

E la diagnosi caso per caso, che è la parte azionabile. È una tabella 2×2:

| | risposta giusta | risposta sbagliata |
|---|---|---|
| **documento recuperato** | `corretto` | **`il documento c'era, non è stato scelto`** |
| **documento non recuperato** | `corretto per un'altra strada` | `il documento non è stato recuperato` |

Le due caselle che contano sono in diagonale:

- **"c'era, non è stato scelto"** → il recupero ha fatto il suo. Si interviene sul **prompt
  di scelta** o sulle politiche del codice. È stata la diagnosi della forchetta;
- **"non è stato recuperato"** → il modello non poteva sceglierlo. Si interviene
  sull'**indice**: formulazioni, nomi, `k`. Toccare il prompt qui è tempo perso.

La casella **"corretto per un'altra strada"** merita attenzione: la risposta è giusta ma il
documento atteso non c'era, quindi ci si è arrivati da un'altra parte — di solito una regola
di categoria che ha rimediato a un dizionario incompleto. È una correttezza fragile: va bene
oggi, ma l'attesa del caso o i dati vanno guardati.

Il confronto fra due esecuzioni (`--confronta`) elenca separatamente i **casi guadagnati** e
i **casi persi**, non solo la media. Una modifica che guadagna cinque casi e ne perde tre è
un pareggio nella percentuale e un problema nella realtà: i tre persi vanno guardati uno per
uno.

---

## 6. Limiti dichiarati

- **il dataset è piccolo** (una dozzina di casi scritti a mano, più quelli che arrivano dai
  riscontri). Le percentuali su numeri così piccoli oscillano molto: si leggono come
  indicatori di direzione, non come misure di precisione. Il meccanismo dei riscontri esiste
  proprio per farlo crescere senza doverlo scrivere tutto a mano;
- **non si misura il riconoscimento.** È deliberato (§2), ma vuol dire che gli errori del
  modello di visione restano fuori da questi numeri e vanno guardati altrove, nelle tracce
  MLflow;
- **le attese le abbiamo decise noi.** Un caso con l'attesa sbagliata rende il sistema
  peggiore mentre sembra migliorarlo: per questo i casi manuali si discutono e i casi da
  riscontro restano in un file separato. **È già successo**: il caso `frullatore` chiedeva
  le destinazioni di "Elettrodomestici", ma ASIA ha una voce `Frullatore` che manda ai
  piccoli RAEE — il sistema dava la risposta migliore e la valutazione la contava come
  errore. Da lì la riga "i documenti trovati portano a…" nell'uscita: prima di dare la
  colpa al recupero si guarda dove portavano i candidati, e un'attesa sbagliata si vede
  subito;
- **non si misura la qualità della spiegazione**, solo la destinazione. Una risposta giusta
  con una motivazione confusa conta come corretta.

---

## 7. Dove sta nel codice

| file | cosa fa |
|---|---|
| `valutazione/casi.py` | cos'è un caso, dove vive, come un riscontro diventa un caso |
| `valutazione/esegui.py` | esecuzione, diagnosi, misure, confronto; comando `ecoscan-valuta` |
| `api/app.py` (`/riscontro`) | registra il giudizio e, se misurabile, lo aggiunge al dataset |
| `frontend/app.py` (`riscontro`) | il pollice giù che chiede dove andava davvero |
| `data/valutazione/casi.jsonl` | i casi scritti a mano, versionati |
