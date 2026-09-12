"""Test del Transform sui casi reali osservati nelle 584 voci di Napoli (estrazione 12/09/2026)."""
import pytest

from ecoscan.etl.transform_napoli import (
    classifica_parentesi, deduplica, normalizza_nome, separa_voce_composta, trasforma_voce,
)


def voce(nome, destinazioni=("Non Riciclabile",), slug="s", avvertenza=None):
    return trasforma_voce({"slug": slug, "nome_originale": nome, "destinazioni": list(destinazioni),
                           "avvertenza": avvertenza})


def test_voce_di_prova_scartata():
    # il dizionario pubblico contiene una voce di test: non deve finire nell'indice
    assert voce("Test di esempio") is None


@pytest.mark.parametrize("nome, atteso", [
    ("Biro E Pena A Sfera", "Biro e pena a sfera"),
    ("Simbolo C/PAP (81)", "Simbolo C/PAP (81)"),
    ("TV a tubo catodico", "TV a tubo catodico"),
    ("calcinacci", "Calcinacci"),
    ("Albero di Natale sintetico", "Albero di Natale sintetico"),
])
def test_normalizza_nome(nome, atteso):
    assert normalizza_nome(nome) == atteso


@pytest.mark.parametrize("contenuto, tipo, valore", [
    ("40", "codice", "40"),                                   # Simbolo FE (40)
    ("tetrapak", "alias", "tetrapak"),                        # Cartone per bevande (tetrapak)
    ("in Grandi Quantità", "condizione", "grandi quantità"),  # Bambù (in Grandi Quantità)
    ("contenitore Vuoto", "condizione", "contenitore vuoto"), # Lacca (contenitore Vuoto)
    ("vuoto", "condizione", "vuoto"),                         # Tubetto del dentifricio (vuoto)
    ("senza feci", "condizione", "senza feci"),               # Pannolino ecologico (senza feci)
    ("in Plastica", "condizione", "in plastica"),             # Contenitori creme (in Plastica)
    ("scatola di pelati, tonno, ...", "esempi", "scatola di pelati, tonno, ..."),
])
def test_classifica_parentesi(contenuto, tipo, valore):
    assert classifica_parentesi(contenuto) == (tipo, valore)


@pytest.mark.parametrize("nome, nome_atteso, condizioni", [
    # la condizione sta in mezzo al nome e distingue due destinazioni diverse
    ("Cartone pulito per pizze", "Cartone per pizze", ["pulito"]),
    ("Cartone unto per pizze", "Cartone per pizze", ["unto"]),
    ("Carta Umida", "Carta", ["umido"]),
    ("Carta Unta", "Carta", ["unto"]),
    ("Barattolo in alluminio sporco", "Barattolo in alluminio", ["sporco"]),
    ("Cenere spenta di legna", "Cenere di legna", ["spento"]),
    # negazione
    ("Scarpe non utilizzabili", "Scarpe", ["non utilizzabile"]),
    ("Pantofole di stoffa, non utilizzabili", "Pantofole di stoffa", ["non utilizzabile"]),
    ("Farmaci non scaduti", "Farmaci", ["non scaduto"]),
    # congiunzione sospesa dopo la rimozione delle condizioni
    ("Cotton fioc biodegradabile e compostabile", "Cotton fioc", ["biodegradabile", "compostabile"]),
])
def test_condizioni(nome, nome_atteso, condizioni):
    v = voce(nome)
    assert v.nome == nome_atteso and v.condizioni == sorted(condizioni)


@pytest.mark.parametrize("nome, componenti", [
    ("Biro e pena a sfera", ["Biro", "pena a sfera"]),
    ("Cuffia e Cuffiette", ["Cuffia", "Cuffiette"]),
    ("Apparecchi per misurare la pressione, termometri digitali, apparecchi per aerosol",
     ["Apparecchi per misurare la pressione", "termometri digitali", "apparecchi per aerosol"]),
    # NON composte
    ("Micro computer per ciclismo, immersioni subacquee, corsa, canottaggio, ecc.", []),
    ("Braccioli, canottini, materassini e altri gonfiabili", []),
    ("Filtri di the e tisane", []),
    ("Contenitori creme per viso corpo e abbronzanti", []),
    ("Simbolo GL o GLS", []),
    ("Polistirolo espanso: gusci e barre da imballaggio", []),
])
def test_separa_voce_composta(nome, componenti):
    assert separa_voce_composta(nome) == componenti


def test_asterisco_segnalato():
    v = voce("Insetticida (barattoli Pieni O Con Tracce) *")
    assert v.nome == "Insetticida" and v.condizioni == ["contenitore pieno o con tracce"]
    assert v.da_revisionare and any("asterisco" in m for m in v.motivi)


def test_deduplica_unisce_e_conserva_avvertenza():
    a = voce("Assorbente", slug="assorbente")
    b = voce("Assorbenti", slug="assorbenti-lungo", avvertenza="Inserirli in un sacchetto apposito")
    unite, conflitti = deduplica([a, b])
    assert not conflitti and len(unite) == 1
    assert unite[0].avvertenza.startswith("Inserirli") and unite[0].slug_uniti


def test_deduplica_segnala_conflitto():
    a = voce("Cellophane", ["Isola Ecologica Estesa"], slug="cellophane")
    b = voce("Cellophane", ["Plastica e Metalli"], slug="cellophane-2")
    unite, conflitti = deduplica([a, b])
    assert len(conflitti) == 1 and len(unite) == 2
    assert all(v.da_revisionare for v in unite)


def test_condizioni_diverse_non_si_fondono():
    # stesso nome ma condizioni diverse: restano due voci con destinazioni diverse
    a = voce("Cartone pulito per pizze", ["Carta e Cartoncino"], slug="pulito")
    b = voce("Cartone unto per pizze", ["Organico"], slug="unto")
    unite, conflitti = deduplica([a, b])
    assert not conflitti and len(unite) == 2
