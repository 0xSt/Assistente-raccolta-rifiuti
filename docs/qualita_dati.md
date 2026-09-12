# Problemi di qualità trovati nelle fonti

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

## Napoli (sito ASIA)

| Problema | Esempio | Trattamento |
|---|---|---|
| Testo segnaposto pubblicato come avvertenza | "Bacinella in plastica" | Codice `placeholder`, avvertenza scartata |
| Istruzioni presenti solo nello slug | `ago-per-prelievi-proteggere-lago-con-il-cappuccio`, `ammoniaca-contenitore-vuoto` | Codice `info_nello_slug`, revisione manuale |
| Duplicati | "Busto ortopedico" due volte (`-2`); "Assorbente" / "Assorbenti" | Codici `slug_duplicato`, possibile duplicato |
| Stessa destinazione con due nomi | "Carta e Cartoncino" (indice) / "Carta e Cartone" (frazioni) | Tabella `destinazione_alias` |
| Refusi | "CCaffettiere" | Codice `refuso` |
| Spaziatura e maiuscole incoerenti | "Bambù (in Grandi Quantità )", "calcinacci" | Normalizzazione |
| Dettaglio separato dal testo | "Bombolette spray non pericolose" + "(non etichettate T e F)" dopo un `<br>` | Campo `dettaglio` della regola |
| Lista non affidabile | "Puoi inoltre conferire in questo contenitore" quasi identica su voci diverse | Usata solo per le avvertenze |
