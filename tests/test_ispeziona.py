"""Il riepilogo deve reggere i casi limite: record senza problemi, senza avvertenza, file mancante."""
import json

import pytest

from ecoscan.etl.ispeziona_napoli import carica, riepiloga

VOCI = [
    {"slug": "armadio", "nome_originale": "Armadio", "destinazioni": ["Ecopunto Ingombranti", "Numero Verde Gratuito"],
     "problemi": [], "avvertenza": None, "descrizioni_destinazioni": {"Ecopunto Ingombranti": "descrizione"}},
    {"slug": "ammoniaca-contenitore-vuoto", "nome_originale": "Ammoniaca", "destinazioni": ["Plastica e Metalli"],
     "problemi": [{"codice": "info_nello_slug", "dettaglio": "contenitore vuoto"}],
     "avvertenza": "Svuotare il contenitore", "descrizioni_destinazioni": {}},
]


def test_riepilogo_non_esplode(capsys):
    riepiloga(VOCI, campione=2)
    out = capsys.readouterr().out
    assert "Voci: 2" in out and "info_nello_slug" in out and "Avvertenze: 1" in out


def test_carica_jsonl(tmp_path):
    f = tmp_path / "v.jsonl"
    f.write_text("\n".join(json.dumps(v, ensure_ascii=False) for v in VOCI) + "\n", encoding="utf-8")
    assert len(carica(f)) == 2


def test_file_mancante_messaggio_chiaro(tmp_path):
    with pytest.raises(SystemExit, match="ecoscan-napoli"):
        carica(tmp_path / "assente.jsonl")
