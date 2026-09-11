# Changelog

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
