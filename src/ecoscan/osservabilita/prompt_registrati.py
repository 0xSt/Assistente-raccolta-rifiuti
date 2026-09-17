"""I prompt nel registro di MLflow.

I prompt restano **file versionati in git**: quella è la verità, e il diff fra due versioni
è leggibile. Il registro di MLflow serve a un'altra cosa: collegare una versione di prompt
alle tracce che l'hanno usata, così quando un risultato peggiora si sa quale testo c'era.

Perciò qui non si genera nulla: si pubblica ciò che già esiste su disco. Il backend continua
a leggere i prompt da disco, e cerca nel registro la versione con la **stessa impronta** per
collegarla a ogni traccia.

La pubblicazione è idempotente: un prompt già registrato con la stessa impronta non crea una
nuova versione. Senza questo controllo ogni lancio aggiungerebbe una versione identica, e i
numeri del registro smetterebbero di voler dire qualcosa.

Uso:
  uv run ecoscan-prompt --pubblica      # manda al registro i prompt nuovi o modificati
  uv run ecoscan-prompt                 # elenca quelli su disco con versione e impronta
"""
from __future__ import annotations

import argparse
import logging

from ecoscan import configurazione as conf
from ecoscan import prompt as prompt_

registro = logging.getLogger(__name__)


def nome_registrato(prompt: prompt_.Prompt) -> str:
    return f"ecoscan-{prompt.nome}"


def versione_registrata(prompt: prompt_.Prompt):
    """La versione del registro con la stessa impronta del file su disco, o None.

    Solleva se MLflow non risponde: chi chiama decide se è un errore o un avviso.
    """
    from mlflow import MlflowClient

    client = MlflowClient()
    try:
        risultato = client.search_prompt_versions(nome_registrato(prompt))
    except Exception as errore:
        # un prompt mai registrato non è un guasto: semplicemente non ha versioni
        if "RESOURCE_DOES_NOT_EXIST" in str(errore) or "not found" in str(errore).lower():
            return None
        raise
    for versione in getattr(risultato, "prompt_versions", risultato) or []:
        if (versione.tags or {}).get("impronta") == prompt.impronta:
            return versione
    return None


def pubblica(prompt: prompt_.Prompt, indirizzo: str | None = None) -> tuple[str, bool] | None:
    """Registra un prompt in MLflow se il suo testo non c'è già.

    Restituisce (riferimento, nuova), dove `nuova` dice se è stata creata una versione;
    None se il registro non è raggiungibile.
    """
    try:
        import mlflow

        from ecoscan.osservabilita.tracciamento import limita_attese

        limita_attese()
        mlflow.set_tracking_uri(indirizzo or conf.MLFLOW)
        if esistente := versione_registrata(prompt):
            return f"{esistente.name}/{esistente.version}", False
        registrato = mlflow.genai.register_prompt(
            name=nome_registrato(prompt),
            template=prompt.testo,
            commit_message=f"versione {prompt.versione}, impronta {prompt.impronta}",
            tags={"versione": prompt.versione, "impronta": prompt.impronta,
                  "scopo": prompt.scopo},
        )
        return f"{registrato.name}/{registrato.version}", True
    except Exception as errore:                      # MLflow spento, o versione senza genai
        registro.warning("registro dei prompt non disponibile (%s): i prompt restano "
                         "comunque versionati in git", errore)
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Elenca i prompt e li pubblica nel registro MLflow.")
    ap.add_argument("--pubblica", action="store_true")
    ap.add_argument("--mlflow", default=None)
    args = ap.parse_args()

    for prompt in prompt_.tutti():
        print(f"{prompt.etichetta:34} {prompt.scopo}")
        if args.pubblica:
            esito = pubblica(prompt, args.mlflow)
            if esito is None:
                print("  non pubblicato")
            else:
                riferimento, nuova = esito
                print(f"  {'pubblicato come' if nuova else 'già presente come'} {riferimento}")


if __name__ == "__main__":
    main()
