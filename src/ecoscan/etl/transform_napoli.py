"""Profilo di Napoli per il motore del Transform.

Regole ricavate dalle 584 voci del dizionario ASIA (estrazione 12/09/2026).
"""
from __future__ import annotations

import functools

from ecoscan.etl.transform_comune import Profilo, trasforma_voce as _trasforma

PROFILO_NAPOLI = Profilo(
    comune="Napoli",
    # voce di prova pubblicata per errore sul sito, con tre destinazioni reali
    nomi_da_scartare=frozenset({"test di esempio"}),
    invarianti_extra=frozenset({"C/PAP", "TE/OF"}),
    # "Lametta usa e getta" è un oggetto solo: a Napoli non distingue destinazioni
    locuzioni_fisse=("usa e getta",),
    fonte="asia_napoli_dove_lo_butto",
    modello_riferimento="{url}",          # ogni voce del dizionario ha la sua pagina
)

trasforma_voce = functools.partial(_trasforma, profilo=PROFILO_NAPOLI)
