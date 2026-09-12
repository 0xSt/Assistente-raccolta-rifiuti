"""Test dell'estrattore Napoli.

- Funzioni di qualità: valori reali osservati sul sito ASIA (settembre 2026).
- Parser HTML: fixture SINTETICA che riproduce solo la struttura logica osservata
  (link voce, intestazioni di colonna, destinazioni tra parentesi). Verifica la logica,
  non la conformità al markup reale: quella si verifica con `--recon`.
"""
from ecoscan.etl.extract_napoli import parse_liste, parse_pagina_frazione, parse_pagina_voce
from ecoscan.etl.napoli_qualita import (
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


# Fixture sintetica che riproduce la FRAMMENTAZIONE osservata sul sito (settembre 2026):
# ogni destinazione è un elemento separato, quindi "(" , nome e ")" non stanno in un solo nodo di testo.
PAGINA_VOCE = """
<html><body>
<h1>Dove buttare Armadio?</h1>
<div class="box"><a href="https://www.asianapoli.it/dove-lo-butto/armadio/">Armadio</a>
  <div class="dest">(<span>Ecopunto Ingombranti</span> , <span>Isola Ecologica Estesa</span> ,
     <span>Numero Verde Gratuito</span>)</div></div>
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

# Stessa voce senza il blocco tra parentesi: deve funzionare il ripiego sul vocabolario
PAGINA_VOCE_SENZA_PARENTESI = PAGINA_VOCE.replace(
    '<div class="dest">(<span>Ecopunto Ingombranti</span> , <span>Isola Ecologica Estesa</span> ,\n'
    '     <span>Numero Verde Gratuito</span>)</div>', "")

PAGINA_FRAZIONE = """
<html><body>
<h1>Plastica e Metalli</h1>
<h2>Il contenitore per la raccolta della Plastica è contraddistinto dal colore <b>GIALLO</b></h2>
<h3>Cosa differenziare nel contenitore della Plastica</h3>
<div><img src="a.png"><strong>Bottiglie e flaconi in plastica</strong></div>
<div><img src="b.png"><strong>Bombolette spray non pericolose</strong><br>(non etichettate T e F)</div>
<h4>Piatti e bicchieri in plastica possono essere anche sporchi ma svuotati di ogni residuo</h4>
</body></html>
"""


def test_parser_pagina_voce_con_parentesi():
    rec = parse_pagina_voce(PAGINA_VOCE, "https://www.asianapoli.it/dove-lo-butto/armadio/")
    assert rec["nome_originale"] == "Armadio"
    assert rec["strategia_destinazioni"] == "parentesi"
    assert rec["destinazioni"] == ["Ecopunto Ingombranti", "Isola Ecologica Estesa", "Numero Verde Gratuito"]
    assert rec["descrizioni_destinazioni"]["Isola Ecologica Estesa"].startswith("Lo puoi conferire")


def test_ripiego_su_vocabolario():
    vocabolario = {"Ecopunto Ingombranti", "Isola Ecologica Estesa", "Numero Verde Gratuito", "Isola Ecologica"}
    url = "https://www.asianapoli.it/dove-lo-butto/armadio/"
    assert parse_pagina_voce(PAGINA_VOCE_SENZA_PARENTESI, url)["destinazioni"] == []
    rec = parse_pagina_voce(PAGINA_VOCE_SENZA_PARENTESI, url, vocabolario)
    assert rec["strategia_destinazioni"] == "vocabolario"
    # solo le destinazioni con icona, e vince la corrispondenza più lunga
    assert rec["destinazioni"] == ["Isola Ecologica Estesa", "Numero Verde Gratuito"]


def test_parser_liste_sintetica():
    righe = {r["slug"]: r for r in parse_liste(PAGINA_VOCE, "https://www.asianapoli.it/dove-lo-butto/armadio/")}
    assert set(righe) == {"asciugacapelli", "bacinella-in-plastica"}  # il link alla voce corrente è escluso
    assert righe["bacinella-in-plastica"]["colonna"] == "Avvertenza"
    assert e_placeholder(righe["bacinella-in-plastica"]["testo"])
    assert righe["asciugacapelli"]["testo"] is None


def test_separatori_con_spazi_dell_indice():
    # l'indice reale restituisce "Contenitore Abiti Usati , Isola Ecologica Estesa"
    assert split_destinazioni("Contenitore Abiti Usati , Isola Ecologica Estesa , Isola Ecologica Ridotta") == [
        "Contenitore Abiti Usati", "Isola Ecologica Estesa", "Isola Ecologica Ridotta"]


def test_parser_pagina_frazione():
    fr = parse_pagina_frazione(PAGINA_FRAZIONE, "")
    assert fr["nome_frazione"] == "Plastica e Metalli" and fr["colore"] == "giallo"
    ammessi = {r["testo"]: r["dettaglio"] for r in fr["regole"] if r["polarita"] == "ammesso"}
    assert ammessi["Bottiglie e flaconi in plastica"] is None
    assert ammessi["Bombolette spray non pericolose"] == "(non etichettate T e F)"  # dettaglio dopo <br>
    assert any("svuotati di ogni residuo" in n for n in fr["note"])
