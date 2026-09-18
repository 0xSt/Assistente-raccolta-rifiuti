"""Test del meccanismo di revisione manuale.

Le decisioni stanno in CSV versionati e vengono applicate a ogni riesecuzione del Transform:
è ciò che impedisce al lavoro umano di andare perso quando le regole cambiano.
"""
import pytest

from ecoscan.etl import revisioni as rev
from ecoscan.etl.esegui_transform import esegui
from ecoscan.etl.transform_torino import PROFILO_TORINO


def grezza(slug, nome, destinazioni=("organico",)):
    return {"slug": slug, "nome_originale": nome, "destinazioni": list(destinazioni), "avvertenza": None}


def test_non_separare_conserva_il_nome_intero():
    grezze = [grezza("foglie-e-fiori-secchi", "Foglie e fiori secchi")]
    senza, _, _ = esegui(grezze, PROFILO_TORINO)
    assert senza[0].alias == ["Fiori secchi"] and senza[0].da_revisionare

    decisioni = {"foglie-e-fiori-secchi": [{"azione": "non_separare", "valore": "", "nota": "qualifica entrambi"}]}
    con, _, _ = esegui(grezze, PROFILO_TORINO, decisioni)
    assert con[0].nome == "Foglie e fiori secchi" and con[0].alias == []
    assert not con[0].da_revisionare


def test_conferma_chiude_la_revisione_senza_cambiare_nulla():
    grezze = [grezza("giornali-e-riviste", "Giornali e riviste")]
    decisioni = {"giornali-e-riviste": [{"azione": "conferma", "valore": "", "nota": "due oggetti"}]}
    voci, _, _ = esegui(grezze, PROFILO_TORINO, decisioni)
    assert voci[0].alias == ["Riviste"] and not voci[0].da_revisionare


@pytest.mark.parametrize("azione, valore, attributo, atteso", [
    ("nome", "Penna a sfera", "nome", "Penna a sfera"),
    ("alias", "Penna a sfera;Biro", "alias", ["Penna a sfera", "Biro"]),
    ("condizione", "unto;pulito", "condizioni", ["pulito", "unto"]),
    ("avvertenza", "Vedi nota a pagina 21", "avvertenza", "Vedi nota a pagina 21"),
])
def test_azioni_di_sostituzione(azione, valore, attributo, atteso):
    voci, _, _ = esegui([grezza("x", "Oggetto")], PROFILO_TORINO,
                        {"x": [{"azione": azione, "valore": valore, "nota": ""}]})
    assert getattr(voci[0], attributo) == atteso


def test_scarta():
    voci, _, scartate = esegui([grezza("x", "Oggetto")], PROFILO_TORINO,
                               {"x": [{"azione": "scarta", "valore": "", "nota": "non è un rifiuto"}]})
    assert voci == [] and scartate == 1


def test_da_decidere_lascia_la_voce_aperta():
    voci, _, _ = esegui([grezza("a-e-b", "Alfa e beta")], PROFILO_TORINO,
                        {"a-e-b": [{"azione": "da_decidere", "valore": "", "nota": "da capire"}]})
    assert voci[0].da_revisionare


def test_decisione_su_voce_inesistente_ferma_tutto():
    # se la fonte cambia, la decisione va rivista, non ignorata in silenzio
    with pytest.raises(SystemExit, match="voci inesistenti"):
        esegui([grezza("x", "Oggetto")], PROFILO_TORINO,
               {"slug-sparito": [{"azione": "conferma", "valore": "", "nota": ""}]})


def test_azione_sconosciuta_rifiutata(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("slug,azione,valore,nota\nx,inventata,,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="azione non riconosciuta"):
        rev.carica("torino", f)


@pytest.mark.parametrize("comune", ["napoli", "torino"])
def test_file_di_decisioni_presenti_e_validi(comune):
    decisioni = rev.carica(comune)
    assert decisioni, f"nessuna decisione caricata per {comune}"
    assert all(d["azione"] in rev.AZIONI for lista in decisioni.values() for d in lista)


@pytest.mark.parametrize("comune, attese", [("napoli", 17), ("torino", 19)])
def test_tutte_le_decisioni_sono_chiuse(comune, attese):
    """Nessuna voce deve restare `da_decidere`: se ne compare una, va affrontata."""
    decisioni = rev.carica(comune)
    assert sum(len(v) for v in decisioni.values()) == attese
    aperte = [slug for slug, lista in decisioni.items()
              if any(d["azione"] == "da_decidere" for d in lista)]
    assert not aperte, f"decisioni ancora aperte per {comune}: {aperte}"


def test_ogni_decisione_ha_una_motivazione():
    # la nota è ciò che rende la decisione difendibile a distanza di mesi
    for comune in ("napoli", "torino"):
        senza_nota = [slug for slug, lista in rev.carica(comune).items()
                      for d in lista if not d["nota"]]
        assert not senza_nota, f"decisioni senza motivazione in {comune}: {senza_nota}"
