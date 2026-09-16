"""I prompt nel registro di MLflow.

I prompt restano **file versionati in git**: quella è la verità, e il diff fra due versioni
è leggibile. Il registro di MLflow serve a un'altra cosa: collegare una versione di prompt
alle run che l'hanno usata, così quando un risultato peggiora si sa quale testo c'era.

Perciò qui non si genera nulla: si pubblica ciò che già esiste su disco, e si dichiara in
ogni traccia quale versione era in uso.

Uso:
  uv run ecoscan-prompt --pubblica      # manda i prompt al registro di MLflow
  uv run ecoscan-prompt                 # elenca quelli su disco con versione e impronta
"""
from __future__ import annotations

import argparse
import logging

from ecoscan import configurazione as conf
from ecoscan import prompt as prompt_

registro = logging.getLogger(__name__)


def pubblica(prompt: prompt_.Prompt, indirizzo: str | None = None) -> str | None:
    """Registra un prompt in MLflow. Restituisce il nome registrato, o None se non riesce."""
    try:
        import mlflow

        mlflow.set_tracking_uri(indirizzo or conf.MLFLOW)
        registrato = mlflow.genai.register_prompt(
            name=f"ecoscan-{prompt.nome}",
            template=prompt.testo,
            commit_message=f"versione {prompt.versione}, impronta {prompt.impronta}",
            tags={"versione": prompt.versione, "impronta": prompt.impronta,
                  "scopo": prompt.scopo},
        )
        return getattr(registrato, "name", f"ecoscan-{prompt.nome}")
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
            nome = pubblica(prompt, args.mlflow)
            print(f"  {'pubblicato come ' + nome if nome else 'non pubblicato'}")
