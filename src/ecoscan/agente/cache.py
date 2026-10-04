"""La stessa foto non si guarda due volte.

"""
from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Sequence

from ecoscan import configurazione as conf
from ecoscan.agente.tipi import Candidato, Riconoscimento, Scelta
from ecoscan.osservabilita.tracciamento import impronta

registro = logging.getLogger(__name__)


class ModelloConCache:
    """Un modello di visione che ricorda i riconoscimenti già fatti."""

    def __init__(self, modello, capienza: int | None = None):
        self.modello = modello
        self.capienza = conf.CACHE_RICONOSCIMENTI if capienza is None else capienza
        self._ricordi: OrderedDict[tuple[str, str], Riconoscimento] = OrderedDict()
        self.centri = 0      # quante volte ha risposto dalla memoria
        self.richieste = 0

    @property
    def nome(self) -> str:
        return self.modello.nome

    def __getattr__(self, attributo: str):
        """Tutto ciò che non è riconoscimento o scelta passa al modello vero: `lato_max`,
        `descrivi` per la diagnostica, e qualunque cosa si aggiunga in futuro."""
        return getattr(self.modello, attributo)

    def riconosci(self, immagine: bytes, testo_utente: str | None = None) -> Riconoscimento:
        if self.capienza <= 0:
            return self.modello.riconosci(immagine, testo_utente)

        self.richieste += 1
        chiave = (impronta(immagine), (testo_utente or "").strip().lower())
        if (ricordo := self._ricordi.get(chiave)) is not None:
            self._ricordi.move_to_end(chiave)      # il più usato resta, il più vecchio cade
            self.centri += 1
            registro.info("riconoscimento dalla memoria: %s", ricordo.oggetto)
            return ricordo

        riconoscimento = self.modello.riconosci(immagine, testo_utente)
        self._ricordi[chiave] = riconoscimento
        while len(self._ricordi) > self.capienza:
            self._ricordi.popitem(last=False)
        return riconoscimento

    def scegli(self, riconoscimento: Riconoscimento, candidati: Sequence[Candidato],
               testo_utente: str | None = None) -> Scelta:
        """Mai in cache: dipende dai candidati, che cambiano con l'indice e con le politiche."""
        return self.modello.scegli(riconoscimento, candidati, testo_utente)

    def stato(self) -> dict[str, int | float]:
        """Quanto sta servendo: utile in `/salute` e mentre si sviluppa."""
        return {"ricordi": len(self._ricordi), "capienza": self.capienza,
                "richieste": self.richieste, "centri": self.centri,
                "risparmio": round(100 * self.centri / self.richieste, 1) if self.richieste else 0.0}
