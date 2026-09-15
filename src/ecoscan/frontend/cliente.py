"""Il frontend parla SOLO con il backend, mai con Qdrant, Ollama o il database.

Questo modulo è l'unico punto di contatto. Tenerlo separato dall'interfaccia ha due
vantaggi: si può provare senza avviare Streamlit, e se un giorno il frontend cambia
tecnologia il contratto resta qui.
"""
from __future__ import annotations

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

    # ------------------------------------------------------------------ rotte

    def comuni(self) -> list[dict]:
        return self._chiedi("GET", "/comuni", ATTESA_BREVE)

    def salute(self) -> dict:
        return self._chiedi("GET", "/salute", ATTESA_BREVE)

    def analizza(self, foto: bytes, nome_file: str, comune: str, testo: str | None = None) -> dict:
        dati = {"comune": comune}
        if testo:
            dati["testo"] = testo
        return self._chiedi("POST", "/analizza", ATTESA_LUNGA, data=dati,
                            files={"foto": (nome_file, foto)})

    def continua(self, contesto: dict, risposta: str) -> dict:
        return self._chiedi("POST", "/continua", ATTESA_LUNGA,
                            json={"contesto": contesto, "risposta": risposta})

    def riscontro(self, comune: str, corretta: bool, oggetto: str | None = None,
                  destinazione_attesa: str | None = None, nota: str | None = None,
                  contesto: dict | None = None) -> dict:
        return self._chiedi("POST", "/riscontro", ATTESA_BREVE, json={
            "comune": comune, "corretta": corretta, "oggetto": oggetto,
            "destinazione_attesa": destinazione_attesa, "nota": nota,
            "contesto": contesto or {}})
