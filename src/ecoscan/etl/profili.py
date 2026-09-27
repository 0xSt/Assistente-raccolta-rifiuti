"""Che cosa cambia da un comune all'altro: tutto qui dentro, e nient'altro.

Il motore di normalizzazione (`trasforma.py`) e quello delle regole (`regole.py`) non
nominano mai Napoli o Torino: ricevono un `Profilo` e lavorano su quello. Aggiungere un
terzo comune significa quindi scrivere **dati in questo file**, non codice altrove — ed è
la proprietà che rende credibile il requisito di estendibilità.

Prima della riorganizzazione questa configurazione stava in tre posti: due moduli da
ventidue e quarantacinque righe (`transform_napoli.py`, `transform_torino.py`) che
contenevano solo un'istanza a testa, e due dizionari sepolti a metà di
`normalizza_regole.py` — dove, non essendoci un profilo, erano accompagnati da due
funzioni quasi identiche invece che da una sola parametrizzata.

`Profilo` sta qui e non nel motore perché è una struttura di configurazione: tenendola
qui, le dipendenze vanno in una direzione sola — i profili non sanno nulla del motore, il
motore legge i profili.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profilo:
    """Regole specifiche di una fonte. I default valgono per entrambi i comuni."""

    comune: str
    nomi_da_scartare: frozenset[str] = frozenset()
    condizioni_extra: tuple[tuple[str, str], ...] = ()      # (nome canonico, pattern) inline
    locuzioni_extra: tuple[tuple[str, str], ...] = ()       # (pattern, nome canonico)
    invarianti_extra: frozenset[str] = frozenset()
    locuzioni_fisse: tuple[str, ...] = ()                   # espressioni da non separare mai
    # Provenienza della singola voce: senza di essa una risposta di livello 1 non può
    # mostrare all'utente da dove viene la regola (D129)
    fonte: str = ""
    modello_riferimento: str = ""                           # formattato con il record grezzo

    def riferimento(self, record: dict) -> str | None:
        if not self.modello_riferimento:
            return None
        try:
            testo = self.modello_riferimento.format_map(record)
        except KeyError:                                     # il grezzo non porta il campo
            return None
        return testo or None


# --------------------------------------------------------------------------- Napoli

# Regole ricavate dalle 584 voci del dizionario ASIA (estrazione 12/09/2026).
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


# --------------------------------------------------------------------------- Torino

# Regole ricavate dalle 324 voci del Rifiutologo AMIAT 2025. Differenze rispetto a Napoli:
# le condizioni stanno quasi sempre fra parentesi e non dentro il nome; "usa e getta" e'
# una CONDIZIONE e non una locuzione fissa, perche' distingue due destinazioni; compaiono
# formule di ammissibilita' assenti a Napoli ("solo se...", "non infiammabili").
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
    fonte="amiat_rifiutologo_2025",
    # il Rifiutologo è un PDF: il riferimento è la pagina, come per le regole di categoria
    modello_riferimento="Rifiutologo AMIAT 2025, pagina {pagina}",
)


# ------------------------------------------------------- regole di categoria: le sorgenti
#
# Nome della scheda o frazione nella fonte -> destinazione usata nelle voci del comune.
# None significa: sezione senza una destinazione propria (indice, pagina di servizio).


@dataclass(frozen=True)
class SorgenteRegole:
    """Da dove vengono le regole di categoria di un comune, e dove si agganciano.

    Ha `fonte` e `modello_riferimento` propri perche' non coincidono con quelli delle voci:
    a Napoli il dizionario e le pagine-frazione sono due sezioni diverse dello stesso sito.
    """

    comune: str
    destinazioni: dict[str, str | None]
    fonte: str
    modello_riferimento: str

    def riferimento(self, scheda: dict) -> str:
        return self.modello_riferimento.format_map(scheda)


DESTINAZIONE_NAPOLI = {
    "Umido/Organico": "Organico",
    "Plastica e Metalli": "Plastica e Metalli",
    "Carta e Cartone": "Carta e Cartoncino",   # le voci usano "Cartoncino", la frazione "Cartone"
    "Vetro": "Vetro",
    "Non riciclabile": "Non Riciclabile",
    "Altri servizi": None,                      # pagina di raccordo, non un contenitore
}

DESTINAZIONE_TORINO = {
    "Rifiuto non recuperabile": "rifiuto_non_recuperabile",
    "Carta e cartone": "carta_e_cartone",
    "Organico": "organico",
    "Imballaggi in plastica": "imballaggi_plastica",
    "Vetro e imballaggi in metallo": "vetro_e_imballaggi_metallo",
    "Pile": "pile",
    "Abiti": "abiti",
    "Farmaci": "farmaci",
    "Oli esausti": "olio_esausto",
    "Rifiuti ingombranti": "rifiuti_ingombranti",
}


# I profili in un elenco solo, nell'ordine in cui la pipeline li lavora.
PROFILI = {"Napoli": PROFILO_NAPOLI, "Torino": PROFILO_TORINO}
DESTINAZIONI_REGOLE = {"Napoli": DESTINAZIONE_NAPOLI, "Torino": DESTINAZIONE_TORINO}

SORGENTI_REGOLE = {
    "Napoli": SorgenteRegole("Napoli", DESTINAZIONE_NAPOLI, "asia_napoli_frazioni", "{url}"),
    "Torino": SorgenteRegole("Torino", DESTINAZIONE_TORINO, "amiat_rifiutologo_2025",
                             "Rifiutologo AMIAT 2025, pagina {pagina}"),
}
