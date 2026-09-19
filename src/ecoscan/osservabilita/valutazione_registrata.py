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
    spento è che la misura non venga archiviata, mai che non venga presa.
    """
    if not conf.MLFLOW_ATTIVO:
        return False
    try:
        from ecoscan.osservabilita.tracciamento import limita_attese

        limita_attese()
        import mlflow

        mlflow.set_tracking_uri(indirizzo or conf.MLFLOW)
        mlflow.set_experiment(esperimento)
        with mlflow.start_run(run_name=f"valutazione {esecuzione.get('data', '')}"):
            mlflow.log_params(_appiattisci(esecuzione))
            mlflow.log_metrics({nome_valido(chiave): float(valore)
                                for chiave, valore in misure.items()
                                if isinstance(valore, (int, float))})
            if esito_completo is not None:
                with tempfile.TemporaryDirectory() as cartella:
                    percorso = Path(cartella) / "esito.json"
                    percorso.write_text(
                        json.dumps(esito_completo, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                    mlflow.log_artifact(str(percorso))
    except Exception as errore:                      # server spento, permessi, versione
        registro.info("valutazione non registrata su MLflow (%s): %s",
                      indirizzo or conf.MLFLOW, errore)
        print(f"\n(esecuzione non registrata su MLflow: {errore})")
        return False
    print(f"\nEsecuzione registrata su MLflow, esperimento «{esperimento}»")
    return True
