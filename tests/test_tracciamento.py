"""Test del tracciamento su MLflow Tracing.

Due cose contano più di tutte le altre:

- **non deve mai bloccare**: se MLflow è spento o rifiuta la scrittura, l'utente riceve
  comunque la sua risposta, e un errore dell'agente non viene nascosto;
- **deve registrare ciò che serve**: input e output di ogni turno con la foto, i documenti
  del retrieval, la sessione, la versione dell'applicazione e dei prompt.

I test usano un archivio MLflow locale (SQLite in una cartella temporanea): nessun server,
nessuna rete.
"""
import logging
import time

import pytest

from ecoscan import prompt as prompt_
from ecoscan.agente.agente import Agente
from ecoscan.agente.tipi import Candidato, Riconoscimento, Variante
from ecoscan.osservabilita import tracciamento as tr
from ecoscan.osservabilita.tracciamento import (
    SpanNullo, Tracciatore, TracciatoreNullo, documento, impronta, impronta_configurazione,
    tipo_immagine,
)
from tests.conftest import SceglieIlDocumento

mlflow = pytest.importorskip("mlflow")

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# ---------------------------------------------------------------------- archivio locale

@pytest.fixture
def archivio(tmp_path, monkeypatch):
    """Un archivio MLflow usa e getta, con gli artefatti (le foto) nella cartella temporanea."""
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    mlflow.set_tracking_uri(uri)
    mlflow.create_experiment("prova", artifact_location=(tmp_path / "artefatti").as_uri())
    yield uri
    mlflow.set_tracking_uri(None)


def tracciatore(archivio, **opzioni) -> Tracciatore:
    return Tracciatore(indirizzo=archivio, esperimento="prova", **opzioni)


def tracce() -> list:
    mlflow.flush_trace_async_logging()
    esperimento = mlflow.get_experiment_by_name("prova")
    trovate = mlflow.search_traces(locations=[esperimento.experiment_id], return_type="list")
    return sorted(trovate, key=lambda t: t.info.request_time)


def span(traccia, nome):
    return next(s for s in traccia.data.spans if s.name == nome)


def bottiglia():
    return SceglieIlDocumento("bottiglia", Riconoscimento(oggetto="bottiglia di plastica",
                                                         confidenza=0.9))


def pizza():
    return SceglieIlDocumento("cartone da pizza", Riconoscimento(oggetto="cartone della pizza",
                                                                 confidenza=0.9))


# ---------------------------------------------------------------------- funzioni pure

def test_l_impronta_identifica_la_foto():
    assert impronta(b"una foto") == impronta(b"una foto")
    assert impronta(b"una foto") != impronta(b"un'altra foto")
    assert len(impronta(b"x")) == 16


def test_il_tipo_della_foto_si_legge_dai_byte():
    """Il nome del file caricato non è affidabile: gli smartphone mandano di tutto."""
    assert tipo_immagine(JPEG) == "image/jpeg"
    assert tipo_immagine(PNG) == "image/png"
    assert tipo_immagine(b"testo qualsiasi") == "application/octet-stream"


def test_la_versione_dell_applicazione_dipende_solo_dai_parametri():
    a = {"modello_visione": "gemma3:4b", "k": "8"}
    assert impronta_configurazione(a) == impronta_configurazione(dict(reversed(a.items())))
    assert impronta_configurazione(a) != impronta_configurazione({**a, "k": "12"})


def test_il_documento_del_retrieval_ha_testo_e_metadati():
    """È il formato che l'interfaccia di MLflow mostra negli span RETRIEVER."""
    candidato = Candidato(id="x", livello=1, testo="Cartone per pizze. …", nome="Cartone per pizze",
                          varianti=[Variante(["unto"], ["organico"])], punteggio=0.61234)
    doc = documento(candidato)
    assert doc["id"] == "x" and doc["page_content"].startswith("Cartone per pizze")
    assert doc["metadata"]["destinazioni"] == ["organico"]
    assert doc["metadata"]["varianti"][0]["condizione"] == "unto"
    assert doc["metadata"]["punteggio"] == 0.6123


def test_l_agente_include_i_prompt_nella_configurazione(ambiente):
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia())
    configurazione = agente.configurazione()
    assert configurazione["prompt_scelta"] == prompt_.carica("scelta").etichetta
    assert {"modello_visione", "modello_embedding", "k", "confidenza_minima"} <= set(configurazione)


# ---------------------------------------------------------------------- senza MLflow

def test_senza_tracciatore_l_agente_funziona_uguale(ambiente):
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia())
    assert isinstance(agente.tracciatore, TracciatoreNullo)
    risposta = agente.analizza(JPEG, "Torino")
    assert risposta.livello_evidenza in (1, 2, 3)
    assert risposta.contesto["id_conversazione"]


def test_si_puo_spegnere(ambiente, archivio):
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia(),
                    tracciatore=tracciatore(archivio, attivo=False))
    agente.analizza(JPEG, "Torino")
    assert tracce() == []


def test_mlflow_spento_non_ferma_la_risposta(ambiente, caplog):
    """Il server non risponde: la risposta arriva, in fretta, con un solo avviso."""
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia(),
                    tracciatore=Tracciatore(indirizzo="http://127.0.0.1:1", esperimento="prova"))
    inizio = time.monotonic()
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert agente.analizza(JPEG, "Torino").livello_evidenza == 1
    assert time.monotonic() - inizio < 15
    assert caplog.text.count("MLflow") == 1


def test_dopo_un_guasto_si_riprova_solo_dopo_l_attesa(monkeypatch):
    """Riprovare a ogni richiesta rallenterebbe tutte le risposte mentre MLflow è spento."""
    tentativi = []
    t = Tracciatore(indirizzo="http://127.0.0.1:1", esperimento="prova", riprova_dopo=60)
    monkeypatch.setattr(t, "_raggiungibile", lambda: (tentativi.append(1), 1 / 0))
    assert t._prepara() is False and t._prepara() is False
    assert len(tentativi) == 1
    t._ultimo_tentativo -= 61
    t._prepara()
    assert len(tentativi) == 2


def test_un_errore_dell_agente_non_viene_nascosto(ambiente, archivio):
    """Il tracciamento inghiotte i propri errori, non quelli di chi traccia."""
    class ModelloRotto(type(bottiglia())):
        def riconosci(self, immagine, testo_utente=None):
            raise RuntimeError("Ollama spento")

    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore,
                    ModelloRotto("x", Riconoscimento(oggetto="x")),
                    tracciatore=tracciatore(archivio))
    with pytest.raises(RuntimeError, match="Ollama spento"):
        agente.analizza(JPEG, "Torino")


def test_span_nullo_fuori_dal_turno(archivio):
    """La valutazione chiama `rispondi` da sola: niente tracce orfane."""
    t = tracciatore(archivio)
    with t.span("recupero_livello1", tr.RETRIEVER, {}) as s:
        assert isinstance(s, SpanNullo) and not s.trace_id


# ---------------------------------------------------------------------- cosa si registra

def test_un_turno_registra_input_output_e_foto(ambiente, archivio):
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia(),
                    tracciatore=tracciatore(archivio))
    risposta = agente.analizza(JPEG, "Torino", testo_utente="è vuota")

    [traccia] = tracce()
    radice = span(traccia, "analizza")
    assert radice.span_type == "CHAIN"
    assert radice.inputs["comune"] == "Torino" and radice.inputs["testo_utente"] == "è vuota"
    assert radice.inputs["impronta_foto"] == impronta(JPEG)
    assert radice.inputs["foto"].startswith("mlflow-attachment://")
    assert "image%2Fjpeg" in radice.inputs["foto"]
    assert radice.outputs["destinazioni"] == risposta.destinazioni
    assert radice.outputs["riconoscimento"]["oggetto"] == "bottiglia di plastica"

    riconoscimento = span(traccia, "riconoscimento")
    assert riconoscimento.span_type == "LLM"
    assert riconoscimento.inputs["prompt"] == prompt_.carica("riconoscimento").etichetta
    assert riconoscimento.outputs["oggetto"] == "bottiglia di plastica"

    scelta = span(traccia, "scelta_livello1")
    assert scelta.span_type == "LLM" and scelta.inputs["candidati"]
    assert scelta.outputs["tipo_corrispondenza"] == "stesso_oggetto"

    assert traccia.info.tags["turno"] == "analizza"
    assert traccia.info.tags["destinazioni"] == "imballaggi_plastica"


def test_il_retrieval_registra_domande_e_documenti(ambiente, archivio):
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia(),
                    tracciatore=tracciatore(archivio))
    risposta = agente.analizza(JPEG, "Torino")

    recupero = span(tracce()[0], "recupero_livello1")
    assert recupero.span_type == "RETRIEVER"
    assert recupero.inputs["domande"] and recupero.inputs["comune"] == "Torino"
    documenti = recupero.outputs
    assert [d["id"] for d in documenti] == [c.id for c in risposta.candidati if c.livello == 1]
    assert all(d["page_content"] and "destinazioni" in d["metadata"] for d in documenti)


def test_senza_salvataggio_delle_foto_resta_l_impronta(ambiente, archivio):
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia(),
                    tracciatore=tracciatore(archivio, salva_foto=False))
    agente.analizza(JPEG, "Torino")
    radice = span(tracce()[0], "analizza")
    assert radice.inputs["foto"] == impronta(JPEG)


def test_i_turni_di_una_conversazione_condividono_la_sessione(ambiente, archivio):
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, pizza(),
                    tracciatore=tracciatore(archivio))
    prima = agente.analizza(JPEG, "Torino")
    assert prima.chiarimento
    dopo = agente.continua(prima.contesto, "è unto")
    assert dopo.contesto["id_conversazione"] == prima.contesto["id_conversazione"]

    analizza, continua = tracce()
    sessione = prima.contesto["id_conversazione"]
    assert analizza.info.trace_metadata["mlflow.trace.session"] == sessione
    assert continua.info.trace_metadata["mlflow.trace.session"] == sessione
    assert span(continua, "continua").inputs["risposta_utente"] == "è unto"
    assert span(continua, "continua").outputs["destinazioni"] == ["organico"]


def test_un_contesto_senza_conversazione_ne_apre_una_nuova(ambiente, archivio):
    """Un client precedente a questa versione non manda l'identificativo."""
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, pizza(),
                    tracciatore=tracciatore(archivio))
    contesto = dict(agente.analizza(JPEG, "Torino").contesto)
    contesto.pop("id_conversazione")
    assert agente.continua(contesto, "è unto").contesto["id_conversazione"]


def test_rispondi_da_solo_non_crea_tracce(ambiente, archivio):
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia(),
                    tracciatore=tracciatore(archivio))
    agente.analizza(JPEG, "Torino")          # prepara il tracciatore
    agente.rispondi(Riconoscimento(oggetto="bottiglia di plastica", confidenza=0.9), "Torino")
    assert len(tracce()) == 1


def test_la_traccia_e_collegata_alla_versione_dell_applicazione(ambiente, archivio):
    t = tracciatore(archivio)
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia(), tracciatore=t)
    agente.analizza(JPEG, "Torino")

    [traccia] = tracce()
    assert traccia.info.trace_metadata.get("mlflow.modelId") == t.id_modello
    modello = mlflow.get_logged_model(t.id_modello)
    assert modello.params["modello_visione"] == agente.modello.nome
    assert modello.params["prompt_scelta"] == prompt_.carica("scelta").etichetta
    assert traccia.info.tags["param.k"] == str(agente.k)

    # stessi parametri dopo un riavvio: stesso LoggedModel, non uno nuovo
    di_nuovo = tracciatore(archivio)
    Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia(),
           tracciatore=di_nuovo).analizza(JPEG, "Torino")
    assert di_nuovo.id_modello == t.id_modello


def test_i_prompt_pubblicati_sono_collegati_alle_tracce(ambiente, archivio):
    from ecoscan.osservabilita.prompt_registrati import pubblica

    for p in prompt_.tutti():
        assert pubblica(p, archivio)[1] is True
    for p in prompt_.tutti():
        assert pubblica(p, archivio)[1] is False, "ripubblicare non crea versioni doppie"

    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia(),
                    tracciatore=tracciatore(archivio))
    agente.analizza(JPEG, "Torino")
    collegati = tracce()[0].info.tags.get("mlflow.linkedPrompts", "")
    for p in prompt_.tutti():
        assert f"ecoscan-{p.nome}" in collegati


def test_un_prompt_non_pubblicato_non_impedisce_di_tracciare(ambiente, archivio):
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia(),
                    tracciatore=tracciatore(archivio))
    agente.analizza(JPEG, "Torino")
    [traccia] = tracce()
    assert "mlflow.linkedPrompts" not in traccia.info.tags
    assert traccia.info.tags["param.prompt_scelta"] == prompt_.carica("scelta").etichetta


def test_anche_la_correzione_e_un_turno_della_conversazione(ambiente, archivio):
    """Correggere l'oggetto è parte della stessa conversazione: va letta insieme agli altri
    turni, non come una richiesta a sé."""
    agente = Agente(ambiente.qdrant, ambiente.vettorizzatore, bottiglia(),
                    tracciatore=tracciatore(archivio))
    prima = agente.analizza(JPEG, "Torino")
    agente.correggi(prima.contesto, "giornali e riviste")

    analizza, correggi = tracce()
    sessione = prima.contesto["id_conversazione"]
    assert correggi.info.tags["turno"] == "correggi"
    assert correggi.info.trace_metadata["mlflow.trace.session"] == sessione
    assert span(correggi, "correggi").inputs["oggetto_corretto"] == "giornali e riviste"
