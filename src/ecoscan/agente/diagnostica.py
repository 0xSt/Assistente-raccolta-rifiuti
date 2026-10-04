"""Diagnostica del canale immagine verso Ollama.


"""
from __future__ import annotations

import json
import struct
import urllib.error
import urllib.request
import zlib

from ecoscan import configurazione as conf

COLORI = {"rosso": (220, 20, 20), "verde": (20, 160, 60), "blu": (30, 60, 200)}
# Una domanda sul colore di un'immagine tinta unita si può indovinare. Tre colori diversi
# e una domanda sulla POSIZIONE no: servono a distinguere "vede" da "ha tirato a indovinare".


def _blocco(tipo: bytes, dati: bytes) -> bytes:
    """Un blocco PNG: lunghezza, tipo, dati, CRC dei due precedenti."""
    corpo = tipo + dati
    return struct.pack(">I", len(dati)) + corpo + struct.pack(">I", zlib.crc32(corpo))


def _png(riga: bytes, lato: int) -> bytes:
    """Un PNG quadrato a partire da una riga di pixel, ripetuta.

    Le due immagini di prova differiscono solo nella riga: il formato — intestazione a
    8 bit RGB, blocchi IHDR/IDAT/IEND — era scritto due volte identico, e un formato
    binario duplicato e' un formato che prima o poi diverge in un punto solo.
    """
    intestazione = struct.pack(">IIBBBBB", lato, lato, 8, 2, 0, 0, 0)  # 8 bit, RGB
    return (b"\x89PNG\r\n\x1a\n" + _blocco(b"IHDR", intestazione)
            + _blocco(b"IDAT", zlib.compress(riga * lato)) + _blocco(b"IEND", b""))


def png_tinta_unita(colore: tuple[int, int, int], lato: int = 256) -> bytes:
    """Un PNG valido, di un solo colore. Il contenuto è noto: è questo che lo rende utile."""
    return _png(b"\x00" + bytes(colore) * lato, lato)      # filtro 0 + pixel RGB


def png_due_meta(sinistra: tuple[int, int, int], destra: tuple[int, int, int],
                 lato: int = 256) -> bytes:
    """Metà di un colore e metà di un altro: verifica che il modello colga anche la posizione."""
    meta = lato // 2
    return _png(b"\x00" + bytes(sinistra) * meta + bytes(destra) * (lato - meta), lato)


def _chiedi(url: str, corpo: dict, timeout: int = 60) -> dict:
    richiesta = urllib.request.Request(url, data=json.dumps(corpo).encode(),
                                       headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(richiesta, timeout=timeout) as risposta:
        return json.load(risposta)


def versione_ollama(base: str) -> str:
    try:
        with urllib.request.urlopen(f"{base}/api/version", timeout=10) as risposta:
            return json.load(risposta).get("version", "?")
    except urllib.error.URLError as errore:
        return f"non raggiungibile ({errore})"


def capacita_modello(base: str, modello: str) -> list[str]:
    """Le `capabilities` dichiarate da Ollama: qui deve comparire 'vision'."""
    try:
        dati = _chiedi(f"{base}/api/show", {"model": modello})
    except urllib.error.URLError as errore:
        return [f"errore: {errore}"]
    except Exception as errore:                      # modello assente o risposta inattesa
        return [f"errore: {errore}"]
    return dati.get("capabilities") or []


def _domanda_con_immagine(url_chat: str, modello: str, immagine: bytes, domanda: str,
                          timeout: int = 600) -> str:
    """Una domanda a Ollama su un'immagine. Temperatura zero: una diagnosi che cambia
    risposta a ogni lancio non diagnostica niente."""
    import base64

    dati = _chiedi(url_chat, {
        "model": modello, "stream": False, "keep_alive": conf.OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0.0},
        "messages": [{"role": "user", "content": domanda,
                      "images": [base64.b64encode(immagine).decode()]}],
    }, timeout=timeout)
    return dati["message"]["content"].strip()


def prova_colore(url_chat: str, modello: str, colore: str = "rosso") -> str:
    return _domanda_con_immagine(
        url_chat, modello, png_tinta_unita(COLORI[colore]),
        "Rispondi con una sola parola: di che colore è questa immagine?")


def prova_posizione(url_chat: str, modello: str, sinistra: str, destra: str) -> str:
    return _domanda_con_immagine(
        url_chat, modello, png_due_meta(COLORI[sinistra], COLORI[destra]),
        "L'immagine è divisa in due metà di colori diversi. Rispondi con una sola parola: "
        "di che colore è la metà SINISTRA?")


def scalini(modello: str, url_chat: str, foto: bytes,
            lati=(2048, 1024, 512, 256)) -> list[tuple[int, str, str]]:
    """Descrive la STESSA foto a dimensioni decrescenti.

    Se le descrizioni diventano sensate solo sotto una certa misura, il problema è la
    dimensione dell'immagine, non il modello né i prompt. Se restano tutte assurde, la
    dimensione non c'entra.
    """
    from ecoscan.agente.immagini import informazioni, prepara

    esiti = []
    for lato in lati:
        ridotta = prepara(foto, lato_max=lato)
        risposta = _domanda_con_immagine(
            url_chat, modello, ridotta,
            "In una frase, che oggetto è ritratto in questa immagine?", timeout=900)
        esiti.append((lato, str(informazioni(ridotta)), risposta))
    return esiti


def esegui(modello: str, url_chat: str) -> list[tuple[bool, str]]:
    base = url_chat.split("/api/")[0]
    esiti: list[tuple[bool, str]] = []

    versione = versione_ollama(base)
    esiti.append(("non raggiungibile" not in versione, f"versione di Ollama: {versione}"))

    capacita = capacita_modello(base, modello)
    esiti.append(("vision" in capacita,
                  f"capacità dichiarate da {modello}: {', '.join(capacita) or '(nessuna)'}"))

    # tre colori diversi: indovinarli tutti e tre per caso è improbabile
    for atteso in ("rosso", "verde", "blu"):
        try:
            risposta = prova_colore(url_chat, modello, atteso)
        except Exception as errore:
            esiti.append((False, f"prova del colore ({atteso}) fallita: {errore}"))
            return esiti
        esiti.append((atteso in risposta.lower(),
                      f"immagine tutta {atteso}, il modello risponde: {risposta[:60]!r}"))

    # la posizione non si indovina: richiede di guardare davvero dove sta cosa
    try:
        risposta = prova_posizione(url_chat, modello, "verde", "rosso")
    except Exception as errore:
        esiti.append((False, f"prova della posizione fallita: {errore}"))
        return esiti
    esiti.append(("verde" in risposta.lower(),
                  f"metà sinistra verde e metà destra rossa, il modello risponde: {risposta[:60]!r}"))
    return esiti
