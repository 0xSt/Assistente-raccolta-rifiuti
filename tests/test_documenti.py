"""Test dei documenti da indicizzare.

Sostituiscono le vecchie schede, che erano frammenti di due o tre parole in italiano storto.
Qui si verifica che il testo generato sia leggibile e che dica il vero: l'embedding lavora
su quel testo, e una frase sbagliata è un errore che nessun metodo di ricerca può rimediare.
"""
import sqlite3

import pytest

from ecoscan.db.carica import carica
from ecoscan.db.documenti import (
    Variante, costruisci, documenti_destinazione, documenti_oggetto, documenti_regola,
    frase_varianti, leggibile, unisci_varianti,
)
from ecoscan.db.documenti import testo_oggetto as componi_oggetto
from ecoscan.db.documenti import testo_regola as componi_regola
from tests.conftest import DESTINAZIONI, REGOLE, VOCI


# ------------------------------------------------------------------ frasi

def test_una_sola_destinazione_da_una_frase_semplice():
    assert frase_varianti([Variante([], ["Organico"])]) == "Va in Organico."


def test_le_varianti_diventano_una_frase_con_le_condizioni():
    frase = frase_varianti([Variante(["pulito"], ["Carta e Cartoncino"]),
                            Variante(["unto"], ["Organico"])])
    assert frase == "Se è pulito va in Carta e Cartoncino; se è unto va in Organico."


def test_la_negazione_si_legge_in_italiano():
    """"se è non utilizzabile" non è italiano."""
    frase = frase_varianti([Variante(["non utilizzabile"], ["Non Riciclabile"]),
                            Variante(["utilizzabile"], ["Contenitore Abiti Usati"])])
    assert frase.startswith("Se non è utilizzabile va in Non Riciclabile")


def test_le_clausole_di_ammissibilita_non_diventano_aggettivi():
    """"se è solo se compostabile certificato e sporco" era la frase prodotta prima."""
    frase = frase_varianti([Variante(["pulito"], ["carta"]),
                            Variante(["solo se compostabile certificato", "sporco"], ["organico"])])
    assert "se è sporco va in organico, ma solo se compostabile certificato" in frase


def test_le_quantita_diventano_clausole():
    frase = frase_varianti([Variante(["piccole quantità da lavori domestici"], ["centro"])])
    assert frase == "Di norma va in centro, ma solo in piccole quantità da lavori domestici."


def test_varianti_con_la_stessa_destinazione_non_si_ripetono():
    """"Di norma va in Organico; se è spento va in Organico" è rumore."""
    assert frase_varianti([Variante([], ["Organico"]),
                           Variante(["spento"], ["Organico"])]) == "Va in Organico."


def test_i_nomi_tecnici_si_leggono_come_parole():
    """Il modello di embedding lavora sul linguaggio, non sui nostri identificatori."""
    assert leggibile("carta_e_cartone") == "carta e cartone"
    assert "carta e cartone" in frase_varianti([Variante([], ["carta_e_cartone"])])


def test_le_varianti_indistinguibili_si_uniscono():
    """"Simbolo GL o GLS" esiste tre volte, per i codici 70, 71 e 72, tutte nel vetro."""
    varianti = [Variante([], ["Vetro"], voce_id=1, codice_materiale="70"),
                Variante([], ["Vetro"], voce_id=2, codice_materiale="71"),
                Variante(["rotto"], ["Vetro"], voce_id=3)]
    assert len(unisci_varianti(varianti)) == 2


def test_il_testo_dell_oggetto_contiene_alias_e_codici():
    testo = componi_oggetto("Simbolo PAP", [Variante([], ["Carta"])],
                          alias=["cartoncino"], codici=["20", "21"])
    assert "Chiamato anche: cartoncino" in testo
    assert "Codici del materiale sull'imballaggio: 20, 21" in testo


def test_la_polarita_sta_dentro_la_frase_della_regola():
    """L'embedding non conosce il nostro campo `polarita`: se il "non" non è nel testo,
    la regola di esclusione viene cercata come se fosse un'ammissione."""
    ammesso = componi_regola("carta_e_cartone", "ammesso", "Giornali e riviste", None)
    escluso = componi_regola("carta_e_cartone", "escluso", "carta con residui di cibo", None)
    assert ammesso == "Nel contenitore carta e cartone va: Giornali e riviste."
    assert "NON va: carta con residui di cibo" in escluso


# ------------------------------------------------------------------ costruzione

def test_un_documento_per_oggetto_non_per_variante(db):
    documenti = documenti_oggetto(db)
    capsule = [d for d in documenti if d.nome == "Capsule del caffè"]
    assert len(capsule) == 1
    assert len(capsule[0].varianti) == 2
    assert "con residuo" in capsule[0].testo and "senza residuo" in capsule[0].testo


def test_il_payload_porta_le_varianti_strutturate(db):
    capsula = next(d for d in documenti_oggetto(db) if d.nome == "Capsule del caffè")
    payload = capsula.payload()
    condizioni = {v["condizione"] for v in payload["varianti"]}
    assert condizioni == {"con residuo", "senza residuo"}
    assert all(v["destinazioni"] for v in payload["varianti"])


def test_le_regole_restano_corte_e_separate(db):
    """Un testo lungo che mescola ammessi ed esclusi produce un embedding medio che non
    somiglia a nulla: le regole si cercano una per una."""
    regole = documenti_regola(db)
    assert regole and all(len(d.testo) < 200 for d in regole)
    assert {d.livello for d in regole} == {2}


def test_il_documento_per_destinazione_non_si_indicizza(db):
    """Serve a spiegare la risposta di livello 2, non a essere cercato."""
    destinazioni = documenti_destinazione(db)
    assert destinazioni and all(not d.indicizzabile for d in destinazioni)
    carta = next(d for d in destinazioni if d.nome == "carta_e_cartone")
    assert "Ci vanno" in carta.testo and "NON ci vanno" in carta.testo


def test_ogni_documento_ha_comune_e_testo(db):
    for d in costruisci(db):
        assert d.comune and d.testo and d.tipo and d.id


def test_la_contraddizione_della_fonte_viene_dichiarata():
    """A Napoli "Pantofole di stoffa" compare due volte con destinazioni diverse e nessuna
    condizione che le distingua: è la fonte a non essere univoca."""
    connessione = sqlite3.connect(":memory:")
    voci = [
        {"comune": "Torino", "slug": "a", "nome": "Pantofole", "nome_originale": "Pantofole",
         "condizioni": [], "alias": [], "codice_materiale": None,
         "destinazioni": ["carta_e_cartone"], "avvertenza": None, "motivi": [], "da_revisionare": False},
        {"comune": "Torino", "slug": "b", "nome": "Pantofole", "nome_originale": "Pantofole",
         "condizioni": [], "alias": [], "codice_materiale": None,
         "destinazioni": ["rifiuto_non_recuperabile"], "avvertenza": None, "motivi": [],
         "da_revisionare": False},
    ]
    carica(connessione, DESTINAZIONI, voci, [], {})
    documento = next(d for d in documenti_oggetto(connessione) if d.nome == "Pantofole")
    assert documento.contraddizione and "non è univoca" in documento.testo
    connessione.close()
