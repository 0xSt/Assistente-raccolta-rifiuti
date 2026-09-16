"""L'agente: dalla foto alla risposta.

Quattro passaggi, nell'ordine deciso in D6, D9 e D10:

1. **riconoscimento** — il modello guarda la foto e descrive l'oggetto (non sa dove va);
2. **recupero** — ricerca ibrida nel comune, prima fra le voci (livello 1), poi fra le
   regole di categoria (livello 2);
3. **scelta vincolata** — il modello sceglie fra candidati reali, oppure dice "nessuno";
4. **risposta** — la destinazione si legge da SQLite, mai dal modello.

Se nessun livello produce una scelta, la risposta è di livello 3: "il comune non dice nulla
su questo oggetto". Non si prendono in prestito le regole di un altro comune (D7).

L'agente non dipende da FastAPI: la valutazione e i test lo chiamano direttamente.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, replace

from ecoscan import prompt as prompt_
from ecoscan.agente.modelli import ModelloVisione
from ecoscan.agente.recupero import candidati as recupera
from ecoscan.agente.recupero import condizioni_in_gioco
from ecoscan.agente.tipi import TIPI_NON_VALIDI, Candidato, Riconoscimento, Risposta, Scelta
from ecoscan.db.indicizza import radice

CONFIDENZA_MINIMA = 0.2   # sotto, il riconoscimento non è affidabile abbastanza per cercare


def _radicalizza(testo: str) -> str:
    """Riduce ogni parola alla radice, come fa la ricerca.

    Serve perché l'utente scrive al plurale e la condizione è al singolare: senza,
    "non utilizzabile" non si riconoscerebbe in "scarpe non utilizzabili".
    """
    return " ".join(radice(p) for p in re.findall(r"[a-z0-9]+", testo.lower()))


def _menzionata(condizione: str, noto: str) -> bool:
    """La condizione compare nel testo, tenendo conto della negazione.

    "unto" NON è menzionata in "non unto": senza questo controllo le due varianti di una
    voce sarebbero indistinguibili proprio quando l'utente è stato più preciso.
    """
    c = _radicalizza(condizione or "")
    testo = _radicalizza(noto or "")
    if not c or c not in testo:
        return False
    if c.startswith("non "):
        return True
    return f"non {c}" not in testo


def _testo_noto(testi: list[str | None]) -> str:
    return " ".join(t for t in testi if t).lower()


def condizione_gia_nota(condizioni: list[str], testi: list[str | None]) -> bool:
    """La condizione è già determinata da ciò che sappiamo?

    Se l'utente ha scritto "cartone della pizza unto", o se il modello ha visto lo stato
    "unto", chiedere "è unto oppure pulito?" fa sembrare l'assistente distratto.
    """
    noto = _testo_noto(testi)
    return bool(noto) and any(_menzionata(c, noto) for c in condizioni)


def domande(riconoscimento: Riconoscimento, testo_utente: str | None = None) -> list[str]:
    """Le domande da porre all'indice: quelle del riconoscimento più le parole dell'utente.

    Le parole dell'utente sono una prova, non un contorno: chi scrive "cartone della pizza
    unto" ha appena detto cosa cercare. Prima venivano passate solo al modello e mai
    all'indice, quindi una descrizione precisa non aiutava il recupero.
    """
    domande_ = list(riconoscimento.formulazioni())
    testo = (testo_utente or "").strip()
    if testo:
        # da sola e unita all'oggetto: "è unto" da solo non basta, "scatola è unto" sì
        for formulazione in (testo, f"{riconoscimento.oggetto} {testo}".strip()):
            if formulazione and formulazione.lower() not in {d.lower() for d in domande_}:
                domande_.append(formulazione)
    return domande_


def scegli_per_condizione(omonimi: list[Candidato],
                          testi: list[str | None]) -> Candidato | None:
    """Fra voci con lo stesso nome, quella la cui condizione l'utente ha dichiarato.

    Non è una scelta da lasciare al modello: se l'utente scrive "è unto", il cartone unto va
    nell'organico e quello pulito nella carta. La differenza fra le due risposte è l'intero
    scopo dell'applicazione, e il modello aveva scelto la variante sbagliata.
    """
    noto = _testo_noto(testi)
    if not noto:
        return None
    migliore, punteggio_migliore = None, 0
    for candidato in omonimi:
        punteggio = sum(1 for c in candidato.condizioni if _menzionata(c, noto))
        if punteggio > punteggio_migliore:
            migliore, punteggio_migliore = candidato, punteggio
    return migliore


def condizioni_del_comune(db: sqlite3.Connection, comune: str) -> list[str]:
    """Tutte le condizioni usate dalle voci di quel comune: unto, pulito, vuoto, usato..."""
    righe = db.execute("""
        SELECT DISTINCT vc.condizione FROM voce_condizione vc
        JOIN voce v ON v.id = vc.voce_id JOIN comune c ON c.id = v.comune_id
        WHERE c.nome = ?""", (comune,)).fetchall()
    return [r[0] for r in righe]


class Agente:
    def __init__(self, db: sqlite3.Connection, qdrant, vettorizzatore, modello: ModelloVisione,
                 k: int = 10):
        self.db, self.qdrant, self.vettorizzatore = db, qdrant, vettorizzatore
        self.modello, self.k = modello, k

    # ------------------------------------------------------------------ passaggi

    def _scegli_nel_livello(self, riconoscimento: Riconoscimento, comune: str, livello: int,
                            testo_utente: str | None) -> tuple[list[Candidato], Scelta]:
        # il testo dell'utente è una formulazione a sé: se scrive "cartone della pizza unto"
        # quella frase trova la voce giusta, mentre il riconoscimento diceva "scatola"
        formulazioni = riconoscimento.formulazioni()
        if testo_utente and testo_utente.strip().lower() not in [f.lower() for f in formulazioni]:
            formulazioni.insert(0, testo_utente.strip())
        trovati = recupera(self.db, self.qdrant, self.vettorizzatore,
                           formulazioni, comune, livello=livello, k=self.k)
        if not trovati:
            return [], Scelta(scheda_id=None, motivo=f"nessun candidato al livello {livello}")
        scelta = self.modello.scegli(riconoscimento, trovati, testo_utente)
        if scelta.tipo_corrispondenza in TIPI_NON_VALIDI:
            # il modello ha indicato una voce ma ha dichiarato che non corrisponde davvero:
            # la politica la scarta, qualunque modello l'abbia prodotta
            return trovati, Scelta(scheda_id=None, tipo_corrispondenza=scelta.tipo_corrispondenza,
                                   motivo=scelta.motivo or f"scartata: {scelta.tipo_corrispondenza}")
        return trovati, scelta

    def _componi(self, scelto: Candidato, riconoscimento: Riconoscimento, scelta: Scelta,
                 comune: str, candidati: list[Candidato], testo_utente: str | None = None,
                 gia_chiesto: bool = False) -> Risposta:
        # Il chiarimento deve riguardare la voce SCELTA: chiedere "utilizzabile o non
        # utilizzabile?" dopo aver scelto "Stivali" confonde, perché la condizione
        # apparteneva a "Scarpe", un'altra voce presente fra i candidati.
        omonimi = [c for c in candidati
                   if c.nome and scelto.nome and c.nome.lower() == scelto.nome.lower()]
        noti = [testo_utente, riconoscimento.stato]

        # Se l'utente ha dichiarato la condizione, la scelta fra omonimi la fa il codice:
        # "è unto" manda il cartone nell'organico, non nella carta, e il modello aveva
        # scelto la variante sbagliata.
        motivo_condizione = ""
        if (per_condizione := scegli_per_condizione(omonimi, noti)) and per_condizione is not scelto:
            scelto = per_condizione
            motivo_condizione = (f"variante scelta in base alla condizione dichiarata: "
                                 f"{', '.join(scelto.condizioni)}")

        condizioni = condizioni_in_gioco(omonimi)
        # non si chiede due volte, e non si chiede ciò che è già stato detto
        zitto = gia_chiesto or condizione_gia_nota(condizioni or scelto.condizioni, noti)
        chiarimento = None if zitto else scelta.chiarimento
        if not zitto and not chiarimento and condizioni:
            chiarimento = ("Per esserne certo devo sapere se l'oggetto è: "
                           + " oppure ".join(condizioni) + "?")
        return Risposta(
            livello_evidenza=scelto.livello, comune=comune, oggetto=riconoscimento.oggetto,
            destinazioni=scelto.destinazioni, polarita=scelto.polarita,
            condizioni=scelto.condizioni, avvertenza=scelto.avvertenza,
            fonte=scelto.fonte, riferimento=scelto.riferimento,
            chiarimento=chiarimento,
            motivo=" · ".join(p for p in (scelta.motivo, motivo_condizione) if p),
            tipo_corrispondenza=scelta.tipo_corrispondenza,
            candidati=candidati, riconoscimento=riconoscimento,
        )

    # ------------------------------------------------------------------ ingresso

    def analizza(self, immagine: bytes, comune: str, testo_utente: str | None = None,
                 contesto: dict | None = None) -> Risposta:
        riconoscimento = self.modello.riconosci(immagine, testo_utente)
        return self.rispondi(riconoscimento, comune, testo_utente, contesto)

    def arricchisci(self, riconoscimento: Riconoscimento, comune: str,
                    testo_utente: str | None) -> Riconoscimento:
        """Porta nel riconoscimento ciò che l'utente ha detto, senza passare dal modello.

        Davanti alla foto di un cartone della pizza con il testo "è unto", il modello ha
        risposto "scatola" con stato vuoto: l'informazione dell'utente era andata persa.
        Qui lo stato viene ricavato confrontando il testo con le condizioni che quel comune
        usa davvero, quindi è un dato del database, non un'interpretazione.
        """
        if not testo_utente or riconoscimento.stato:
            return riconoscimento
        dichiarate = [c for c in condizioni_del_comune(self.db, comune)
                      if _menzionata(c, testo_utente)]
        if not dichiarate:
            return riconoscimento
        return replace(riconoscimento, stato=", ".join(sorted(dichiarate)))

    def rispondi(self, riconoscimento: Riconoscimento, comune: str,
                 testo_utente: str | None = None, contesto: dict | None = None,
                 gia_chiesto: bool = False) -> Risposta:
        """Dal riconoscimento alla risposta. Separato da `analizza` per poter valutare il
        retrieval e la scelta senza rieseguire il modello di visione su ogni foto."""
        riconoscimento = self.arricchisci(riconoscimento, comune, testo_utente)
        base = {"comune": comune, "riconoscimento": riconoscimento,
                "contesto": self._contesto(riconoscimento, comune, testo_utente)}

        if not riconoscimento.riuscito or riconoscimento.confidenza < CONFIDENZA_MINIMA:
            return Risposta(livello_evidenza=3, oggetto=riconoscimento.oggetto or None,
                            motivo="oggetto non riconosciuto con sufficiente sicurezza",
                            chiarimento="Puoi rifare la foto più da vicino, o dirmi di che oggetto si tratta?",
                            **base)

        tutti: list[Candidato] = []
        for livello in (1, 2):
            trovati, scelta = self._scegli_nel_livello(riconoscimento, comune, livello, testo_utente)
            tutti.extend(trovati)
            if scelta.scheda_id is not None:
                scelto = next(c for c in trovati if c.scheda_id == scelta.scheda_id)
                risposta = self._componi(scelto, riconoscimento, scelta, comune, trovati,
                                         testo_utente=testo_utente, gia_chiesto=gia_chiesto)
                # si mostrano i candidati di TUTTI i livelli provati: se la scelta è caduta
                # sul livello 2, vedere cosa era stato scartato al livello 1 spiega il perché
                risposta.candidati = tutti
                risposta.contesto = base["contesto"]
                return risposta

        return Risposta(livello_evidenza=3, oggetto=riconoscimento.oggetto,
                        motivo=f"nessuna regola di {comune} copre questo oggetto",
                        chiarimento=None, candidati=tutti, **base)

    def _contesto(self, riconoscimento: Riconoscimento, comune: str,
                  testo_utente: str | None) -> dict:
        """Il backend resta senza stato: il contesto torna al client, che lo rimanda con la
        risposta al chiarimento."""
        return {"riconoscimento": asdict(riconoscimento), "comune": comune,
                "testo_utente": testo_utente,
                "prompt": [prompt_.carica(n).etichetta for n in ("riconoscimento", "scelta")],
                "modello_visione": self.modello.nome}

    def continua(self, contesto: dict, risposta_utente: str) -> Risposta:
        """Secondo giro dopo un chiarimento: si riparte dal riconoscimento già fatto,
        aggiungendo ciò che l'utente ha detto. Nessuna nuova lettura della foto.

        `gia_chiesto` impedisce di riproporre la stessa domanda: l'utente ha risposto, e
        ripetergliela lo lascerebbe in un giro senza uscita.
        """
        riconoscimento = Riconoscimento(**contesto["riconoscimento"])
        testo = " ".join(filter(None, [contesto.get("testo_utente"), risposta_utente]))
        arricchito = Riconoscimento(**{**contesto["riconoscimento"],
                                       "stato": risposta_utente or riconoscimento.stato})
        return self.rispondi(arricchito, contesto["comune"], testo, gia_chiesto=True)
