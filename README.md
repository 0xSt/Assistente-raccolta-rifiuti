# EcoScan Local

Assistente per la raccolta differenziata che gira interamente in locale. L'utente fotografa **un oggetto**, indica il **comune** e, se vuole, aggiunge un testo; l'app risponde dove conferirlo, con la fonte ufficiale.

Progetto universitario. Comuni del prototipo: **Napoli** (ASIA) e **Torino** (AMIAT).

## Stato attuale (v0.1.1)

| Componente | Stato |
|---|---|
| Estrattore Torino (PDF) | Funzionante: 324 voci, verificato sul PDF reale |
| Estrattore Napoli (HTML) | Ricognizione superata (584 voci dalla sitemap); **estrazione completa da eseguire** |
| Schema dati normalizzato (SQLite) | Definito e verificato con Torino completo + campione Napoli |
| Transform (condizioni, alias) | Da fare |
| Retrieval ibrido, backend, frontend, modello | Da fare |

## Struttura

```
etl/            estrattori (livello grezzo) e funzioni di pulizia
db/             schema.sql e script dimostrativo dello schema
tests/          test di regressione e unitari
data/grezzo/    output degli estrattori (versionati)
data/sorgenti/  documenti ufficiali scaricati (NON versionati, vedi docs/fonti.md)
data/cache/     cache HTML dell'estrattore Napoli (NON versionata)
docs/           fonti, decisioni, qualità dei dati
```

## Come eseguire

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Torino: scarica il PDF (link in docs/fonti.md) in data/sorgenti/, poi
python etl/extract_torino.py

# Napoli: prima la ricognizione, poi l'estrazione completa
python etl/extract_napoli.py --recon
python etl/extract_napoli.py

python -m pytest          # i test Torino si saltano se il PDF non è presente
python db/demo_schema.py  # carica i dati nello schema ed esegue interrogazioni di esempio
```

## Documentazione

- [docs/fonti.md](docs/fonti.md): link e documenti da cui provengono i dati
- [docs/decisioni.md](docs/decisioni.md): decisioni di progetto e motivazioni
- [docs/qualita_dati.md](docs/qualita_dati.md): problemi trovati nelle fonti
- [CHANGELOG.md](CHANGELOG.md): cronologia delle modifiche
