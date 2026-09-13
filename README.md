# EcoScan Local

Assistente per la raccolta differenziata che gira interamente in locale. L'utente fotografa **un oggetto**, indica il **comune** e, se vuole, aggiunge un testo; l'app risponde dove conferirlo, con la fonte ufficiale.

Progetto universitario. Comuni del prototipo: **Napoli** (ASIA) e **Torino** (AMIAT).

## Stato attuale (v0.6.1)

Il quadro completo è in [docs/diario.md](docs/diario.md).

| Componente | Stato |
|---|---|
| Estrattore Torino (PDF) | Funzionante: 324 voci, verificato sul PDF reale |
| Estrattore Napoli (HTML) | **Completato**: 584 voci estratte, tutte con destinazione |
| Schema dati normalizzato (SQLite) | Definito e verificato con Torino completo + campione Napoli |
| Transform Napoli (condizioni, alias, dedup) | Eseguito su 574 voci: 0 conflitti, 15 da revisionare |
| Transform Torino | Eseguito su 324 voci: 0 conflitti, 16 da revisionare |
| Retrieval ibrido, backend, frontend, modello | Da fare |

## Struttura

```
pyproject.toml       dipendenze, comandi e configurazione di pytest
uv.lock              versioni bloccate (da versionare)
src/ecoscan/
  percorsi.py        radice del progetto e cartelle dati
  etl/               estrattori (grezzo), motore del Transform e profili per comune
  db/                schema.sql e script dimostrativo dello schema
tests/               test di regressione e unitari
data/grezzo/         output degli estrattori (versionati)
data/sorgenti/       documenti ufficiali scaricati (NON versionati, vedi docs/fonti.md)
data/cache/          cache HTML dell'estrattore Napoli (NON versionata)
docs/                fonti, decisioni, qualità dei dati
```

## Come eseguire

Serve solo [uv](https://docs.astral.sh/uv/): scarica Python e le dipendenze da sé, non serve creare o attivare un virtualenv.

```bash
uv sync                         # prepara l'ambiente da uv.lock

uv run ecoscan-torino           # Torino, dizionario A-Z: metti prima il PDF in data/sorgenti/
uv run ecoscan-torino-regole    # Torino, regole di categoria dalle pagine 8-12
uv run ecoscan-napoli --recon   # Napoli: ricognizione, poche pagine
uv run ecoscan-napoli           # Napoli: estrazione completa (584 voci, ~15 minuti)
uv run ecoscan-ispeziona        # riepiloga il grezzo di Napoli già estratto
uv run ecoscan-transform        # normalizza entrambi i comuni -> data/normalizzato/

uv run pytest                   # i test Torino si saltano se il PDF non è presente
uv run ecoscan-demo             # carica i dati nello schema ed esegue interrogazioni di esempio
```

Ogni comando accetta `--help`. I percorsi sono relativi alla radice del progetto, quindi funzionano da qualsiasi cartella; `ECOSCAN_RADICE` permette di forzarla (utile nei container).

### Aggiungere dipendenze e file

```bash
uv add <pacchetto>              # dipendenza di esecuzione (aggiorna pyproject.toml e uv.lock)
uv add --dev <pacchetto>        # dipendenza solo di sviluppo
```

I nuovi moduli vanno in `src/ecoscan/`; per renderli eseguibili basta aggiungere una riga in `[project.scripts]` che punti a una funzione `main()`.

## Documentazione

- **[docs/diario.md](docs/diario.md)**: il file da leggere per primo. Stato del progetto, decisioni prese e perché, questioni aperte, annotazioni e cronologia delle modifiche.
- [docs/glossario.md](docs/glossario.md): significato dei termini usati nel progetto, in particolare quelli dell'ETL
- [docs/fonti.md](docs/fonti.md): link e documenti da cui provengono i dati
- [docs/qualita_dati.md](docs/qualita_dati.md): catalogo dei difetti di ciascuna fonte

Diario e glossario si tengono aggiornati man mano: il diario a ogni modifica sostanziale o decisione, il glossario quando entra in gioco un termine nuovo.
