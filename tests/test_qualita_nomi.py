"""Test dei controlli sulla qualità dei nomi normalizzati.

Il valore di questi controlli sta tutto nella **precisione**: un controllo che segnala nomi
sani viene disattivato e non serve più a niente. Per questo i test sui falsi positivi sono
più numerosi di quelli sui difetti veri.
"""
import pytest

from ecoscan.etl import qualita_nomi


@pytest.mark.parametrize("nome, difetto", [
    ("Stovaglie in materiale", "materiale annunciato e non detto"),
    ("Piatti di materiale", "materiale annunciato e non detto"),
    ("Tovaglioli di carta o di cibo", "congiunzione seguita da preposizione"),
    ("Scatole di cartone e", "congiunzione orfana"),
    ("Contenitori in di plastica", "preposizioni consecutive"),
    ("Bottiglia bottiglia di vetro", "parola ripetuta"),
    ("Cartone da pizza di", "finisce con una preposizione"),
    ("Bottiglia  di vetro", "spazi doppi"),
])
def test_i_nomi_mutilati_vengono_segnalati(nome, difetto):
    assert difetto in qualita_nomi.difetti(nome)


@pytest.mark.parametrize("nome", [
    "Cartone da pizza",
    "Bottiglia in plastica",              # un materiale detto per intero non è un difetto
    "Barattolo in latta",
    "CD",                                 # i nomi corti sono spesso sigle legittime
    "Piatti e bicchieri di plastica",     # congiunzione fra due oggetti, non fra condizioni
    "Pentole e padelle",
    "Lampadine a risparmio energetico",
    "Toner e cartucce per stampanti",
    "Olio di frittura",
    "Rifiuti da apparecchiature elettriche",
])
def test_i_nomi_sani_non_vengono_segnalati(nome):
    """Il costo di un falso positivo è alto: chi revisiona smette di fidarsi dell'elenco."""
    assert qualita_nomi.difetti(nome) == []


def test_un_nome_vuoto_non_fa_esplodere_il_controllo():
    assert qualita_nomi.difetti("") == []
    assert qualita_nomi.difetti(None) == []


def test_il_motivo_e_nella_forma_usata_dal_transform():
    motivo = qualita_nomi.motivo("Stovaglie in materiale")
    assert motivo and "verificare" in motivo
    assert qualita_nomi.motivo("Cartone da pizza") is None


def test_un_difetto_diventa_un_motivo_di_revisione():
    """Il collegamento che rende il controllo utile: la voce compare fra quelle da
    revisionare di `ecoscan-transform`, invece di restare in un elenco che nessuno guarda."""
    from ecoscan.etl.transform_comune import trasforma_voce
    voce = trasforma_voce({"slug": "stoviglie", "destinazioni": ["organico"],
                           "nome_originale": "Stovaglie monouso in materiale compostabile"})
    assert voce.nome.lower().endswith("in materiale")      # la normalizzazione ha mutilato
    assert any("sgrammaticato" in m for m in voce.motivi)
    assert voce.da_revisionare
