# Problemi di qualità trovati nelle fonti

Catalogo di riferimento per fonte. Le decisioni su come trattarli e la cronologia stanno nel [diario](diario.md).

Ogni problema diventa una riga della tabella `problema_qualita` durante il caricamento.

## Torino (Rifiutologo 2025)

| Problema | Esempio | Trattamento |
|---|---|---|
| Destinazione codificata solo da colore/icona | Tutte le voci A-Z | Lettura dei marcatori vettoriali |
| Sei destinazioni con lo stesso gradiente | Centro di raccolta, ingombranti, abiti, farmaci, olio, pile | Impronta del glifo interno |
| Condizioni nel nome della voce | "Cartone da pizza sporco (solo se certificato compostabile)", "Truciolato (piccole quantità)" | Campo `condizione` |
| Voci composte | "Accendini, Accendisigari e Accendigas" | Tabella `voce_alias` |
| Refusi e incoerenze | "prevenienti", "Blue-ray", "Filtri del the", "Capsule di caffè" / "Capsule del caffè" | Testo originale conservato, forma pulita separata |
| Rimandi a note | "Oli vegetali esausti*" | Asterisco rimosso, nota in `avvertenza` |

### Esito del Transform di Torino (324 voci)

- **0 conflitti**. L'unico conflitto iniziale ("Involucro cioccolatini") era dovuto alle parentesi con il materiale, classificate erroneamente come sinonimi.
- 16 voci segnalate, tutte decise a mano: 13 separazioni confermate, 3 annullate, 1 nota a piè di pagina agganciata come avvertenza. Nessuna resta aperta.
- Le condizioni di Torino stanno quasi sempre tra parentesi, al contrario di Napoli.

### Regole di categoria di Torino (pagine 8-12)

| Problema | Esempio | Trattamento |
|---|---|---|
| Due schede affiancate per pagina | p8: "Rifiuto non recuperabile" e "Carta e cartone" | Divisione per colonna a x=310 |
| Esclusioni in prosa, non in elenco | "Scontrini, carta forno... NON vanno conferiti nella carta!" | Separazione del soggetto prima di "NON" |
| Riquadri con etichette diverse | "I RIFIUTATI", "METTITI NEI NOSTRI PANNI", "È ORA DI ESPORSI" | Riconoscimento dal font, non dall'etichetta |
| Frasi imperative senza elenco | "Non gettare l'olio negli scarichi" | Classificate come nota, non come esclusioni |
| Schede senza griglia di oggetti | Farmaci, Oli esausti, Rifiuti ingombranti | Nessun ammesso; il testo va in `descrizione` |

## Napoli (sito ASIA)

| Problema | Esempio | Trattamento |
|---|---|---|
| Testo segnaposto pubblicato come avvertenza | "Bacinella in plastica" | Codice `placeholder`, avvertenza scartata |
| Istruzioni presenti solo nello slug | `ago-per-prelievi-proteggere-lago-con-il-cappuccio` (15 casi) | Quasi tutte coperte dal campo avvertenza, che è pulito: codice `info_nello_slug_coperta`, risolto. Senza avvertenza resta `info_nello_slug` da revisionare |
| Parentesi con tre significati diversi | sinonimo "Cartone per bevande (tetrapak)", esempi "Barattolo in latta (scatola di pelati, tonno, ...)", condizione "Bambù (in Grandi Quantità)" | Da classificare nel Transform: alias oppure condizione |
| Maiuscole casuali | "Biro E Pena A Sfera" vs "Bucce di frutta" | Normalizzazione del nome |
| Refusi nei nomi | "Ghewing gum", "Pena a sfera", "acciao" | Nome originale conservato, forma pulita separata |
| Singolare/plurale non uniforme tra comuni | Napoli "Divano", Torino "Divani" | Normalizzazione del numero + ricerca a trigrammi |
| Destinazione con nome variante | "Cartone" (1 voce) vs "Carta e Cartoncino" (28) vs "Carta e Cartone" (frazioni) | Tabella `destinazione_alias` |
| Duplicati | "Busto ortopedico" due volte (`-2`); "Assorbente" / "Assorbenti" | Codici `slug_duplicato`, possibile duplicato |
| Stessa destinazione con due nomi | "Carta e Cartoncino" (indice) / "Carta e Cartone" (frazioni) | Tabella `destinazione_alias` |
| Refusi | "CCaffettiere" | Codice `refuso` |
| Spaziatura e maiuscole incoerenti | "Bambù (in Grandi Quantità )", "calcinacci" | Normalizzazione |
| Dettaglio separato dal testo | "Bombolette spray non pericolose" + "(non etichettate T e F)" dopo un `<br>` | Campo `dettaglio` della regola |
| Esclusioni pubblicate solo come immagine | solo il Vetro ha l'elenco testuale | Rilevate come `immagini_informative`; l'Umido è stato trascritto a mano, Plastica e Carta non ne hanno |
| Ammessi ed esclusi con markup diverso | ammessi: `<img>` + `<strong>`; esclusi: `<ul><li>` | Raccolta separata per polarità (corretto in v0.5.0) |
| Etichette grafiche "SI"/"NO" lette come note | nota "NO" nella pagina del Vetro | Filtrate |
| Lista non affidabile | "Puoi inoltre conferire in questo contenitore" quasi identica su voci diverse | Usata solo per le avvertenze |

### Correzioni al registro dopo il Transform

- I 21 `slug_duplicato` erano **falsi positivi**: quasi tutti sono voci "Simbolo" il cui slug finisce con il codice del materiale (`simbolo-fe-40`), non con il contatore di WordPress.
- Il dizionario pubblico contiene una voce di prova: `test-di-esempio`, "Test di esempio", con tre destinazioni reali. Scartata dal Transform.

### Esito del Transform (578 voci normalizzate)

- **0 conflitti**: nessuna contraddizione reale nella fonte. I 5 conflitti della prima esecuzione erano difetti del Transform, non dei dati.
- 84 voci con almeno una condizione, 28 alias, 20 codici materiale, 5 fuse nella deduplicazione.
- 16 voci segnalate, tutte decise a mano: 8 separazioni confermate, 2 annullate, 1 alias corretto, 6 asterischi verificati come residui tipografici. Nessuna resta aperta.
- Refuso della fonte gestito: "biodegratabile" per "biodegradabile".

### Numeri dell'estrazione completa (12/09/2026, 584 voci)

- 21 `slug_duplicato`, 15 `info_nello_slug` (di cui la gran parte coperta da avvertenza), 1 `placeholder`.
- 17 avvertenze in totale, 16 valide (una è il placeholder).
- 5 gruppi di possibili duplicati: Assorbente/Assorbenti, Busto ortopedico (doppio), Fondi/Fondo di caffè, Mozzicone/Mozziconi di sigaretta, Tappi/Tappo di sughero.
- 462 voci con una sola destinazione, 122 con alternative (fino a 5).
- 16 destinazioni distinte; 196 voci vanno all'Isola Ecologica Estesa e 167 al Non Riciclabile.
