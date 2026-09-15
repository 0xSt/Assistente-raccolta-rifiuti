"""Dal testo ai candidati, arricchiti con i dati del relazionale.

La ricerca trova delle schede; qui diventano `Candidato`, cioè oggetti che portano con sé
destinazioni, condizioni, avvertenza e fonte. Quei dati arrivano **sempre da SQLite**, mai
dal payload di Qdrant (D61): l'indice dice quali schede somigliano alla domanda, il
relazionale dice cosa significano.

La cascata dei livelli di evidenza (D10) è qui: prima le voci di dizionario (livello 1),
poi le regole di categoria (livello 2). Non si mescolano in un'unica classifica, perché
significano cose diverse: una voce dice dove va *quell'oggetto*, una regola dice cosa entra
in *quel contenitore*.
"""
from __future__ import annotations

import sqlite3
from typing import Sequence

from ecoscan.agente.tipi import Candidato
from ecoscan.db.indicizza import cerca as cerca_lessicale
from ecoscan.db.vettorizza import cerca_semantica, fondi_rrf


def _dettagli(db: sqlite3.Connection, scheda_id: int) -> dict:
    riga = db.execute("""
        SELECT s.livello, s.testo, v.nome, v.avvertenza,
               (SELECT group_concat(d.nome, '|') FROM voce_destinazione vd
                  JOIN destinazione d ON d.id = vd.destinazione_id
                 WHERE vd.voce_id = s.voce_id ORDER BY vd.ordine),
               (SELECT group_concat(vc.condizione, '|') FROM voce_condizione vc
                 WHERE vc.voce_id = s.voce_id),
               r.polarita, r.fonte, r.riferimento, r.dettaglio,
               (SELECT d.nome FROM destinazione d WHERE d.id = r.destinazione_id)
        FROM scheda s
        LEFT JOIN voce v ON v.id = s.voce_id
        LEFT JOIN regola r ON r.id = s.regola_id
        WHERE s.id = ?""", (scheda_id,)).fetchone()
    if not riga:
        return {}
    livello, testo, nome, avvertenza, dest_voce, condizioni, polarita, fonte, rif, dettaglio, dest_regola = riga
    return {
        "livello": livello, "testo": testo, "nome": nome,
        "condizioni": condizioni.split("|") if condizioni else [],
        "destinazioni": dest_voce.split("|") if dest_voce else ([dest_regola] if dest_regola else []),
        "polarita": polarita, "avvertenza": avvertenza or dettaglio,
        "fonte": fonte, "riferimento": rif,
    }


def arricchisci(db: sqlite3.Connection, risultati: Sequence[dict]) -> list[Candidato]:
    candidati = []
    for r in risultati:
        dettagli = _dettagli(db, r["scheda_id"])
        if not dettagli:
            continue
        candidati.append(Candidato(scheda_id=r["scheda_id"], posizioni=r.get("posizioni", {}),
                                   **dettagli))
    return candidati


def candidati(db: sqlite3.Connection, qdrant, vettorizzatore, query: str | Sequence[str],
              comune: str, livello: int, k: int = 8) -> list[Candidato]:
    """Ricerca ibrida su un solo livello di evidenza, dentro un solo comune.

    `query` può essere una domanda sola o più formulazioni della stessa: in quel caso ogni
    formulazione produce due classifiche (lessicale e semantica) e tutte vengono fuse con
    RRF. Una voce trovata da più formulazioni sale, il che è esattamente ciò che si vuole.
    """
    domande = [query] if isinstance(query, str) else list(query)
    classifiche: dict[str, list[dict]] = {}
    for n, domanda in enumerate(d for d in domande if d and d.strip()):
        classifiche[f"lessicale{n}"] = cerca_lessicale(db, domanda, comune, livello=livello, k=k)
        classifiche[f"semantica{n}"] = cerca_semantica(qdrant, domanda, comune, vettorizzatore,
                                                       livello=livello, k=k)
    if not classifiche:
        return []
    return arricchisci(db, _fondi_garantendo_i_primi(classifiche, k))


PRIMI_GARANTITI = 2   # quanti risultati di ciascuna formulazione entrano comunque


def _fondi_garantendo_i_primi(classifiche: dict[str, list[dict]], k: int,
                              garantiti: int = PRIMI_GARANTITI) -> list[dict]:
    """Fonde con RRF, ma garantisce i primi risultati di OGNI formulazione.

    Con più formulazioni la fusione premia chi compare in molte classifiche, e una scheda
    trovata al primo posto da una sola formulazione può restare fuori. È successo con
    "calzatura", che trova "Scarpe" al primo posto: fusa con le altre sette classifiche,
    la voce giusta spariva dai candidati mostrati al modello.
    """
    fusi = fondi_rrf(classifiche, k=k)
    presenti = {r["scheda_id"] for r in fusi}
    for metodo, risultati in classifiche.items():
        for posizione, risultato in enumerate(risultati[:garantiti], start=1):
            if risultato["scheda_id"] not in presenti:
                aggiunto = dict(risultato)
                aggiunto["posizioni"] = {metodo: posizione}
                fusi.append(aggiunto)
                presenti.add(aggiunto["scheda_id"])
    return fusi


def condizioni_in_gioco(candidati_: Sequence[Candidato]) -> list[str]:
    """Condizioni che distinguono candidati con lo STESSO nome ma destinazioni diverse.

    È il segnale che serve una domanda all'utente invece di una risposta: "Capsule del caffè
    in plastica" *con residuo* e *senza residuo* vanno in contenitori diversi, e dalla foto
    la differenza spesso non si vede.
    """
    per_nome: dict[str, list[Candidato]] = {}
    for c in candidati_:
        if c.nome:
            per_nome.setdefault(c.nome.lower(), []).append(c)
    condizioni: list[str] = []
    for gruppo in per_nome.values():
        destinazioni = {tuple(c.destinazioni) for c in gruppo}
        if len(gruppo) > 1 and len(destinazioni) > 1:
            for c in gruppo:
                condizioni.extend(x for x in c.condizioni if x not in condizioni)
    return condizioni
