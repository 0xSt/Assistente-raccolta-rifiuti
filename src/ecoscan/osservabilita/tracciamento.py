"""Tracciamento delle conversazioni su MLflow Tracing.

**Cosa si registra.** Tre cose, e basta:

1. **input e output di ogni turno** di conversazione. Ogni chiamata ad `analizza` o a
   `continua` produce una traccia; dentro ci sono gli span delle chiamate al modello
   (riconoscimento e scelta) con i loro ingressi e le loro uscite. La foto viene salvata
   come allegato della traccia. I turni della stessa conversazione condividono la sessione
   (`mlflow.trace.session`), così si leggono insieme;
2. **i risultati del retrieval**: uno span RETRIEVER per livello di evidenza, con le
   formulazioni poste all'indice e i documenti restituiti;
3. **la versione dell'applicazione**: i parametri significativi (modelli, `k`, soglie,
   prompt) formano un LoggedModel a cui ogni traccia è collegata, e le versioni dei prompt
   pubblicate nel registro sono collegate a ogni traccia.

L'evaluation non è qui: si imposterà in seguito, sopra queste tracce.

**Non bloccante, per scelta.** Se MLflow è spento, lento o rifiuta la scrittura, l'utente
riceve comunque la sua risposta. Ogni errore di MLflow viene inghiottito e segnalato una
volta sola; gli errori dell'agente invece passano sempre, perché nasconderli sarebbe peggio.
Se il server non risponde, si riprova dopo `ECOSCAN_MLFLOW_RIPROVA` secondi: MLflow può
partire dopo il backend senza costringere a riavviarlo.

**L'agente non importa `mlflow`.** Usa questo modulo attraverso `Tracciatore` oppure
`TracciatoreNullo`, che non fa nulla: i test dell'agente girano senza MLflow.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from typing import Any
from collections.abc import Iterator

from ecoscan import configurazione as conf

registro = logging.getLogger(__name__)

# Tipi di span di MLflow, ripetuti qui come testo per non importare mlflow nell'agente
CATENA, LLM, RETRIEVER = "CHAIN", "LLM", "RETRIEVER"

# Vero dentro un turno. Fuori da un turno (la valutazione che chiama `rispondi` da sola)
# gli span non si registrano: diventerebbero ciascuno una traccia orfana.
_nel_turno: ContextVar[bool] = ContextVar("ecoscan_nel_turno", default=False)


# ---------------------------------------------------------------------- funzioni pure

def impronta(dati: bytes) -> str:
    """Identifica una foto: due richieste sulla stessa immagine si riconoscono anche senza
    aprire l'allegato."""
    return hashlib.sha256(dati).hexdigest()[:16]


def limita_attese() -> None:
    """Un tracciamento non bloccante deve fallire IN FRETTA: senza questi limiti il client
    di MLflow riprova per minuti un server spento, e la risposta all'utente resta appesa."""
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", str(conf.MLFLOW_ATTESA))
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "1")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_BACKOFF_FACTOR", "0")


def nuova_conversazione() -> str:
    return uuid.uuid4().hex


def tipo_immagine(dati: bytes) -> str:
    """Il content type dai primi byte: il nome del file caricato non è affidabile."""
    if dati.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if dati.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if dati[:4] == b"RIFF" and dati[8:12] == b"WEBP":
        return "image/webp"
    if dati[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if dati[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1"):
        return "image/heic"
    return "application/octet-stream"


def impronta_configurazione(parametri: dict[str, str]) -> str:
    """Stessi parametri, stessa impronta: è ciò che separa una versione dell'app dall'altra."""
    testo = json.dumps(parametri, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:8]


def documento(candidato) -> dict:
    """Un candidato nel formato documento che l'interfaccia di MLflow mostra negli span
    RETRIEVER: testo in `page_content`, il resto in `metadata`."""
    return {
        "id": candidato.id,
        "page_content": candidato.testo,
        "metadata": {
            "nome": candidato.nome,
            "livello": candidato.livello,
            "tipo": candidato.tipo,
            "polarita": candidato.polarita,
            "destinazioni": candidato.destinazioni,
            "varianti": [{"condizione": v.condizione, "destinazioni": v.destinazioni,
                          "avvertenza": v.avvertenza} for v in candidato.varianti],
            "punteggio": round(float(candidato.punteggio), 4),
            "per_codice": candidato.per_codice,
            "codice_materiale": candidato.codice_materiale,
            "fonte": candidato.fonte,
            "riferimento": candidato.riferimento,
            "contraddizione": candidato.contraddizione,
        },
    }


def uscita_risposta(risposta) -> dict:
    """La risposta come la vede l'utente, senza candidati (stanno negli span RETRIEVER) e
    senza contesto (è un dettaglio di trasporto)."""
    return {
        "livello_evidenza": risposta.livello_evidenza,
        "comune": risposta.comune,
        "oggetto": risposta.oggetto,
        "destinazioni": risposta.destinazioni,
        "polarita": risposta.polarita,
        "condizioni": risposta.condizioni,
        "avvertenza": risposta.avvertenza,
        "fonte": risposta.fonte,
        "riferimento": risposta.riferimento,
        "chiarimento": risposta.chiarimento,
        "definitiva": risposta.definitiva,
        "tipo_corrispondenza": risposta.tipo_corrispondenza,
        "motivo": risposta.motivo,
        "contraddizione": risposta.contraddizione,
        "riconoscimento": asdict(risposta.riconoscimento) if risposta.riconoscimento else None,
    }


def etichette_risposta(risposta) -> dict[str, str]:
    """Tag per filtrare le tracce nella lista, senza aprirle."""
    return {
        "livello_evidenza": str(risposta.livello_evidenza),
        "oggetto": risposta.oggetto or "(non riconosciuto)",
        "destinazioni": " oppure ".join(risposta.destinazioni) or "(nessuna)",
        "tipo_corrispondenza": risposta.tipo_corrispondenza or "(nessuna)",
        "chiarimento": "si" if risposta.chiarimento else "no",
        "definitiva": "si" if risposta.definitiva else "no",
    }


def _serializzabile(valore: Any) -> Any:
    return asdict(valore) if is_dataclass(valore) and not isinstance(valore, type) else valore


# ---------------------------------------------------------------------- span

class SpanNullo:
    """Uno span che non registra nulla: quando il tracciamento è spento o MLflow non c'è."""

    trace_id: str | None = None

    def uscita(self, valore: Any) -> None:
        pass

    def attributi(self, **valori: Any) -> None:
        pass


class _Span(SpanNullo):
    def __init__(self, span, tracciatore: Tracciatore):
        self._span = span
        self._tracciatore = tracciatore
        self.trace_id = getattr(span, "trace_id", None)

    def uscita(self, valore: Any) -> None:
        self._tracciatore._prova(self._span.set_outputs, _serializzabile(valore))

    def attributi(self, **valori: Any) -> None:
        self._tracciatore._prova(self._span.set_attributes, valori)


# ---------------------------------------------------------------------- tracciatori

class TracciatoreNullo:
    """Stessa interfaccia di `Tracciatore`, nessun effetto. È il predefinito dell'agente."""

    salva_foto = False

    def configura(self, parametri: dict[str, str]) -> None:
        pass

    def allegato(self, dati: bytes) -> str:
        return impronta(dati)

    @contextmanager
    def turno(self, nome: str, conversazione: str, ingressi: dict  # noqa: ARG002
              ) -> Iterator[SpanNullo]:
        """Stessa firma di `Tracciatore.turno`, nessun effetto: i parametri servono a
        restare sostituibile, non a essere usati."""
        yield SpanNullo()

    @contextmanager
    def span(self, nome: str, tipo: str, ingressi: dict  # noqa: ARG002
             ) -> Iterator[SpanNullo]:
        yield SpanNullo()

    def chiudi_turno(self, span, risposta) -> None:
        pass


class Tracciatore(TracciatoreNullo):
    """Invia le tracce a MLflow. Si può spegnere, e se MLflow non risponde non disturba."""

    def __init__(self, indirizzo: str | None = None, esperimento: str | None = None,
                 attivo: bool | None = None, salva_foto: bool | None = None,
                 riprova_dopo: float | None = None):
        self.indirizzo = indirizzo or conf.MLFLOW
        self.esperimento = esperimento or conf.MLFLOW_ESPERIMENTO
        self.attivo = conf.MLFLOW_ATTIVO if attivo is None else attivo
        self.salva_foto = conf.MLFLOW_FOTO if salva_foto is None else salva_foto
        self.riprova_dopo = conf.MLFLOW_RIPROVA if riprova_dopo is None else riprova_dopo
        self.parametri: dict[str, str] = {}
        self.id_modello: str | None = None
        self.versioni_prompt: list = []
        self._pronto = False
        self._avvisato = False
        self._ultimo_tentativo: float | None = None

    # ------------------------------------------------------------------ preparazione

    def configura(self, parametri: dict[str, str]) -> None:
        """I parametri che definiscono la versione dell'applicazione. Li passa l'agente."""
        self.parametri = {k: str(v) for k, v in parametri.items()}

    def _avvisa(self, errore: Exception) -> None:
        """Una volta sola: un avviso a ogni richiesta è rumore che si impara a ignorare."""
        if not self._avvisato:
            registro.warning("tracciamento MLflow non disponibile (%s): le risposte continuano "
                             "a funzionare, i dati non vengono registrati", errore)
            self._avvisato = True

    def _prova(self, funzione, *argomenti, **opzioni):
        try:
            return funzione(*argomenti, **opzioni)
        except Exception as errore:                  # MLflow non deve fermare la risposta
            self._avvisa(errore)
            return None

    def _raggiungibile(self) -> None:
        """Un controllo esplicito prima di tutto: il client di MLflow, da solo, riprova a
        lungo e lascerebbe la risposta appesa."""
        if not self.indirizzo.startswith(("http://", "https://")):
            return                                   # archivio locale (test): niente rete
        import requests

        requests.get(f"{self.indirizzo.rstrip('/')}/health",
                     timeout=conf.MLFLOW_ATTESA).raise_for_status()

    def _e_ora_di_riprovare(self) -> bool:
        """Dopo un guasto si riprova a intervalli: tentare a ogni richiesta rallenterebbe
        tutte le risposte finché MLflow resta spento."""
        adesso = time.monotonic()
        if (self._ultimo_tentativo is not None
                and adesso - self._ultimo_tentativo < self.riprova_dopo):
            return False
        self._ultimo_tentativo = adesso
        return True

    def _connetti(self) -> bool:
        """Contatta il server e sceglie l'esperimento. False se non risponde."""
        limita_attese()
        try:
            self._raggiungibile()
            import mlflow

            mlflow.set_tracking_uri(self.indirizzo)
            mlflow.set_experiment(self.esperimento)
        except Exception as errore:                  # server spento, permessi, versione
            self._avvisa(errore)
            return False
        return True

    def _collega_versioni(self) -> None:
        """Versione dell'applicazione e prompt. Se falliscono, le tracce si registrano lo
        stesso: perdono i collegamenti, non i dati."""
        self.id_modello = self._prova(self._versione_applicazione)
        self.versioni_prompt = self._prova(self._versioni_prompt) or []
        if self.id_modello:
            for versione in self.versioni_prompt:
                self._prova(self._collega_prompt_al_modello, versione)

    def _prepara(self) -> bool:
        """Pronto a tracciare? Si connette alla prima richiesta, non all'avvio: il backend
        deve poter partire anche senza MLflow."""
        if not self.attivo:
            return False
        if self._pronto:
            return True
        if not self._e_ora_di_riprovare() or not self._connetti():
            return False

        self._pronto = True
        self._collega_versioni()
        self._avvisato = False                       # un guasto futuro va segnalato di nuovo
        return True

    def _versione_applicazione(self) -> str | None:
        """Un LoggedModel per ogni combinazione di parametri. Stessa combinazione, stesso
        modello: riavviare il backend non ne crea uno nuovo."""
        import mlflow

        if not self.parametri:
            return None
        nome = f"ecoscan-{impronta_configurazione(self.parametri)}"
        esperimento = mlflow.get_experiment_by_name(self.esperimento)
        esistenti = mlflow.search_logged_models(
            experiment_ids=[esperimento.experiment_id], filter_string=f"name = '{nome}'",
            max_results=1, output_format="list")
        if esistenti:
            return esistenti[0].model_id
        modello = mlflow.create_external_model(
            name=nome, params=self.parametri, model_type="agent",
            experiment_id=esperimento.experiment_id)
        return modello.model_id

    def _versioni_prompt(self) -> list:
        """Le versioni del registro che corrispondono ai prompt su disco, confrontate per
        impronta. Un prompt modificato e non ancora pubblicato semplicemente non si collega:
        la sua etichetta resta comunque nei tag della traccia."""
        from ecoscan import prompt as prompt_
        from ecoscan.osservabilita.prompt_registrati import versione_registrata

        trovate = []
        for prompt in prompt_.tutti():
            if versione := versione_registrata(prompt):
                trovate.append(versione)
            else:
                registro.info("prompt %s non pubblicato nel registro: lancia "
                              "`uv run ecoscan-prompt --pubblica`", prompt.etichetta)
        return trovate

    def _collega_prompt_al_modello(self, versione) -> None:
        from mlflow import MlflowClient

        MlflowClient().link_prompt_version_to_model(versione.name, str(versione.version),
                                                    self.id_modello)

    # ------------------------------------------------------------------ registrazione

    def allegato(self, dati: bytes):
        """La foto come allegato della traccia, oppure la sola impronta se il salvataggio
        delle foto è spento."""
        if not self.salva_foto:
            return impronta(dati)
        from mlflow.tracing.attachments import Attachment

        return Attachment(content_type=tipo_immagine(dati), content_bytes=dati)

    @contextmanager
    def span(self, nome: str, tipo: str, ingressi: dict) -> Iterator[SpanNullo]:
        """Uno span figlio del turno in corso. Fuori da un turno non registra nulla."""
        if not _nel_turno.get():
            yield SpanNullo()
            return
        with self._apri(nome, tipo, ingressi) as span:
            yield span

    @contextmanager
    def _apri(self, nome: str, tipo: str, ingressi: dict) -> Iterator[SpanNullo]:
        """Apre uno span con i suoi ingressi. Gli errori di MLflow si inghiottono, quelli
        del codice dentro il blocco no."""
        if not self._prepara():
            yield SpanNullo()
            return
        try:
            import mlflow

            gestore = mlflow.start_span(name=nome, span_type=tipo)
            grezzo = gestore.__enter__()
            grezzo.set_inputs({k: _serializzabile(v) for k, v in ingressi.items()})
        except Exception as errore:
            self._avvisa(errore)
            yield SpanNullo()
            return

        try:
            yield _Span(grezzo, self)
        except BaseException as eccezione:
            self._prova(gestore.__exit__, type(eccezione), eccezione, eccezione.__traceback__)
            raise
        else:
            self._prova(gestore.__exit__, None, None, None)

    @contextmanager
    def turno(self, nome: str, conversazione: str, ingressi: dict) -> Iterator[SpanNullo]:
        """Lo span radice di un turno: apre la traccia e la collega a sessione, versione
        dell'applicazione e prompt."""
        segno = _nel_turno.set(True)
        try:
            with self._apri(nome, CATENA, ingressi) as radice:
                if radice.trace_id:
                    self._prova(self._collega_traccia, radice.trace_id, nome, conversazione)
                yield radice
        finally:
            _nel_turno.reset(segno)

    def _collega_traccia(self, trace_id: str, nome: str, conversazione: str) -> None:
        import mlflow

        mlflow.update_current_trace(
            session_id=conversazione, model_id=self.id_modello,
            tags={"turno": nome, **{f"param.{k}": v for k, v in self.parametri.items()}})
        if self.versioni_prompt:
            from mlflow import MlflowClient

            MlflowClient().link_prompt_versions_to_trace(self.versioni_prompt, trace_id)

    def chiudi_turno(self, span, risposta) -> None:
        """Uscita e tag del turno: si chiamano prima di chiudere lo span radice."""
        span.uscita(uscita_risposta(risposta))
        if span.trace_id:
            import mlflow

            self._prova(mlflow.update_current_trace, tags=etichette_risposta(risposta))
