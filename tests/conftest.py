"""Strumenti condivisi fra i test."""
import numpy as np
import pytest


class VettorizzatoreFinto:
    """Vettori deterministici dal testo: nessuna rete, risultati riproducibili.

    Sta qui e non in un singolo file di test perché lo usano sia i test dell'indice sia
    quelli dell'agente.
    """

    nome = "finto"
    dimensione = 8

    def __init__(self):
        self.chiamate = 0

    def vettorizza(self, testi, come="documento"):
        self.chiamate += len(testi)
        vettori = []
        for t in testi:
            nudo = (t.replace("task: search result | query: ", "")
                     .replace("title: none | text: ", "").lower())
            generatore = np.random.default_rng(abs(hash(nudo)) % 2**32)
            vettori.append(generatore.normal(size=self.dimensione).tolist())
        return vettori


@pytest.fixture
def vettorizzatore_finto():
    return VettorizzatoreFinto()
