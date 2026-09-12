# Changelog

## [0.4.0] - 2026-09-12

### Aggiunto
- Transform di Torino: `transform_torino.py` con il profilo delle 324 voci del Rifiutologo. 0 conflitti, 16 voci da revisionare.
- `ecoscan-transform --comune {napoli,torino,tutti}`: il comando copre entrambe le fonti e legge sia JSONL sia CSV.
- 19 test nuovi sui casi reali di Torino.

### Modificato
- Il Transform è stato diviso in motore comune (`transform_comune.py`) e profili per comune. Le regole che cambiano tra fonti (condizioni, locuzioni, sigle, voci da scartare) stanno nel `Profilo`.
- Le voci normalizzate portano il campo `comune`.
- Le parentesi che elencano materiali o provenienza sono classificate come condizioni.

## [0.3.1] - 2026-09-12

### Corretto
Cinque difetti emersi eseguendo il Transform sulle 574 voci reali; producevano conflitti falsi, ora azzerati.
- Separazione su " o ": indica materiali alternativi dello stesso oggetto, non due oggetti.
- Separazione quando la qualificazione sta solo a destra ("Pentola e padella in acciaio").
- Locuzione fissa "usa e getta" separata per errore.
- "(grosse Quantità)" senza "in" non era riconosciuta come condizione.
- "(contenitori vuoti in Vetro)" classificata come sinonimo invece che come condizione.
- Il codice materiale non entrava nella chiave di deduplicazione.
- Refuso della fonte "biodegratabile" non riconosciuto.

### Aggiunto
- 12 test di regressione sui falsi composti reali.

## [0.3.0] - 2026-09-12

### Aggiunto
- Transform di Napoli (`ecoscan/etl/transform_napoli.py`) e comando `ecoscan-transform`: normalizzazione dei nomi, classificazione delle parentesi (condizione, sinonimo, esempi, codice materiale), estrazione delle condizioni anche fuori dalle parentesi, separazione prudente delle voci composte, deduplicazione con segnalazione dei conflitti.
- 37 test nuovi, tutti su casi reali delle 584 voci.

### Corretto
- La voce di prova `test-di-esempio` presente nel dizionario pubblico viene scartata.
- Il controllo `slug_duplicato` produceva falsi positivi sulle voci "Simbolo" (lo slug finisce con il codice materiale).
- Bug nella separazione delle voci composte: il controllo su "ecc" faceva match dentro "apparecchi".

### Da fare
- Le pagine frazione non producono regole con polarità `escluso`: la sezione "cosa non differenziare" non viene estratta.

## [0.2.2] - 2026-09-12

### Corretto
- Rimosso il campo `descrizioni_destinazioni` dalle voci: il parser non lo popolava mai e il dato appartiene comunque alla destinazione, non alla voce.

### Modificato
- `info_nello_slug` viene segnalato come risolto (`info_nello_slug_coperta`) quando la stessa informazione è già nel campo avvertenza, che è pulito.

### Documentato
- Numeri e problemi dell'estrazione completa di Napoli in `docs/qualita_dati.md`.

## [0.2.1] - 2026-09-12

### Aggiunto
- Comando `ecoscan-ispeziona`: riepiloga il livello grezzo di Napoli già estratto (destinazioni, combinazioni, problemi di qualità, indizi per il Transform) senza riscaricare nulla.

### Confermato dall'estrazione completa di Napoli
- 584 voci estratte, tutte con destinazione, strategia "parentesi" al 100%, nessuna discordanza con l'indice, 6 pagine frazione.
- Da verificare: solo 17 voci con avvertenza, numero più basso dell'atteso.

## [0.2.0] - 2026-09-12

### Modificato
- Gestione del progetto con **uv**: `pyproject.toml` + `uv.lock` al posto di `requirements.txt` e `pytest.ini`.
- Codice riorganizzato come package `src/ecoscan` (`etl/`, `db/`), import assoluti.
- Tre comandi: `ecoscan-torino`, `ecoscan-napoli`, `ecoscan-demo`.

### Aggiunto
- `ecoscan/percorsi.py`: radice del progetto e cartelle dati, con override `ECOSCAN_RADICE`.
- 3 test sulla risoluzione dei percorsi; messaggio esplicito se manca il PDF di Torino.

## [0.1.1] - 2026-09-12

### Corretto
- Le destinazioni nelle pagine voce risultavano sempre vuote: i nodi di testo sono frammentati, ora si legge il testo aggregato degli elementi.
- Il dettaglio delle regole di categoria non veniva raccolto quando separato da un `<br>`.

### Aggiunto
- Secondo passaggio di estrazione con ripiego sul vocabolario di destinazioni, per voci con impaginato diverso.
- Diagnostica: conteggio per strategia e discordanze tra pagina voce e indice.
- 3 test nuovi; fixture aggiornata alla frammentazione reale del markup.

### Confermato dalla ricognizione
- Sitemap disponibile con 584 URL di voce; indice a 40 voci per pagina; struttura delle pagine frazione.

## [0.1.0] - 2026-09-11

### Aggiunto
- Estrattore Torino (`etl/extract_torino.py`): 324 voci dal Rifiutologo AMIAT 2025, con controlli di qualità.
- Estrattore Napoli (`etl/extract_napoli.py`, `etl/napoli_qualita.py`): scoperta via sitemap o indice, cache con hash, controlli di qualità. Da verificare sul sito reale.
- Schema SQLite a tre livelli (`db/schema.sql`) e script dimostrativo (`db/demo_schema.py`).
- Test: 7 unitari Napoli, 10 di regressione Torino.
- Documentazione: fonti, decisioni, qualità dei dati.

### Contesto precedente al repo
- Scelta dell'idea e architettura iniziale (con un altro assistente).
- Revisione dell'architettura, scelta del modello per l'hardware, progettazione del retrieval ibrido e dei livelli di evidenza.
- Confronto tra Milano, Torino, Roma e Firenze; scelta di Torino.
