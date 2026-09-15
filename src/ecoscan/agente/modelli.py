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
from ecoscan.agente.immagini import prepara
from ecoscan.agente.tipi import Candidato, Riconoscimento, Scelta

SCHEMA_RICONOSCIMENTO = {
    "type": "object",
    "properties": {
        "oggetto": {"type": "string"},
        "sinonimi": {"type": "array", "items": {"type": "string"}},
        "categoria": {"type": "string"},
        "materiali": {"type": "array", "items": {"type": "string"}},
        "stato": {"type": "string"},
        "componenti": {"type": "array", "items": {"type": "string"}},
        "confidenza": {"type": "number", "description": "da 0.0 a 1.0"},
        "note": {"type": "string"},
    },
    # sinonimi e categoria sono OBBLIGATORI: lasciati facoltativi, il modello li omette e
    # la ricerca perde il ponte col vocabolario della fonte
    "required": ["oggetto", "sinonimi", "categoria", "materiali", "confidenza"],
}

SCHEMA_SCELTA = {
    "type": "object",
    "properties": {
        "numero": {"type": "integer"},
        "tipo_corrispondenza": {
            "type": "string",
            "enum": ["stesso_oggetto", "sinonimo", "categoria", "solo_materiale", "nessuna"],
        },
        "motivo": {"type": "string"},
        "chiarimento": {"type": "string"},
    },
    "required": ["numero", "tipo_corrispondenza", "motivo"],
}



class ModelloVisione(Protocol):
    nome: str

    def riconosci(self, immagine: bytes, testo_utente: str | None = None) -> Riconoscimento: ...

    def scegli(self, riconoscimento: Riconoscimento, candidati: Sequence[Candidato],
               testo_utente: str | None = None) -> Scelta: ...


def _chiarimento(valore) -> str | None:
    """Tiene il chiarimento solo se è davvero una domanda.

    Il campo è facoltativo e il modello lo riempie comunque: ha già risposto "0", che
    mostrato all'utente sarebbe incomprensibile.
    """
    testo = (valore or "").strip()
    return testo if len(testo) >= 10 and "?" in testo else None


def _confidenza(valore) -> float:
    """Normalizza la confidenza in 0-1: i modelli rispondono spesso in percentuale."""
    try:
        numero = float(valore)
    except (TypeError, ValueError):
        return 0.0
    if numero > 1.0:
        numero = numero / 100.0
    return max(0.0, min(1.0, numero))


def _elenco(candidati: Sequence[Candidato]) -> str:
    return "\n".join(f"{i}. {c.descrizione()}" for i, c in enumerate(candidati, start=1))


def _descrizione_oggetto(r: Riconoscimento, testo_utente: str | None) -> str:
    """Come l'oggetto viene presentato al modello nella scelta.

    Sinonimi e categoria non sono un di più: senza di essi un nome ambiguo può essere
    reinterpretato. Davanti a "ciabatta" il modello ha risposto "è un tipo di pane" e ha
    scelto una busta per alimenti; con "categoria: calzatura" quella strada è chiusa.
    """
    righe = [f"Oggetto: {r.oggetto}"]
    if r.categoria:
        righe.append(f"Categoria: {r.categoria}")
    if r.sinonimi:
        righe.append(f"Chiamato anche: {', '.join(r.sinonimi)}")
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
                 temperatura: float = 0.0, lato_max: int | None = None):
        self.nome = modello or conf.MODELLO_VISIONE
        self.url = url or conf.OLLAMA_CHAT
        self.temperatura = temperatura
        self.lato_max = lato_max or conf.LATO_MAX_IMMAGINE

    # ---------------------------------------------------------------- chiamate

    def _codifica(self, immagine: bytes) -> str:
        """Ridimensiona e ricodifica prima di inviare: vedi agente/immagini.py."""
        return base64.b64encode(prepara(immagine, self.lato_max)).decode()

    def _chiama(self, messaggio: dict, schema: dict | None = None) -> str:
        """Una richiesta a Ollama. `keep_alive` evita di ricaricare il modello ogni volta."""
        corpo: dict = {"model": self.nome, "messages": [messaggio], "stream": False,
                       "keep_alive": conf.OLLAMA_KEEP_ALIVE,
                       "options": {"temperature": self.temperatura}}
        if schema:
            corpo["format"] = schema
        corpo_codificato = json.dumps(corpo).encode()
        richiesta = urllib.request.Request(self.url, data=corpo_codificato,
                                           headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(richiesta, timeout=900) as risposta:
                return json.load(risposta)["message"]["content"]
        except urllib.error.URLError as errore:
            raise SystemExit(f"Ollama non raggiungibile su {self.url} ({errore}).\n"
                             f"Avvialo e scarica il modello: ollama pull {self.nome}") from errore

    def _chiama_json(self, messaggio: dict, schema: dict) -> dict:
        contenuto = self._chiama(messaggio, schema)
        try:
            return json.loads(contenuto)
        except json.JSONDecodeError as errore:
            raise ValueError(f"il modello non ha restituito JSON valido: {contenuto[:200]!r}") from errore

    def descrivi(self, immagine: bytes, domanda: str | None = None) -> str:
        """Diagnostica: descrizione libera della foto, senza schema e senza istruzioni nostre.

        Serve a distinguere due guasti molto diversi: un modello che vede la foto ma la
        interpreta male, e un modello che la foto non la riceve affatto.
        """
        domanda = domanda or "Descrivi in italiano che cosa vedi in questa immagine."
        return self._chiama({"role": "user", "content": domanda,
                             "images": [self._codifica(immagine)]})

    # ---------------------------------------------------------------- passaggi

    def riconosci(self, immagine: bytes, testo_utente: str | None = None) -> Riconoscimento:
        istruzioni = prompt_.carica("riconoscimento").testo
        if testo_utente:
            istruzioni += f"\n\nL'utente aggiunge questa informazione: {testo_utente}"
        dati = self._chiama_json({"role": "user", "content": istruzioni,
                                  "images": [self._codifica(immagine)]},
                                 SCHEMA_RICONOSCIMENTO)
        return Riconoscimento(
            oggetto=(dati.get("oggetto") or "").strip(),
            sinonimi=[s.strip() for s in dati.get("sinonimi", []) if s and s.strip()],
            categoria=(dati.get("categoria") or "").strip() or None,
            materiali=[m for m in dati.get("materiali", []) if m],
            stato=(dati.get("stato") or "").strip() or None,
            componenti=[c for c in dati.get("componenti", []) if c],
            confidenza=_confidenza(dati.get("confidenza")),
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
        dati = self._chiama_json({"role": "user", "content": contenuto}, SCHEMA_SCELTA)
        numero = int(dati.get("numero") or 0)
        tipo = (dati.get("tipo_corrispondenza") or "").strip()
        motivo = dati.get("motivo") or ""
        if not 1 <= numero <= len(candidati):
            return Scelta(scheda_id=None, tipo_corrispondenza=tipo or "nessuna",
                          motivo=motivo or "nessuna voce corrisponde")
        return Scelta(scheda_id=candidati[numero - 1].scheda_id, tipo_corrispondenza=tipo,
                      motivo=motivo, chiarimento=_chiarimento(dati.get("chiarimento")))
