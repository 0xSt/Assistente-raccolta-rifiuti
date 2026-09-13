# EcoScan Local

Assistente per la raccolta differenziata che gira interamente in locale. L'utente fotografa **un oggetto**, indica il **comune** e, se vuole, aggiunge un testo; l'app risponde dove conferirlo, con la fonte ufficiale.

Progetto universitario. Comuni del prototipo: **Napoli** (ASIA) e **Torino** (AMIAT).

## Stato attuale (v0.10.1)

Il quadro completo è in [docs/diario.md](docs/diario.md).

| Componente | Stato |
|---|---|
| Extract Torino (PDF) | 324 voci dall'elenco A-Z + 10 schede di regole |
| Extract Napoli (HTML) | 584 voci dal dizionario + 6 pagine frazione |
| Transform Napoli | 578 voci normalizzate: 0 conflitti, 0 da revisionare |
| Transform Torino | 324 voci normalizzate: 0 conflitti, 0 da revisionare |
| Regole di categoria | 110 normalizzate e collegate alle destinazioni |
| Revisione manuale | 32 decisioni prese (3,5% delle voci), nessuna aperta |
| Load relazionale | Fatto: comuni, destinazioni, voci, condizioni, alias, regole, decisioni |
| Serving (FTS5, embedding, ricerca ibrida) | Da fare |
| Backend, frontend, modello | Da fare |

## Struttura

```
pyproject.toml       dipendenze, comandi e configurazione di pytest
uv.lock              versioni bloccate (da versionare)
src/ecoscan/
  percorsi.py        radice del progetto e cartelle dati
  etl/               estrattori (grezzo), motore del Transform e profili per comune
  db/                schema.sql e script dimostrativo dello schema
tests/               test di regressione e unitari
data/revisioni/      decisioni manuali sulle voci incerte (versionate)
data/riferimento/    destinazioni: canale, colore, flussi di materiale (versionati)
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
uv run ecoscan-napoli           # Napoli: estrazione completa (584 voci)
uv run ecoscan-ispeziona        # riepiloga il grezzo di Napoli già estratto
uv run ecoscan-transform        # normalizza le voci dei due comuni -> data/normalizzato/
uv run ecoscan-regole           # normalizza le regole di categoria e le collega alle destinazioni
uv run ecoscan-carica           # ricostruisce data/ecoscan.db dai file normalizzati
uv run ecoscan-carica --verifica # solo i controlli di coerenza, senza scrivere

uv run pytest                   # i test Torino si saltano se il PDF non è presente
uv run ecoscan-demo             # carica i dati nello schema ed esegue interrogazioni di esempio
```

La prima estrazione di Napoli scarica 584 pagine con una pausa di 1,5 secondi fra una e
l'altra, quindi dura circa **15 minuti**; stampa l'avanzamento ogni 25 voci. Le esecuzioni
successive leggono da `data/cache/` e durano pochi secondi. Due conseguenze pratiche:
la cache non va cancellata senza motivo, e conviene **versionare il grezzo prodotto**
(`data/grezzo/napoli/`), così chi parte da un clone pulito non riscarica nulla.

Ogni comando accetta `--help`. I percorsi sono relativi alla radice del progetto, quindi funzionano da qualsiasi cartella; `ECOSCAN_RADICE` permette di forzarla (utile nei container).

### Aggiungere dipendenze e file

```bash
uv add <pacchetto>              # dipendenza di esecuzione (aggiorna pyproject.toml e uv.lock)
uv add --dev <pacchetto>        # dipendenza solo di sviluppo
```

I nuovi moduli vanno in `src/ecoscan/`; per renderli eseguibili basta aggiungere una riga in `[project.scripts]` che punti a una funzione `main()`.

## Mappa dei moduli

| Modulo | Cosa fa |
|---|---|
| `etl/extract_torino.py` | Legge l'elenco A-Z del Rifiutologo: destinazioni dai marcatori vettoriali |
| `etl/extract_torino_regole.py` | Legge le schede per frazione (pagine 8-12): ammessi ed esclusi |
| `etl/extract_napoli.py` | Scarica e legge il dizionario ASIA e le pagine frazione |
| `etl/napoli_qualita.py` | Pulizia dei testi e rilevamento dei difetti delle voci di Napoli |
| `etl/trascrizioni.py` | Dati leggibili solo a occhio (testo dentro immagini) e assenze verificate |
| `etl/ispeziona_napoli.py` | Riepilogo del grezzo di Napoli, senza riscaricare nulla |
| `etl/transform_comune.py` | Motore del Transform: condizioni, alias, deduplicazione |
| `etl/transform_napoli.py`, `etl/transform_torino.py` | Regole specifiche di ciascun comune (`Profilo`) |
| `etl/revisioni.py` | Decisioni manuali, applicate a ogni riesecuzione |
| `etl/esegui_transform.py` | Comando che mette insieme Transform, profili e revisioni |
| `etl/normalizza_regole.py` | Collega le regole di categoria alle destinazioni dei comuni |
| `percorsi.py` | Radice del progetto e cartelle dati |
| `db/schema.sql` | Schema del livello relazionale |
| `db/carica.py` | Load: ricostruisce il database dai file normalizzati |

## Documentazione

- **[docs/diario.md](docs/diario.md)**: il file da leggere per primo. Stato del progetto, decisioni prese e perché, questioni aperte, annotazioni e cronologia delle modifiche.
- [docs/glossario.md](docs/glossario.md): significato dei termini usati nel progetto, in particolare quelli dell'ETL
- [docs/fonti.md](docs/fonti.md): link e documenti da cui provengono i dati
- [docs/qualita_dati.md](docs/qualita_dati.md): catalogo dei difetti di ciascuna fonte

Diario e glossario si tengono aggiornati man mano: il diario a ogni modifica sostanziale o decisione, il glossario quando entra in gioco un termine nuovo.

Non è affidato alla memoria: `tests/test_documentazione.py` fallisce se la versione corrente non ha una voce nella cronologia del diario, se un comando o un modulo non è documentato, se la numerazione delle decisioni ha buchi o doppioni, o se manca un termine essenziale dal glossario.
