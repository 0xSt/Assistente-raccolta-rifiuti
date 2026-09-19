"""Ogni esecuzione della valutazione diventa una run di MLflow.

**Perché, visto che c'è già `--salva` e `--confronta`.** Quei due bastano mentre si lavora:
due file, un confronto, si vede cosa ha fatto la modifica. Non bastano per guardare la
**serie storica**: dieci esecuzioni fra la v0.40 e la v0.45 sono dieci file JSON da aprire
uno per uno, e la domanda "il recupero è salito o è tornato indietro tre versioni fa?" non
ha una risposta che si possa mostrare a qualcuno. MLflow quella tabella la fa da sé, con i
parametri di ciascuna esecuzione accanto ai numeri.

**Esperimento separato** (`ecoscan-valutazione`, contro `ecoscan-chat` delle
conversazioni). Le tracce delle conversazioni sono osservazioni di ciò che è successo a un
utente; le run di valutazione sono misure ripetibili su un dataset fermo. Mescolarle
renderebbe illeggibili entrambe le liste.

**Non bloccante**, come tutto il tracciamento del progetto (D116): se MLflow è spento la
valutazione stampa i suoi numeri e finisce senza lamentarsi più di una riga. Una misura che
non si può prendere perché manca un servizio di osservabilità sarebbe un impianto al
contrario.

Cosa finisce nella run:

- **parametri**: la configurazione dell'agente (modello, `k`, versioni dei prompt con
  impronta), la modalità e la composizione del dataset. Sono le condizioni in cui la misura
  vale, e sono le stesse che `--confronta` usa per avvisare che due esecuzioni non sono
  confrontabili;
- **metriche**: tutte quelle prodotte da `misure()`, saltando quelle che valgono `None`
  perché non sono state misurate;
- **allegato**: l'esito completo in JSON, così da una run si risale al singolo caso.
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from ecoscan import configurazione as conf

registro = logging.getLogger(__name__)

ESPERIMENTO = "ecoscan-valutazione"


def nome_valido(chiave: str) -> str:
    """MLflow ammette nei nomi delle metriche solo alfanumerici, `_ - . : / ` e spazi.

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


def registra(esecuzione: dict, misure: dict, esito_completo: dict | None = None,
             indirizzo: str | None = None, esperimento: str = ESPERIMENTO) -> bool:
    """Scrive l'esecuzione su MLflow. Restituisce False se non è stato possibile.

    Gli errori si inghiottono di proposito: l'unica conseguenza accettabile di un MLflow
    spento è che la misura non venga archiviata, mai che non venga presa. **Ma non in
    silenzio**: una registrazione che non avviene e non lo dice è peggio di un errore,
    perché si continua a cercare la run in una lista dove non c'è mai arrivata.

    Per la stessa ragione, a registrazione riuscita si stampa il **link diretto** alla run:
    l'esperimento è separato da quello delle conversazioni, e senza il link la prima
    domanda è sempre "ma dove è finita?".

    I tre passaggi — parametri, metriche, allegato — sono protetti **uno per uno**: se
    l'allegato non si carica, le metriche restano comunque scritte, e l'esito dice cosa è
    passato e cosa no.
    """
    indirizzo = indirizzo or conf.MLFLOW
    if not conf.MLFLOW_ATTIVO:
        print("\nMLflow è spento (ECOSCAN_MLFLOW_ATTIVO=no): esecuzione non registrata.")
        return False
    try:
        from ecoscan.osservabilita.tracciamento import limita_attese

        limita_attese()
        import mlflow

        mlflow.set_tracking_uri(indirizzo)
        info = mlflow.set_experiment(esperimento)
    except Exception as errore:                      # server spento, permessi, versione
        registro.info("MLflow non raggiungibile (%s): %s", indirizzo, errore)
        print(f"\nMLflow non raggiungibile su {indirizzo}: esecuzione non registrata.")
        print(f"  motivo: {errore}")
        print("  il server si avvia con: docker compose up -d mlflow")
        return False

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
    print(f"  {indirizzo}/#/experiments/{info.experiment_id}/runs/{identificativo}")
    for nome, errore in falliti:
        print(f"  ATTENZIONE: {nome} non registrati — {errore}")
    return not falliti


def _allega(mlflow, esito_completo: dict | None) -> None:
    if esito_completo is None:
        return
    with tempfile.TemporaryDirectory() as cartella:
        percorso = Path(cartella) / "esito.json"
        percorso.write_text(json.dumps(esito_completo, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        mlflow.log_artifact(str(percorso))
