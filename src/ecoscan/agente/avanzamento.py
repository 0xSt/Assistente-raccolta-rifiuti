"""Le fasi dell'agente, annunciate mentre accadono.

Su CPU una risposta richiede minuti. Uno spinner fermo per tutto quel tempo non dice se il
sistema sta lavorando, a che punto è, né — soprattutto — **cosa ha visto il modello**: se il
riconoscimento è sbagliato, l'utente lo scopre solo alla fine, dopo aver aspettato invano.

L'agente non sa nulla di HTTP né di Streamlit: chiama `fase(...)` e chi ascolta decide cosa
farne. Il predefinito non fa nulla, quindi i test e la valutazione restano identici.

Le fasi, in ordine:

- `riconoscimento` — il modello sta guardando la foto;
- `riconosciuto` — cosa ha visto, con i dati del riconoscimento: è la fase che permette di
  accorgersi subito dell'errore;
- `recupero` / `recuperato` — ricerca nel comune a un livello di evidenza, con le domande
  poste e quanti documenti sono tornati;
- `scelta` — il modello sta scegliendo fra i documenti trovati.

La fase finale (`risposta`) la aggiunge chi trasporta gli eventi, perché è la risposta
stessa e l'agente la restituisce già.
"""
from __future__ import annotations

from typing import Any, Callable, Protocol


class Avanzamento(Protocol):
    """Chi ascolta le fasi. Un protocollo, non una classe da ereditare: l'agente accetta
    qualunque oggetto con questo metodo."""

    def fase(self, nome: str, **dati: Any) -> None: ...


class SenzaAvanzamento:
    """Nessuno sta guardando: è il predefinito di tutti i metodi dell'agente."""

    def fase(self, nome: str, **dati: Any) -> None:
        pass


class Ascoltatore:
    """Passa ogni fase a una funzione, inghiottendone gli errori.

    Un guasto di chi ascolta (una coda chiusa, un client che se n'è andato) non deve far
    fallire una risposta già a metà: l'avanzamento è un di più, la risposta è il compito.
    """

    def __init__(self, funzione: Callable[[dict], None]):
        self.funzione = funzione

    def fase(self, nome: str, **dati: Any) -> None:
        try:
            self.funzione({"fase": nome, **dati})
        except Exception:                      # il client può essersene andato
            pass


SENZA_AVANZAMENTO = SenzaAvanzamento()
