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
# Modello multimodale che legge le foto e sceglie fra i candidati
MODELLO_VISIONE = _testo("ECOSCAN_MODELLO_VISIONE", "gemma4:e2b")
# Endpoint di Ollama per le conversazioni (diverso da quello degli embedding)
OLLAMA_CHAT = _testo("ECOSCAN_OLLAMA_CHAT", OLLAMA.replace("/api/embed", "/api/chat"))
# Quanto Ollama tiene il modello in memoria dopo una richiesta. Senza questo, fra una
# chiamata e l'altra il modello viene scaricato e ricaricato: su CPU sono decine di secondi
# buttati a ogni passaggio. Costa memoria: metterlo a "0" lo scarica subito.
OLLAMA_KEEP_ALIVE = _testo("ECOSCAN_OLLAMA_KEEP_ALIVE", "30m")
# Lato lungo massimo delle immagini inviate al modello. Le foto degli smartphone sono molto
# più grandi di quanto il modello guardi davvero: mandarle intere costa byte, non dettaglio.
LATO_MAX_IMMAGINE = _intero("ECOSCAN_LATO_MAX_IMMAGINE", 1024)
# Quante schede si vettorizzano per chiamata
LOTTO_EMBEDDING = _intero("ECOSCAN_LOTTO_EMBEDDING", 32)


def riepilogo() -> dict[str, str]:
    """Valori in uso, per mostrarli nei comandi: è il modo più rapido per scoprire
    che una variabile non era impostata come si credeva."""
    return {"qdrant": QDRANT, "ollama": OLLAMA, "modello": MODELLO_EMBEDDING,
            "modello_visione": MODELLO_VISIONE, "keep_alive": OLLAMA_KEEP_ALIVE,
            "lato_max_immagine": str(LATO_MAX_IMMAGINE),
            "lotto": str(LOTTO_EMBEDDING),
            "modalita_qdrant": "server" if QDRANT.startswith(("http://", "https://")) else "in-process"}
