"""Impostazioni del progetto, lette una volta sola dal file `.env`.

Il file si trova alla radice ed è escluso da git; `.env.example` ne è il modello versionato.
Le variabili d'ambiente vere hanno la precedenza sul file, così un container può
sovrascrivere un valore senza modificare nulla su disco.

Il caricamento avviene in `percorsi.py`, che è importato prima di tutto il resto.
"""
from __future__ import annotations

import os

from ecoscan.percorsi import DATI


def _testo(nome: str, default: str) -> str:
    valore = os.environ.get(nome, "").strip()
    return valore or default


def _intero(nome: str, default: int) -> int:
    valore = os.environ.get(nome, "").strip()
    if not valore:
        return default
    if not valore.lstrip("-").isdigit():
        raise SystemExit(f"{nome} deve essere un numero intero, trovato {valore!r} (vedi .env)")
    return int(valore)


# Dove sta Qdrant: un URL usa il server, un percorso la modalità in-process
QDRANT = _testo("ECOSCAN_QDRANT", str(DATI / "qdrant"))
# Endpoint di Ollama per gli embedding
OLLAMA = _testo("ECOSCAN_OLLAMA", "http://localhost:11434/api/embed")
# Modello di embedding: cambiarlo richiede di reindicizzare
MODELLO_EMBEDDING = _testo("ECOSCAN_MODELLO_EMBEDDING", "embeddinggemma")
# Modello multimodale che legge le foto e sceglie fra i candidati.
# Predefinito gemma3:4b: su questa installazione gemma4 (e2b ed e4b) non interpreta le
# fotografie, pur dichiarando la capacità "vision" e superando le prove su immagini
# sintetiche. Vedi docs/diario.md, decisione D79. Il modello resta sostituibile da .env.
MODELLO_VISIONE = _testo("ECOSCAN_MODELLO_VISIONE", "gemma3:4b")
# Endpoint di Ollama per le conversazioni (diverso da quello degli embedding)
OLLAMA_CHAT = _testo("ECOSCAN_OLLAMA_CHAT", OLLAMA.replace("/api/embed", "/api/chat"))
# Quanto Ollama tiene il modello in memoria dopo una richiesta. Senza questo, fra una
# chiamata e l'altra il modello viene scaricato e ricaricato: su CPU sono decine di secondi
# buttati a ogni passaggio. Costa memoria: metterlo a "0" lo scarica subito.
OLLAMA_KEEP_ALIVE = _testo("ECOSCAN_OLLAMA_KEEP_ALIVE", "30m")
# Lato lungo massimo delle immagini inviate al modello. Le foto degli smartphone sono molto
# più grandi di quanto il modello guardi davvero: mandarle intere costa byte, non dettaglio.
LATO_MAX_IMMAGINE = _intero("ECOSCAN_LATO_MAX_IMMAGINE", 1024)
# EmbeddingGemma prevede prefissi diversi per documenti e interrogazioni. Alcune versioni di
# Ollama però li applicano già da sé: in quel caso i nostri li duplicherebbero, peggiorando
# il recupero. L'interruttore serve a misurare quale delle due configurazioni funziona.
PREFISSI_EMBEDDING = _testo("ECOSCAN_PREFISSI_EMBEDDING", "si").lower() not in ("no", "0", "false")
# Arricchimento dei documenti con dati della fonte (canale, flussi, regole che nominano
# l'oggetto). Si spegne per misurare quanto vale: `ECOSCAN_ARRICCHIMENTO=no` e si rivettorizza.
ARRICCHIMENTO = _testo("ECOSCAN_ARRICCHIMENTO", "si").lower() not in ("no", "0", "false")
# Dove il frontend trova il backend. In Docker diventa il nome del servizio.
API = _testo("ECOSCAN_API", "http://localhost:8000/api/v1")
# Tracciamento su MLflow. Non è mai bloccante: se il server non risponde, le risposte
# continuano ad arrivare e i dati semplicemente non vengono registrati.
MLFLOW = _testo("ECOSCAN_MLFLOW", "http://localhost:5000")
MLFLOW_ESPERIMENTO = _testo("ECOSCAN_MLFLOW_ESPERIMENTO", "ecoscan-chat")
MLFLOW_ATTIVO = _testo("ECOSCAN_MLFLOW_ATTIVO", "si").lower() not in ("no", "0", "false")
# Secondi di attesa prima di rinunciare: un tracciamento non bloccante fallisce in fretta
MLFLOW_ATTESA = _intero("ECOSCAN_MLFLOW_ATTESA", 3)
# Le foto delle richieste si salvano come allegati delle tracce; con "no" resta solo
# l'impronta (D124)
MLFLOW_FOTO = _testo("ECOSCAN_MLFLOW_FOTO", "si").lower() not in ("no", "0", "false")
# Dopo un guasto di MLflow si riprova solo dopo questi secondi: riprovare a ogni richiesta
# rallenterebbe tutte le risposte mentre il server è spento
MLFLOW_RIPROVA = _intero("ECOSCAN_MLFLOW_RIPROVA", 60)
# Quanti riconoscimenti tenere in memoria: la stessa foto non si guarda due volte.
# Su CPU il riconoscimento è il passaggio lento, e riprovare la stessa foto è comune.
# 0 spegne la cache. Non sopravvive al riavvio del backend, di proposito.
CACHE_RICONOSCIMENTI = _intero("ECOSCAN_CACHE_RICONOSCIMENTI", 64)
# Quante schede si vettorizzano per chiamata
LOTTO_EMBEDDING = _intero("ECOSCAN_LOTTO_EMBEDDING", 32)


def riepilogo() -> dict[str, str]:
    """Valori in uso, per mostrarli nei comandi: è il modo più rapido per scoprire
    che una variabile non era impostata come si credeva."""
    return {"qdrant": QDRANT, "ollama": OLLAMA, "modello": MODELLO_EMBEDDING,
            "modello_visione": MODELLO_VISIONE, "keep_alive": OLLAMA_KEEP_ALIVE,
            "lato_max_immagine": str(LATO_MAX_IMMAGINE),
            "prefissi_embedding": "si" if PREFISSI_EMBEDDING else "no",
            "arricchimento": "si" if ARRICCHIMENTO else "no", "api": API,
            "mlflow": (MLFLOW + (" (con foto)" if MLFLOW_FOTO else " (solo impronte)"))
            if MLFLOW_ATTIVO else "spento",
            "lotto": str(LOTTO_EMBEDDING),
            "modalita_qdrant": "server" if QDRANT.startswith(("http://", "https://")) else "in-process"}
