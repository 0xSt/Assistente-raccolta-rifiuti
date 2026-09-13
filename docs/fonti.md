# Fonti dei dati

Da dove vengono i dati. Decisioni e cronologia: [diario](diario.md). Termini: [glossario](glossario.md).

Regola: ogni dato nel database deve risalire a una riga di questa pagina (tabelle `fonte`, `snapshot`, `record_grezzo`).

## Fonti usate per i dati

### Torino: AMIAT, "Il Rifiutologo | Torino", edizione 2025

- **URL:** https://amiat.it/content/dam/amiat/guide/Rifiutologo%20AMIAT%202025%20x%20sito.pdf
- **File locale:** `data/sorgenti/Rifiutologo_AMIAT_2025_x_sito.pdf` (32 pagine, creato il 13/10/2025)
- **SHA-256:** `f04e3e45cf46887f8f51f073561410c61e5d4a725d9b3a9b72fafaef8fa3fe31`
- **Consultato:** 11/09/2026

| Pagine | Contenuto | Uso |
|---|---|---|
| 6 | Legenda "Come leggere il Rifiutologo" (icone e colori) | Mappatura manuale colori/icone → destinazioni |
| 8-12 | Schede per frazione: oggetti ammessi e riquadro con gli esclusi | **Estratte:** 10 schede → `data/grezzo/torino/torino_regole.json` |
| 13 | Centri di raccolta (indirizzi e orari) | Fuori perimetro v1 |
| 16-22 | "Dove lo butto? Dalla A alla Z" | **Estratto:** 324 voci → `data/grezzo/torino/torino_voci_raw.csv` |
| 23 | "8 punti fermi" (punto 7: nel dubbio, rifiuto non recuperabile) | Regola per il livello di evidenza 3 |

### Napoli: ASIA Napoli, sito web

Estrazione completa eseguita il 12/09/2026: **584 voci** dalla sitemap e **6 pagine frazione**. I dati Napoli in `src/ecoscan/db/demo.py` restano un campione trascritto, in attesa del caricamento del grezzo completo.

Ricognizione del 12/09/2026 (`python etl/extract_napoli.py --recon`, eseguita da Stef):
- la **sitemap XML è disponibile** e contiene **584 URL di voce**: è la strategia di scoperta usata;
- l'indice mostra **40 voci per pagina** (A-B), con la sola colonna "Contenitore";
- il vocabolario delle destinazioni si ricava dall'indice e dalle voci lette correttamente.

| URL | Contenuto | Uso |
|---|---|---|
| https://www.asianapoli.it/dove-lo-butto/ | Indice del dizionario (Rifiuto / Contenitore), paginato | Struttura dell'estrattore; campione di 7 voci (A-B) |
| https://www.asianapoli.it/dove-lo-butto/specchio/ | Pagina voce: destinazioni, descrizioni, lista con avvertenze | Struttura dell'estrattore |
| https://www.asianapoli.it/dove-lo-butto/armadio/ | Pagina voce con 4 destinazioni alternative | Struttura dell'estrattore |
| https://www.asianapoli.it/dove-lo-butto/abito-usato/ | Pagina voce | Verifica della lista "Puoi inoltre conferire" |
| https://www.asianapoli.it/dove-lo-butto/telefono/ | Pagina voce | Verifica della lista "Puoi inoltre conferire" |
| https://www.asianapoli.it/servizi/materiali-da-differenziare/ | Elenco delle 6 frazioni | Pagine frazione da estrarre |
| https://www.asianapoli.it/servizi/materiali-da-differenziare/plastica-e-metalli/ | Colore del contenitore e lista "cosa differenziare" | Campione di 4 regole + 1 nota nella demo |
| https://www.asianapoli.it/comunicazione/educazione-ambientale/domande-frequenti/ | FAQ (oggetti in metallo piccoli/grandi, plastica non imballaggio) | Condizioni da trasformare in note |
| https://www.asianapoli.it/wp-content/uploads/2025/10/Asia_Opuscolo_A5_new-1.pdf | Guida completa in PDF | **Non ancora consultata** |

## Dati trascritti a mano

`data/sorgenti/manuale/napoli_esclusioni.csv` — esclusioni leggibili solo dentro le immagini informative delle pagine frazione di ASIA. Lette a occhio e trascritte alla lettera il 12/09/2026. Ogni riga porta l'URL della pagina di provenienza. Nel database avranno `origine: trascrizione_manuale`.

| Frazione | Esito della lettura |
|---|---|
| Umido/Organico | 6 esclusioni + 1 avviso generale ("NON METTERE NESSUN OGGETTO IN PLASTICA") |
| Plastica e Metalli | nessuna sezione di esclusioni nell'immagine |
| Carta e Cartone | nessuna sezione di esclusioni nell'immagine |

## Fonti consultate solo per scegliere il secondo comune (nessun dato usato)

| Città | URL | Esito |
|---|---|---|
| Milano | https://www.amsa.it/it/milano/servizi/dove-lo-butto | Motore di ricerca interattivo, nessuna pagina per voce |
| Firenze | https://cd.aliaserviziambientali.it/it-it/cittadini/cittadini/servizi/servizi-ai-cittadini/dove-lo-butto | Accesso automatico bloccato da robots.txt |
| Roma | https://www.amaroma.it/public/files/raccolta-differenziata/2019/guida-famiglie-2018_web.pdf | Guida del 2018 |
| Roma | https://www.amaroma.it/mobile/pages/1462-ma-questo-dove-lo-butto.html?news=1 | Solo materiali particolari |
| Torino (area metropolitana) | https://www.beataladifferenziata.it/it/il-destino-dei-rifiuti/riciclo-e-recupero/riciclo/dizionario-dei-rifiuti | Dizionario provinciale, non usato |

Per il confronto sono state viste anche guide PDF AMSA di comuni dell'hinterland milanese e il "Dove lo butto?" di Livorno, come esempi di formato; i link esatti non sono stati conservati.
