"""Test della cache dei riconoscimenti.

Quello che conta non è che la cache sia veloce — qui i modelli sono finti — ma che sia
**trasparente**: stesse risposte, stessa interfaccia, e il modello vero chiamato solo
quando serve davvero.
"""
import pytest

from ecoscan.agente.cache import ModelloConCache
from ecoscan.agente.tipi import Riconoscimento

FOTO = b"\x89PNG-una-foto"
ALTRA = b"\x89PNG-un-altra"


class ModelloContato:
    """Risponde in modo diverso a ogni chiamata: così un ricordo servito si riconosce."""

    nome = "contato"
    lato_max = 512

    def __init__(self):
        self.chiamate = 0

    def riconosci(self, immagine, testo_utente=None):
        self.chiamate += 1
        return Riconoscimento(oggetto=f"oggetto {self.chiamate}", confidenza=0.9)

    def scegli(self, riconoscimento, candidati, testo_utente=None):
        self.chiamate += 1
        return "una scelta"

    def descrivi(self, immagine):
        return "una descrizione"


def test_la_stessa_foto_non_si_guarda_due_volte():
    modello = ModelloContato()
    cache = ModelloConCache(modello, capienza=10)
    primo = cache.riconosci(FOTO)
    secondo = cache.riconosci(FOTO)
    assert primo == secondo
    assert modello.chiamate == 1
    assert cache.stato()["centri"] == 1


def test_foto_diverse_sono_riconoscimenti_diversi():
    modello = ModelloContato()
    cache = ModelloConCache(modello, capienza=10)
    assert cache.riconosci(FOTO) != cache.riconosci(ALTRA)
    assert modello.chiamate == 2


def test_il_testo_dell_utente_fa_parte_della_chiave():
    """Il prompt riceve anche il testo: stessa foto con "è vuota" può dare un altro
    riconoscimento, quindi non è lo stesso ricordo."""
    modello = ModelloContato()
    cache = ModelloConCache(modello, capienza=10)
    cache.riconosci(FOTO, "è vuota")
    cache.riconosci(FOTO, "è unta")
    assert modello.chiamate == 2
    cache.riconosci(FOTO, "  È VUOTA ")      # spazi e maiuscole non sono una domanda nuova
    assert modello.chiamate == 2


def test_la_scelta_non_si_mette_mai_in_cache():
    """Dipende dai candidati, che cambiano con l'indice: metterla in cache renderebbe
    invisibile proprio ciò che stiamo misurando."""
    modello = ModelloContato()
    cache = ModelloConCache(modello, capienza=10)
    riconoscimento = Riconoscimento(oggetto="x", confidenza=1.0)
    cache.scegli(riconoscimento, [])
    cache.scegli(riconoscimento, [])
    assert modello.chiamate == 2


def test_la_memoria_si_svuota_dalla_voce_piu_vecchia():
    modello = ModelloContato()
    cache = ModelloConCache(modello, capienza=2)
    cache.riconosci(b"a")
    cache.riconosci(b"b")
    cache.riconosci(b"c")                    # "a" esce
    assert cache.stato()["ricordi"] == 2
    cache.riconosci(b"a")
    assert modello.chiamate == 4


def test_capienza_zero_spegne_la_cache():
    modello = ModelloContato()
    cache = ModelloConCache(modello, capienza=0)
    cache.riconosci(FOTO)
    cache.riconosci(FOTO)
    assert modello.chiamate == 2


@pytest.mark.parametrize("attributo, atteso", [("nome", "contato"), ("lato_max", 512)])
def test_tutto_il_resto_passa_al_modello_vero(attributo, atteso):
    """È un decoratore, non un sostituto: l'agente non deve accorgersi che esiste."""
    cache = ModelloConCache(ModelloContato())
    assert getattr(cache, attributo) == atteso
    assert cache.descrivi(FOTO) == "una descrizione"


def test_lo_stato_dice_quanto_sta_servendo():
    cache = ModelloConCache(ModelloContato(), capienza=10)
    cache.riconosci(FOTO)
    cache.riconosci(FOTO)
    stato = cache.stato()
    assert stato["richieste"] == 2 and stato["centri"] == 1
    assert stato["risparmio"] == 50.0
