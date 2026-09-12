"""Test del profilo di Torino sui casi reali del Rifiutologo AMIAT 2025 (324 voci)."""
import pytest

from ecoscan.etl.transform_comune import classifica_parentesi, deduplica
from ecoscan.etl.transform_torino import PROFILO_TORINO, trasforma_voce


def voce(nome, destinazioni=("rifiuto_non_recuperabile",), slug="s"):
    return trasforma_voce({"slug": slug, "nome_originale": nome,
                           "destinazioni": list(destinazioni), "avvertenza": None})


@pytest.mark.parametrize("nome, nome_atteso, condizioni", [
    # a Torino "usa e getta" DISTINGUE le destinazioni: è una condizione, non una locuzione fissa
    ("Piatti in plastica usa e getta", "Piatti in plastica", ["usa e getta"]),
    ("Piatti in plastica dura riutilizzabili", "Piatti in plastica dura", ["riutilizzabile"]),
    ("Cartone da pizza pulito", "Cartone da pizza", ["pulito"]),
    ("Cartone da pizza sporco (solo se certificato compostabile)", "Cartone da pizza",
     ["solo se compostabile certificato", "sporco"]),
    ("Carta assorbente da cucina non unta", "Carta assorbente da cucina", ["non unto"]),
    ("Capsule del caffè in plastica con residui di caffè", "Capsule del caffè in plastica", ["con residuo"]),
    ("Bombolette spray in alluminio (non infiammabili)", "Bombolette spray in alluminio", ["non infiammabile"]),
    ("Foglie secche (grandi quantitativi)", "Foglie secche", ["grandi quantità"]),
    ("Libri (senza copertina plastificata)", "Libri", ["senza copertina plastificata"]),
    ("Laterizi (in piccole quantità prevenienti da lavori domestici)", "Laterizi",
     ["piccole quantità da lavori domestici"]),
])
def test_condizioni_torino(nome, nome_atteso, condizioni):
    v = voce(nome)
    assert v.nome == nome_atteso and v.condizioni == sorted(condizioni)


@pytest.mark.parametrize("contenuto, tipo", [
    ("alluminio", "condizione"),            # Involucro cioccolatini (alluminio)
    ("plastica argentata", "condizione"),   # Involucro cioccolatini (plastica argentata)
    ("in metallo o plastica", "condizione"),
    ("carta chimica o termica", "condizione"),
    ("di finestre e porte", "condizione"),  # provenienza
    ("pluriball", "alias"),                 # sinonimo utile per la ricerca
    ("cappelli, cinture, cravatte", "esempi"),
])
def test_parentesi_torino(contenuto, tipo):
    assert classifica_parentesi(contenuto, PROFILO_TORINO)[0] == tipo


def test_involucro_cioccolatini_non_e_un_conflitto():
    # stesso nome, materiali diversi, destinazioni diverse: la condizione li distingue
    a = voce("Involucro cioccolatini (alluminio)", ["vetro_e_imballaggi_metallo"], slug="a")
    b = voce("Involucro cioccolatini (plastica argentata)", ["imballaggi_plastica"], slug="b")
    unite, conflitti = deduplica([a, b])
    assert not conflitti and len(unite) == 2


def test_comune_nel_record():
    assert voce("Divani").comune == "Torino"
