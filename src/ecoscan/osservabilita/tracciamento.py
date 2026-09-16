"""Tracciamento delle richieste su MLflow.

**Non bloccante, per scelta.** Se MLflow è spento, lento o rifiuta la scrittura, l'utente
riceve comunque la sua risposta: il tracciamento serve a capire come va il sistema, non a
farlo funzionare. Ogni errore viene inghiottito e registrato una volta sola, perché un
avviso ripetuto a ogni richiesta è rumore che si impara a ignorare.

**Cosa si registra.** Una run per richiesta, con i parametri che descrivono la domanda
(comune, modello, versione dei prompt), le metriche che descrivono l'esito (livello di
evidenza raggiunto, numero di candidati, tempi per fase) e i tag che permettono di cercare
(tipo di corrispondenza, se ha chiesto un chiarimento).

**Cosa NON si registra.** Le immagini: restano sul computer di chi le ha scattate. Si
registra l'impronta della foto, che basta a riconoscere richieste ripetute senza
conservarne il contenuto.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from ecoscan import configurazione as conf

registro = logging.getLogger(__name__)


@dataclass
class Traccia:
    """Ciò che si è osservato durante una richiesta. Si riempie man mano e si invia alla fine."""

    comune: str
    modello_visione: str = ""
    modello_embedding: str = ""
    prompt: list[str] = field(default_factory=list)
    impronta_foto: str | None = None
    testo_utente: str | None = None
    oggetto: str | None = None
    confidenza: float = 0.0
    livello_evidenza: int = 0
    candidati: int = 0
    tipo_corrispondenza: str = ""
    chiarimento: bool = False
    definitiva: bool = False
    contraddizione: bool = False
    destinazioni: list[str] = field(default_factory=list)
    durate: dict[str, float] = field(default_factory=dict)

    @contextmanager
    def fase(self, nome: str):
        """Misura una fase: i tempi per fase sono il dato più utile su CPU."""
        inizio = time.monotonic()
        try:
            yield
        finally:
            self.durate[nome] = round(time.monotonic() - inizio, 3)

    def parametri(self) -> dict[str, str]:
        return {k: str(v) for k, v in {
            "comune": self.comune,
            "modello_visione": self.modello_visione,
            "modello_embedding": self.modello_embedding,
            "prompt": ", ".join(self.prompt),
            "impronta_foto": self.impronta_foto or "",
            "con_testo_utente": bool(self.testo_utente),
        }.items() if v not in ("", None)}

    def metriche(self) -> dict[str, float]:
        misure = {"livello_evidenza": float(self.livello_evidenza),
                  "candidati": float(self.candidati),
                  "confidenza": float(self.confidenza)}
        misure.update({f"durata_{fase}": durata for fase, durata in self.durate.items()})
        if self.durate:
            misure["durata_totale"] = round(sum(self.durate.values()), 3)
        return misure

    def etichette(self) -> dict[str, str]:
        return {"oggetto": self.oggetto or "(non riconosciuto)",
                "tipo_corrispondenza": self.tipo_corrispondenza or "(nessuna)",
                "chiarimento": "si" if self.chiarimento else "no",
                "definitiva": "si" if self.definitiva else "no",
                "contraddizione": "si" if self.contraddizione else "no",
                "destinazioni": " oppure ".join(self.destinazioni) or "(nessuna)"}


def impronta(dati: bytes) -> str:
    """Identifica una foto senza conservarla: due richieste sulla stessa immagine si
    riconoscono, ma l'immagine non lascia il computer dell'utente."""
    return hashlib.sha256(dati).hexdigest()[:16]


class Tracciatore:
    """Invia le tracce a MLflow. Si può spegnere, e se MLflow non risponde non disturba."""

    def __init__(self, indirizzo: str | None = None, esperimento: str | None = None,
                 attivo: bool | None = None):
        self.indirizzo = indirizzo or conf.MLFLOW
        self.esperimento = esperimento or conf.MLFLOW_ESPERIMENTO
        self.attivo = conf.MLFLOW_ATTIVO if attivo is None else attivo
        self._avvisato = False
        self._pronto = False

    def _prepara(self) -> bool:
        if not self.attivo:
            return False
        if self._pronto:
            return True
        # Un tracciamento non bloccante deve fallire IN FRETTA: senza questi limiti il
        # client di MLflow riprova per minuti, e la risposta all'utente resta appesa.
        os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", str(conf.MLFLOW_ATTESA))
        os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "1")
        os.environ.setdefault("MLFLOW_HTTP_REQUEST_BACKOFF_FACTOR", "0")
        try:
            import mlflow

            mlflow.set_tracking_uri(self.indirizzo)
            mlflow.set_experiment(self.esperimento)
            self._pronto = True
        except Exception as errore:                  # server spento, permessi, versione
            self._avvisa(errore)
        return self._pronto

    def _avvisa(self, errore: Exception) -> None:
        """Una volta sola: un avviso a ogni richiesta è rumore che si impara a ignorare."""
        if not self._avvisato:
            registro.warning("tracciamento MLflow non disponibile (%s): le risposte continuano "
                             "a funzionare, i dati non vengono registrati", errore)
            self._avvisato = True

    def registra(self, traccia: Traccia, nome: str = "analisi") -> bool:
        """Registra una traccia. Restituisce True se è stata scritta davvero."""
        if not self._prepara():
            return False
        try:
            import mlflow

            with mlflow.start_run(run_name=nome):
                mlflow.log_params(traccia.parametri())
                mlflow.log_metrics(traccia.metriche())
                mlflow.set_tags(traccia.etichette())
            return True
        except Exception as errore:                  # la risposta all'utente non si ferma qui
            self._avvisa(errore)
            return False
