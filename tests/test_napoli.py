"""Test dell'estrattore Napoli.

- Funzioni di qualità: valori reali osservati sul sito ASIA (settembre 2026).
- Parser HTML: fixture SINTETICA che riproduce solo la struttura logica osservata
  (link voce, intestazioni di colonna, destinazioni tra parentesi). Verifica la logica,
  non la conformità al markup reale: quella si verifica con `--recon`.
"""
from extract_napoli import parse_liste, parse_pagina_voce
from napoli_qualita import (
    chiave_confronto, e_placeholder, info_nello_slug, normalizza_spazi,
    possibili_duplicati, problemi_qualita, slugify_wp, split_destinazioni,
)


def test_slugify_come_wordpress():
    assert slugify_wp("Bambù (in Grandi Quantità )") == "bambu-in-grandi-quantita"
    assert slugify_wp("proteggere l'ago con il cappuccio") == "proteggere-lago-con-il-cappuccio"


def test_info_nascosta_nello_slug():
    assert info_nello_slug("Ago per prelievi", "ago-per-prelievi-proteggere-lago-con-il-cappuccio") \
        == "proteggere lago con il cappuccio"
    assert info_nello_slug("Ammoniaca", "ammoniaca-contenitore-vuoto") == "contenitore vuoto"
    assert info_nello_slug("Assorbenti",
                           "assorbenti-inserirlo-in-un-sacchetto-apposito-da-chiudere-bene-e-da-depositare-"
                           "nel-sacco-generale-doppio-sacco").startswith("inserirlo in un sacchetto")
    assert info_nello_slug("Specchio", "specchio") is None
    assert info_nello_slug("Busto ortopedico", "busto-ortopedico-2") is None


def test_placeholder_e_destinazioni():
    assert e_placeholder("Questo è un eventuale messaggio che è possibile specificare per ogni singolo rifiuto!!!")
    assert not e_placeholder("Svuotare il contenitore")
    assert split_destinazioni("Ecopunto Ingombranti, Isola Ecologica Estesa,  Numero Verde Gratuito") == [
        "Ecopunto Ingombranti", "Isola Ecologica Estesa", "Numero Verde Gratuito"]
    assert normalizza_spazi("Bambù (in Grandi Quantità )") == "Bambù (in Grandi Quantità)"


def test_possibili_duplicati_reali():
    gruppi = possibili_duplicati(["Assorbente", "Assorbenti", "Busto ortopedico", "Busto ortopedico", "Specchio"])
    assert sorted(map(sorted, gruppi)) == [["Assorbente", "Assorbenti"], ["Busto ortopedico", "Busto ortopedico"]]
    assert chiave_confronto("Acido Cloridrico") == chiave_confronto("acido cloridrico")


def test_problemi_qualita_record():
    rec = {"nome_originale": "Ammoniaca", "slug": "ammoniaca-contenitore-vuoto",
           "destinazioni": ["Plastica e Metalli"], "destinazioni_indice": ["Plastica e Metalli"], "avvertenza": None}
    assert [p["codice"] for p in problemi_qualita(rec)] == ["info_nello_slug"]
    rec2 = {"nome_originale": "Busto ortopedico", "slug": "busto-ortopedico-2", "destinazioni": [],
            "avvertenza": "Questo è un eventuale messaggio che è possibile specificare per ogni singolo rifiuto!!!"}
    assert {p["codice"] for p in problemi_qualita(rec2)} == {"placeholder", "slug_duplicato", "senza_destinazione"}


PAGINA_SINTETICA = """
<html><body>
<h1>Dove buttare Armadio?</h1>
<div><a href="https://www.asianapoli.it/dove-lo-butto/armadio/">Armadio</a></div>
<div>(Ecopunto Ingombranti, Isola Ecologica Estesa, Numero Verde Gratuito)</div>
<ul>
 <li><img alt="Icona Porta a Porta"><span>Isola Ecologica Estesa</span><p>Lo puoi conferire presso le Isole Ecologiche Estese.</p></li>
 <li><img alt="Icona Porta a Porta"><span>Numero Verde Gratuito</span><p>Puoi contattare il numero verde.</p></li>
</ul>
<h3>Rifiuto</h3><h3>Avvertenza</h3>
<ul>
 <li><div><a href="/dove-lo-butto/asciugacapelli/">Asciugacapelli</a></div></li>
 <li><div><a href="/dove-lo-butto/bacinella-in-plastica/">Bacinella in plastica</a></div>
     <div>Questo è un eventuale messaggio che è possibile specificare per ogni singolo rifiuto!!!</div></li>
</ul>
</body></html>
"""


def test_parser_pagina_voce_sintetica():
    rec = parse_pagina_voce(PAGINA_SINTETICA, "https://www.asianapoli.it/dove-lo-butto/armadio/")
    assert rec["nome_originale"] == "Armadio"
    assert rec["destinazioni"] == ["Ecopunto Ingombranti", "Isola Ecologica Estesa", "Numero Verde Gratuito"]
    assert rec["descrizioni_destinazioni"]["Isola Ecologica Estesa"].startswith("Lo puoi conferire")


def test_parser_liste_sintetica():
    righe = {r["slug"]: r for r in parse_liste(PAGINA_SINTETICA, "https://www.asianapoli.it/dove-lo-butto/armadio/")}
    assert set(righe) == {"asciugacapelli", "bacinella-in-plastica"}  # il link accanto al titolo è escluso
    assert righe["bacinella-in-plastica"]["colonna"] == "Avvertenza"
    assert e_placeholder(righe["bacinella-in-plastica"]["testo"])
    assert righe["asciugacapelli"]["testo"] is None
