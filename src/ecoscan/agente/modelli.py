"""Il modello di visione dietro un'interfaccia.

Due chiamate distinte, con ruoli diversi:

- `riconosci` guarda la foto e descrive l'oggetto. Non sa dove va buttato;
- `scegli` riceve candidati REALI presi dal dizionario comunale e ne indica uno, o nessuno.

La seconda chiamata è ciò che contiene le allucinazioni: il modello non produce un nome
libero, sceglie fra opzioni esistenti (D9). Entrambe usano l'output strutturato di Ollama
(`format` con uno schema JSON), così il backend non deve interpretare della prosa.

`ModelloVisione` è un protocollo: i test usano un modello finto, la valutazione può
confrontare modelli diversi senza toccare il resto dell'agente.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Protocol, Sequence

from ecoscan import configurazione as conf
from ecoscan import prompt as prompt_
from ecoscan.agente.tipi import Candidato, Riconoscimento, Scelta

SCHEMA_RICONOSCIMENTO = {
    "type": "object",
    "properties": {
        "oggetto": {"type": "string"},
        "materiali": {"type": "array", "items": {"type": "string"}},
        "stato": {"type": "string"},
        "componenti": {"type": "array", "items": {"type": "string"}},
        "confidenza": {"type": "number"},
        "note": {"type": "string"},
    },
    "required": ["oggetto", "materiali", "confidenza"],
}

SCHEMA_SCELTA = {
    "type": "object",
    "properties": {
        "numero": {"type": "integer"},
        "motivo": {"type": "string"},
        "chiarimento": {"type": "string"},
    },
    "required": ["numero", "motivo"],
}


class ModelloVisione(Protocol):
    nome: str

    def riconosci(self, immagine: bytes, testo_utente: str | None = None) -> Riconoscimento: ...

    def scegli(self, riconoscimento: Riconoscimento, candidati: Sequence[Candidato],
               testo_utente: str | None = None) -> Scelta: ...


def _elenco(candidati: Sequence[Candidato]) -> str:
    return "\n".join(f"{i}. {c.descrizione()}" for i, c in enumerate(candidati, start=1))


def _descrizione_oggetto(r: Riconoscimento, testo_utente: str | None) -> str:
    righe = [f"Oggetto: {r.oggetto}"]
    if r.materiali:
        righe.append(f"Materiali visibili: {', '.join(r.materiali)}")
    if r.stato:
        righe.append(f"Stato: {r.stato}")
    if r.componenti:
        righe.append(f"Componenti: {', '.join(r.componenti)}")
    if testo_utente:
        righe.append(f"L'utente aggiunge: {testo_utente}")
    return "\n".join(righe)


class ModelloOllama:
    """Gemma 4 via Ollama, con output vincolato a uno schema JSON."""

    def __init__(self, modello: str | None = None, url: str | None = None,
                 temperatura: float = 0.0):
        self.nome = modello or conf.MODELLO_VISIONE
        self.url = url or conf.OLLAMA_CHAT
        self.temperatura = temperatura

    # ---------------------------------------------------------------- chiamate

    def _chiama(self, messaggio: dict, schema: dict) -> dict:
        corpo = json.dumps({"model": self.nome, "messages": [messaggio], "format": schema,
                            "stream": False, "options": {"temperature": self.temperatura}}).encode()
        richiesta = urllib.request.Request(self.url, data=corpo,
                                           headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(richiesta, timeout=600) as risposta:
                contenuto = json.load(risposta)["message"]["content"]
        except urllib.error.URLError as errore:
            raise SystemExit(f"Ollama non raggiungibile su {self.url} ({errore}).\n"
                             f"Avvialo e scarica il modello: ollama pull {self.nome}") from errore
        try:
            return json.loads(contenuto)
        except json.JSONDecodeError as errore:
            raise ValueError(f"il modello non ha restituito JSON valido: {contenuto[:200]!r}") from errore

    # ---------------------------------------------------------------- passaggi

    def riconosci(self, immagine: bytes, testo_utente: str | None = None) -> Riconoscimento:
        istruzioni = prompt_.carica("riconoscimento").testo
        if testo_utente:
            istruzioni += f"\n\nL'utente aggiunge questa informazione: {testo_utente}"
        dati = self._chiama({"role": "user", "content": istruzioni,
                             "images": [base64.b64encode(immagine).decode()]},
                            SCHEMA_RICONOSCIMENTO)
        return Riconoscimento(
            oggetto=(dati.get("oggetto") or "").strip(),
            materiali=[m for m in dati.get("materiali", []) if m],
            stato=(dati.get("stato") or "").strip() or None,
            componenti=[c for c in dati.get("componenti", []) if c],
            confidenza=float(dati.get("confidenza") or 0.0),
            note=(dati.get("note") or "").strip() or None,
        )

    def scegli(self, riconoscimento: Riconoscimento, candidati: Sequence[Candidato],
               testo_utente: str | None = None) -> Scelta:
        if not candidati:
            return Scelta(scheda_id=None, motivo="nessun candidato da valutare")
        contenuto = "\n\n".join([
            prompt_.carica("scelta").testo,
            _descrizione_oggetto(riconoscimento, testo_utente),
            "Voci del dizionario:\n" + _elenco(candidati),
        ])
        dati = self._chiama({"role": "user", "content": contenuto}, SCHEMA_SCELTA)
        numero = int(dati.get("numero") or 0)
        if not 1 <= numero <= len(candidati):
            return Scelta(scheda_id=None, motivo=dati.get("motivo") or "nessuna voce corrisponde")
        return Scelta(scheda_id=candidati[numero - 1].scheda_id,
                      motivo=dati.get("motivo") or "",
                      chiarimento=(dati.get("chiarimento") or "").strip() or None)
