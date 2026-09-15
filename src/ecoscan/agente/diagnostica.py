"""Diagnostica del canale immagine verso Ollama.

Una descrizione sbagliata non dice se il modello vede male o non vede affatto. Qui si
costruisce un'immagine il cui contenuto è noto con certezza — un rettangolo di un colore
pieno — e si chiede al modello di dire quale colore è. Se sbaglia, il canale è rotto:
nessun modello che riceve un'immagine tutta rossa risponde "griglia di blocchi".

Il PNG è generato a mano, senza librerie: servono una ventina di righe e nessuna dipendenza.
"""
from __future__ import annotations

import json
import struct
import urllib.error
import urllib.request
import zlib

from ecoscan import configurazione as conf

COLORI = {"rosso": (220, 20, 20), "verde": (20, 160, 60), "blu": (30, 60, 200)}


def png_tinta_unita(colore: tuple[int, int, int], lato: int = 256) -> bytes:
    """Un PNG valido, di un solo colore. Il contenuto è noto: è questo che lo rende utile."""
    riga = b"\x00" + bytes(colore) * lato          # filtro 0 + pixel RGB
    grezzo = riga * lato

    def blocco(tipo: bytes, dati: bytes) -> bytes:
        corpo = tipo + dati
        return struct.pack(">I", len(dati)) + corpo + struct.pack(">I", zlib.crc32(corpo))

    intestazione = struct.pack(">IIBBBBB", lato, lato, 8, 2, 0, 0, 0)  # 8 bit, RGB
    return (b"\x89PNG\r\n\x1a\n" + blocco(b"IHDR", intestazione)
            + blocco(b"IDAT", zlib.compress(grezzo)) + blocco(b"IEND", b""))


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


def prova_colore(url_chat: str, modello: str, colore: str = "rosso") -> str:
    immagine = png_tinta_unita(COLORI[colore])
    import base64
    dati = _chiedi(url_chat, {
        "model": modello, "stream": False, "keep_alive": conf.OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0.0},
        "messages": [{"role": "user",
                      "content": "Rispondi con una sola parola: di che colore è questa immagine?",
                      "images": [base64.b64encode(immagine).decode()]}],
    }, timeout=600)
    return dati["message"]["content"].strip()


def scalini(modello: str, url_chat: str, foto: bytes,
            lati=(2048, 1024, 512, 256)) -> list[tuple[int, str, str]]:
    """Descrive la STESSA foto a dimensioni decrescenti.

    Se le descrizioni diventano sensate solo sotto una certa misura, il problema è la
    dimensione dell'immagine, non il modello né i prompt. Se restano tutte assurde, la
    dimensione non c'entra.
    """
    import base64

    from ecoscan.agente.immagini import informazioni, prepara

    esiti = []
    for lato in lati:
        ridotta = prepara(foto, lato_max=lato)
        dati = _chiedi(url_chat, {
            "model": modello, "stream": False, "keep_alive": conf.OLLAMA_KEEP_ALIVE,
            "options": {"temperature": 0.0},
            "messages": [{"role": "user",
                          "content": "In una frase, che oggetto è ritratto in questa immagine?",
                          "images": [base64.b64encode(ridotta).decode()]}],
        }, timeout=900)
        esiti.append((lato, str(informazioni(ridotta)), dati["message"]["content"].strip()))
    return esiti


def esegui(modello: str, url_chat: str) -> list[tuple[bool, str]]:
    base = url_chat.split("/api/")[0]
    esiti: list[tuple[bool, str]] = []

    versione = versione_ollama(base)
    esiti.append(("non raggiungibile" not in versione, f"versione di Ollama: {versione}"))

    capacita = capacita_modello(base, modello)
    esiti.append(("vision" in capacita,
                  f"capacità dichiarate da {modello}: {', '.join(capacita) or '(nessuna)'}"))

    atteso = "rosso"
    try:
        risposta = prova_colore(url_chat, modello, atteso)
    except Exception as errore:
        esiti.append((False, f"prova del colore fallita: {errore}"))
        return esiti
    esiti.append((atteso in risposta.lower(),
                  f"immagine tutta {atteso}, il modello risponde: {risposta[:80]!r}"))
    return esiti
