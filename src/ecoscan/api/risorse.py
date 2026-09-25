"""Risorse condivise dalle rotte: database, Qdrant, modelli, agente.

Sono costruite una volta all'avvio e riusate: aprire una connessione per richiesta
sprecherebbe tempo, e soprattutto il modello verrebbe ricaricato di continuo.

Il database si apre in **sola lettura**: il backend non scrive mai nei dati, che si
rigenerano con i comandi dell'ETL. È un vincolo dichiarato nel codice, non una promessa.

`Risorse` è sostituibile: i test ne costruiscono una versione con un database in memoria e
un modello finto, senza alzare nulla.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ecoscan import procedure as procedure_
from ecoscan.agente.agente import Agente
from ecoscan.agente.cache import ModelloConCache
from ecoscan.agente.recupero import Recupero, RecuperoQdrant
from ecoscan.agente.modelli import ModelloOllama, ModelloVisione
from ecoscan.db.vettorizza import COLLEZIONE, DB, VettorizzatoreOllama, apri_qdrant
from ecoscan.osservabilita.tracciamento import Tracciatore


def apri_database_in_lettura(percorso: Path) -> sqlite3.Connection:
    if not percorso.is_file():
        raise SystemExit(f"Database non trovato: {percorso}\nLancia prima: uv run ecoscan-carica")
    # uri=True permette il modo read-only: un tentativo di scrittura fallisce invece di riuscire
    return sqlite3.connect(f"file:{percorso}?mode=ro", uri=True, check_same_thread=False)


@dataclass
class Risorse:
    db: sqlite3.Connection
    qdrant: object
    vettorizzatore: object
    recupero: Recupero
    modello: ModelloVisione
    agente: Agente

    @classmethod
    def costruisci(cls, percorso_db: Path | None = None, k: int = 8) -> Risorse:
        db = apri_database_in_lettura(percorso_db or DB)
        qdrant = apri_qdrant()
        vettorizzatore = VettorizzatoreOllama()
        # la cache sta fuori dal modello e dentro le risorse: l'agente non sa che esiste
        modello = ModelloConCache(ModelloOllama())
        recupero = RecuperoQdrant(qdrant, vettorizzatore)
        return cls(db, qdrant, vettorizzatore, recupero, modello,
                   Agente(recupero, modello, k=k, tracciatore=Tracciatore()))

    def chiudi(self) -> None:
        self.db.close()
        chiudi = getattr(self.qdrant, "close", None)
        if chiudi:
            chiudi()

    # ------------------------------------------------------------------ stato

    def comuni(self) -> list[dict]:
        righe = self.db.execute("""
            SELECT c.nome, c.gestore,
                   (SELECT count(*) FROM voce v WHERE v.comune_id = c.id),
                   (SELECT count(*) FROM regola r JOIN destinazione d ON d.id = r.destinazione_id
                     WHERE d.comune_id = c.id)
            FROM comune c ORDER BY c.nome""").fetchall()
        return [{"nome": n, "gestore": g, "voci": v, "regole": r} for n, g, v, r in righe]

    def destinazioni(self, comune: str) -> list[dict]:
        """I contenitori di un comune, con l'etichetta con cui vanno scritti all'utente."""
        righe = self.db.execute("""
            SELECT d.nome, coalesce(d.etichetta, d.nome), d.canale, d.colore, d.note
            FROM destinazione d JOIN comune c ON c.id = d.comune_id
            WHERE c.nome = ? ORDER BY d.canale, d.nome""", (comune,)).fetchall()
        return [{"nome": n, "etichetta": e, "canale": ca, "colore": co, "note": no}
                for n, e, ca, co, no in righe]

    def canali(self, comune: str) -> dict[str, str]:
        """Nome della destinazione -> canale con cui ci si conferisce.

        È la traduzione da "dove" a "come": `Isola Ecologica Estesa` -> `centro_raccolta`,
        e da lì si trova la procedura. Il canale è già nei dati, non va indovinato.
        """
        return {d["nome"]: d["canale"] for d in self.destinazioni(comune)}

    def procedure(self, comune: str, destinazioni: list[str]) -> list[procedure_.Procedura]:
        """Come si conferisce alle destinazioni di una risposta, dalla più comoda in giù.

        Si passa la coppia (canale, destinazione) e non il solo canale: un canale può
        raccogliere contenitori che si usano in modi diversi — farmaci, pile, abiti e olio
        stanno tutti in `contenitore_dedicato` — e senza la destinazione la procedura
        finisce per spiegarli tutti insieme.
        """
        canali = self.canali(comune)
        return procedure_.per_canali(
            comune, [(canali[d], d) for d in destinazioni if d in canali])

    def salute(self) -> dict:
        dettagli: dict[str, str] = {}
        try:
            self.db.execute("SELECT 1 FROM voce LIMIT 1").fetchone()
            database = True
        except Exception as errore:                      # database assente o schema incompleto
            database, dettagli["database"] = False, str(errore)

        try:
            schede = self.qdrant.count(COLLEZIONE).count
            qdrant_ok = True
        except Exception as errore:                      # server spento o collezione mancante
            schede, qdrant_ok, dettagli["qdrant"] = None, False, str(errore)

        try:
            self.vettorizzatore.vettorizza(["prova"], "query")
            ollama = True
        except Exception as errore:                      # Ollama spento o modello non scaricato
            ollama, dettagli["ollama"] = False, str(errore)

        tutto = database and qdrant_ok and ollama
        return {"stato": "pronto" if tutto else "degradato", "database": database,
                "qdrant": qdrant_ok, "ollama": ollama, "schede_indicizzate": schede,
                "modello_visione": self.modello.nome, "dettagli": dettagli}
