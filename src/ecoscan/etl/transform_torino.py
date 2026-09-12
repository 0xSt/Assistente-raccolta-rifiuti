"""Profilo di Torino per il motore del Transform.

Regole ricavate dalle 324 voci del Rifiutologo AMIAT 2025. Differenze rispetto a Napoli:

- le condizioni stanno quasi sempre tra parentesi, non dentro il nome;
- "usa e getta" è una CONDIZIONE (distingue due destinazioni), non una locuzione fissa:
  "Piatti in plastica usa e getta" -> imballaggi in plastica,
  "Piatti in plastica dura riutilizzabili" -> rifiuto non recuperabile;
- compaiono formule di ammissibilità assenti a Napoli ("solo se...", "non infiammabili").
"""
from __future__ import annotations

import functools

from ecoscan.etl.transform_comune import Profilo, trasforma_voce as _trasforma

PROFILO_TORINO = Profilo(
    comune="Torino",
    condizioni_extra=(
        ("usa e getta", r"usa e getta"),
        ("riutilizzabile", r"riutilizzabil[ei]"),
        ("bagnato", r"bagnat[oaie]"),
        ("infiammabile", r"infiammabil[ei]"),
        ("esausto", r"esaust[oaie]"),
    ),
    locuzioni_extra=(
        # ammissibilità condizionata, tipica del Rifiutologo
        (r"solo se certificato compostabile", "solo se compostabile certificato"),
        (r"solo componenti in carta", "solo le componenti in carta"),
        (r"senza copertina plastificata", "senza copertina plastificata"),
        (r"non adibite a contenere i farmaci", "non ha contenuto farmaci"),
        (r"solo da utenze domestiche", "utenza domestica"),
        (r"senza mozzicone", "senza mozzicone"),
        (r"senza cerchione", "senza cerchione"),
        (r"grandi quantitativi", "grandi quantità"),
        (r"(in )?piccole quantit[aà] (pr[eo]venienti )?da lavori domestici", "piccole quantità da lavori domestici"),
        (r"con residui( di caff[eè])?", "con residuo"),
    ),
    invarianti_extra=frozenset({"CD", "DVD", "Blue-ray", "USB", "RAEE", "Natale", "Tetra", "Pak"}),
)

trasforma_voce = functools.partial(_trasforma, profilo=PROFILO_TORINO)
