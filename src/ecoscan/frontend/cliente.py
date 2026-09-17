"""Il frontend parla SOLO con il backend, mai con Qdrant, Ollama o il database.

Questo modulo è l'unico punto di contatto. Tenerlo separato dall'interfaccia ha due
vantaggi: si può provare senza avviare Streamlit, e se un giorno il frontend cambia
tecnologia il contratto resta qui.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

import requests

from ecoscan import configurazione as conf

ATTESA_LUNGA = 600   # il riconoscimento su CPU può richiedere minuti
ATTESA_BREVE = 15


class ErroreBackend(RuntimeError):
    """Il backend non risponde o rifiuta la richiesta. Il messaggio è mostrato all'utente,
    quindi deve essere comprensibile e dire cosa fare."""


@dataclass
class ClienteAPI:
    base: str = ""

    def __post_init__(self) -> None:
        self.base = (self.base or conf.API).rstrip("/")

    # ------------------------------------------------------------------ interno

    def _esito(self, risposta: requests.Response):
        if risposta.status_code >= 400:
            try:
                dettaglio = risposta.json().get("detail", risposta.text)
            except ValueError:
                dettaglio = risposta.text
            raise ErroreBackend(str(dettaglio))
        return risposta.json()

    def _chiedi(self, metodo: str, rotta: str, attesa: int, **argomenti):
        try:
            return self._esito(requests.request(metodo, f"{self.base}{rotta}",
                                                timeout=attesa, **argomenti))
        except requests.exceptions.ConnectionError as errore:
            raise ErroreBackend(
                f"Backend non raggiungibile su {self.base}. Avvialo con: uv run ecoscan-api"
            ) from errore
        except requests.exceptions.Timeout as errore:
            raise ErroreBackend(
                "Il backend non ha risposto in tempo. Su CPU il riconoscimento richiede minuti: "
                "riprova, oppure controlla che Ollama sia acceso."
            ) from errore

    def _flusso(self, rotta: str, **argomenti) -> Iterator[dict]:
        """Legge un flusso di eventi (SSE) dal backend e li restituisce uno per uno.

        L'ultimo evento è sempre `risposta` o `errore`: se il flusso finisce senza, la
        connessione si è rotta a metà e va detto, invece di lasciare l'utente con una chat
        che sembra aver funzionato.
        """
        try:
            with requests.post(f"{self.base}{rotta}", stream=True, timeout=ATTESA_LUNGA,
                               **argomenti) as risposta:
                if risposta.status_code >= 400:
                    self._esito(risposta)
                for riga in risposta.iter_lines(decode_unicode=True):
                    if riga and riga.startswith("data: "):
                        yield json.loads(riga[6:])
        except requests.exceptions.ConnectionError as errore:
            raise ErroreBackend(
                f"Backend non raggiungibile su {self.base}. Avvialo con: uv run ecoscan-api"
            ) from errore
        except requests.exceptions.Timeout as errore:
            raise ErroreBackend(
                "Il backend non ha risposto in tempo. Su CPU il riconoscimento richiede minuti: "
                "riprova, oppure controlla che Ollama sia acceso."
            ) from errore

    # ------------------------------------------------------------------ rotte

    def comuni(self) -> list[dict]:
        return self._chiedi("GET", "/comuni", ATTESA_BREVE)

    def salute(self) -> dict:
        return self._chiedi("GET", "/salute", ATTESA_BREVE)

    def destinazioni(self, comune: str) -> list[dict]:
        """I contenitori del comune con l'etichetta leggibile: si chiede una volta sola e
        serve a non mostrare all'utente i nomi interni."""
        return self._chiedi("GET", "/destinazioni", ATTESA_BREVE, params={"comune": comune})

    def analizza(self, foto: bytes, nome_file: str, comune: str, testo: str | None = None) -> dict:
        dati = {"comune": comune}
        if testo:
            dati["testo"] = testo
        return self._chiedi("POST", "/analizza", ATTESA_LUNGA, data=dati,
                            files={"foto": (nome_file, foto)})

    def continua(self, contesto: dict, risposta: str) -> dict:
        return self._chiedi("POST", "/continua", ATTESA_LUNGA,
                            json={"contesto": contesto, "risposta": risposta})

    def analizza_a_fasi(self, foto: bytes, nome: str, comune: str,
                        testo: str | None = None) -> Iterator[dict]:
        """Come `analizza`, ma restituisce le fasi mentre accadono."""
        return self._flusso("/analizza/flusso", files={"foto": (nome, foto, "image/jpeg")},
                            data={"comune": comune, "testo": testo or ""})

    def continua_a_fasi(self, contesto: dict, risposta: str) -> Iterator[dict]:
        return self._flusso("/continua/flusso",
                            json={"contesto": contesto, "risposta": risposta})

    def correggi_a_fasi(self, contesto: dict, oggetto: str) -> Iterator[dict]:
        return self._flusso("/correggi/flusso",
                            json={"contesto": contesto, "oggetto": oggetto})

    def correggi(self, contesto: dict, oggetto: str) -> dict:
        """L'oggetto riconosciuto era sbagliato: si rifà la ricerca con quello dell'utente."""
        return self._chiedi("POST", "/correggi", ATTESA_LUNGA,
                            json={"contesto": contesto, "oggetto": oggetto})

    def riscontro(self, comune: str, corretta: bool, oggetto: str | None = None,
                  destinazione_attesa: str | None = None, nota: str | None = None,
                  contesto: dict | None = None) -> dict:
        return self._chiedi("POST", "/riscontro", ATTESA_BREVE, json={
            "comune": comune, "corretta": corretta, "oggetto": oggetto,
            "destinazione_attesa": destinazione_attesa, "nota": nota,
            "contesto": contesto or {}})
