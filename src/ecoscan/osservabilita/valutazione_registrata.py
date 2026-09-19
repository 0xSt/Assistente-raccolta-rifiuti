"""Ogni esecuzione della valutazione diventa una run di MLflow. **Sempre.**

**Perché, visto che c'è già `--salva` e `--confronta`.** Quei due bastano mentre si lavora:
due file, un confronto, si vede cosa ha fatto la modifica. Non bastano per guardare la
**serie storica**: dieci esecuzioni fra la v0.40 e la v0.45 sono dieci file JSON da aprire
uno per uno, e la domanda "il recupero è salito o è tornato indietro tre versioni fa?" non
ha una risposta che si possa mostrare a qualcuno. MLflow quella tabella la fa da sé, con i
parametri di ciascuna esecuzione accanto ai numeri.

**Una misura non è osservabilità.** Il resto del tracciamento del progetto è non bloccante
per scelta (D116): se MLflow è spento, l'utente riceve comunque la sua risposta e la traccia
si perde senza danno. Una **misura** no: si prende una volta, spesso dopo minuti di CPU, e
se non viene registrata è persa. Da qui tre regole che valgono solo qui:

1. `ECOSCAN_MLFLOW_ATTIVO` **non si guarda**: governa le tracce delle conversazioni, non le
   misure. L'unico modo di non registrare è chiederlo, con `--senza-mlflow`;
2. se il server non risponde, la run si scrive comunque in un **archivio locale**
   (`data/valutazione/mlflow-locale.db`), che è un archivio MLflow vero e si apre con
   `mlflow ui`. È SQLite e non una cartella di file perché dalla 3.x MLflow rifiuta il
   vecchio *file store*, e un ripiego che non funziona è peggio di nessun ripiego;
3. se fallisce anche quello, il comando **si ferma con errore**, invece di lasciar credere
   che la misura sia al sicuro da qualche parte.

**Esperimento separato** (`ecoscan-valutazione`, contro `ecoscan-chat` delle
conversazioni). Le tracce delle conversazioni sono osservazioni di ciò che è successo a un
utente; le run di valutazione sono misure ripetibili su un dataset fermo. Mescolarle
renderebbe illeggibili entrambe le liste — ed è anche il motivo per cui l'uscita stampa il
**link diretto** alla run: cercarla nella lista sbagliata è l'errore più facile da fare.

Cosa finisce nella run:

- **parametri**: la configurazione dell'agente (modello, `k`, versioni dei prompt con
  impronta), la modalità e la composizione del dataset. Sono le condizioni in cui la misura
  vale, e sono le stesse che `--confronta` usa per avvisare che due esecuzioni non sono
  confrontabili;
- **metriche**: tutte quelle prodotte da `misure()`, saltando quelle che valgono `None`
  perché non sono state misurate;
- **allegato**: l'esito completo in JSON, così da una run si risale al singolo caso.

I tre passaggi sono protetti **uno per uno**: se l'allegato non passa, le metriche restano
comunque scritte e l'uscita dice cosa è andato e cosa no.
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from ecoscan import configurazione as conf
from ecoscan.percorsi import DATI

registro = logging.getLogger(__name__)

ESPERIMENTO = "ecoscan-valutazione"
# L'archivio di ripiego, dentro i dati del progetto e non versionato: SQLite per i
# metadati (il file store è in "maintenance mode" dalla 3.x e viene rifiutato) e una
# cartella accanto per gli allegati. È un archivio MLflow vero: `mlflow ui` lo apre.
RIPIEGO = DATI / "valutazione" / "mlflow-locale.db"
RIPIEGO_ALLEGATI = DATI / "valutazione" / "mlflow-locale-artefatti"


def nome_valido(chiave: str) -> str:
    """MLflow ammette nei nomi solo alfanumerici, `_ - . : / ` e spazi.

    `recall@8` faceva fallire l'intera chiamata a `log_metrics` — e con lei tutte le altre
    metriche, perché la scrittura è una sola. La conversione avviene **solo qui**, al
    confine con MLflow: dentro il progetto la metrica continua a chiamarsi `recall@8`, che
    è il nome con cui la si legge in letteratura e nei nostri documenti.
    """
    return chiave.replace("@", "_at_")


def _appiattisci(esecuzione: dict) -> dict[str, str]:
    """I parametri di una run sono coppie di stringhe: la configurazione annidata si
    appiattisce, i conteggi dei casi diventano `casi_campione`, `casi_regressioni`…"""
    parametri = {nome_valido(chiave): str(valore) for chiave, valore in esecuzione.items()
                 if chiave not in ("configurazione", "casi")}
    parametri.update({nome_valido(chiave): str(valore)
                      for chiave, valore in esecuzione.get("configurazione", {}).items()})
    parametri.update({nome_valido(f"casi_{insieme}"): str(quanti)
                      for insieme, quanti in esecuzione.get("casi", {}).items()})
    return parametri


def _apri(indirizzo: str, esperimento: str, allegati: Path | None = None):
    """Collega il client all'archivio e sceglie l'esperimento. Solleva se non ci riesce.

    `allegati` serve solo all'archivio locale: senza, MLflow metterebbe gli artefatti in
    `./mlruns` relativo alla cartella da cui è stato lanciato il comando, che cambia da
    un'esecuzione all'altra.
    """
    from ecoscan.osservabilita.tracciamento import limita_attese

    limita_attese()
    import mlflow

    mlflow.set_tracking_uri(indirizzo)
    if allegati is not None and mlflow.get_experiment_by_name(esperimento) is None:
        allegati.mkdir(parents=True, exist_ok=True)
        mlflow.create_experiment(esperimento, artifact_location=allegati.resolve().as_uri())
    return mlflow.set_experiment(esperimento), mlflow


def _allega(mlflow, esito_completo: dict | None) -> None:
    if esito_completo is None:
        return
    with tempfile.TemporaryDirectory() as cartella:
        percorso = Path(cartella) / "esito.json"
        percorso.write_text(json.dumps(esito_completo, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        mlflow.log_artifact(str(percorso))


def registra(esecuzione: dict, misure: dict, esito_completo: dict | None = None,
             indirizzo: str | None = None, esperimento: str = ESPERIMENTO,
             ripiego: Path | None = None) -> bool:
    """Scrive l'esecuzione su MLflow, sul server o — se non risponde — in locale.

    Restituisce True se è andato tutto; False se la run è stata creata ma qualche pezzo
    non è passato. Se non è stato possibile scrivere **da nessuna parte**, solleva
    `SystemExit`: a quel punto tacere sarebbe la cosa peggiore, perché la misura è persa e
    chi l'ha lanciata non lo saprebbe.
    """
    indirizzo = indirizzo or conf.MLFLOW
    ripiego = ripiego or RIPIEGO
    try:
        info, mlflow = _apri(indirizzo, esperimento)
    except Exception as errore:                      # server spento, permessi, versione
        registro.info("MLflow non raggiungibile (%s): %s", indirizzo, errore)
        print(f"\nMLflow non raggiungibile su {indirizzo}: {errore}")
        print("  (il server si avvia con: docker compose up -d mlflow)")
        locale = f"sqlite:///{ripiego.resolve()}"
        try:
            # la cartella si crea DENTRO il try: un disco pieno o un permesso negato qui
            # devono produrre lo stesso errore chiaro degli altri, non una traccia grezza
            ripiego.parent.mkdir(parents=True, exist_ok=True)
            info, mlflow = _apri(locale, esperimento, RIPIEGO_ALLEGATI)
        except Exception as secondo:                 # disco pieno, permessi
            raise SystemExit(
                f"  e nemmeno l'archivio locale ha funzionato: {secondo}\n"
                "La misura NON è stata registrata da nessuna parte: controlla il server "
                f"o i permessi su {ripiego}, e rilancia.") from secondo
        indirizzo = locale
        print(f"  registrata invece nell'archivio locale: {ripiego}")
        print(f"  per guardarla: uv run mlflow ui --backend-store-uri {locale}")

    scritti, falliti = [], []
    with mlflow.start_run(run_name=f"valutazione {esecuzione.get('data', '')}") as run:
        for nome, scrivi in (
                ("parametri", lambda: mlflow.log_params(_appiattisci(esecuzione))),
                ("metriche", lambda: mlflow.log_metrics(
                    {nome_valido(c): float(v) for c, v in misure.items()
                     if isinstance(v, (int, float))})),
                ("esito completo", lambda: _allega(mlflow, esito_completo))):
            try:
                scrivi()
                scritti.append(nome)
            except Exception as errore:
                registro.info("MLflow, %s non registrati: %s", nome, errore)
                falliti.append((nome, errore))
        identificativo = run.info.run_id

    print(f"\nEsecuzione registrata su MLflow ({', '.join(scritti)}), "
          f"esperimento «{esperimento}»")
    # il link si stampa solo se è un link: per l'archivio locale un URL http inventato
    # manderebbe su una pagina che non esiste
    if indirizzo.startswith(("http://", "https://")):
        print(f"  {indirizzo}/#/experiments/{info.experiment_id}/runs/{identificativo}")
    else:
        print(f"  run {identificativo}, esperimento {info.experiment_id}")
    for nome, errore in falliti:
        print(f"  ATTENZIONE: {nome} non registrati — {errore}")
    return not falliti


def prova(indirizzo: str | None = None) -> bool:
    """Scrive una run minuscola per capire, in un secondo, se MLflow accetta le scritture.

    Serve a rispondere alla domanda "è il server o è il mio codice?" senza dover rieseguire
    una valutazione intera: `uv run ecoscan-valuta --prova-mlflow`.
    """
    indirizzo = indirizzo or conf.MLFLOW
    print(f"Provo a scrivere su MLflow: {indirizzo}")
    esito = registra({"data": "prova", "k": 0, "modalita": "prova", "casi": {},
                      "configurazione": {"prova": "si"}},
                     {"recall@8": 0.0, "prova": 1.0}, None, indirizzo,
                     esperimento=f"{ESPERIMENTO}-prova")
    print("La scrittura funziona." if esito else "La scrittura è passata solo in parte.")
    return esito
