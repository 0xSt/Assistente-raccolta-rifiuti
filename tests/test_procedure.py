"""Test delle procedure di smaltimento.

Le due cose che possono davvero sbagliarsi: l'**ordine** delle alternative, che è il
messaggio (prima ciò che si fa da casa), e il fatto che la raccolta ordinaria non debba
occupare il posto di una procedura che invece va spiegata.
"""
import pytest

from ecoscan import procedure as proc


@pytest.fixture
def csv_procedure(tmp_path):
    percorso = tmp_path / "procedure.csv"
    percorso.write_text(
        "comune,canale,sforzo,titolo,passi,nota,da_verificare\n"
        "Testopoli,raccolta_ordinaria,1,Da casa,Nel sacco,,\n"
        "Testopoli,ritiro_domicilio,2,Lo ritirano,Chiama | Aspetta | Esponi,Gratuito.,recapiti\n"
        "Testopoli,centro_raccolta,5,Lo porti tu,Documento | Vai,,indirizzi\n",
        encoding="utf-8")
    proc.tutte.cache_clear()
    yield percorso
    proc.tutte.cache_clear()


@pytest.fixture
def _caricate(csv_procedure, monkeypatch):
    monkeypatch.setattr(proc, "PROCEDURE", csv_procedure)
    monkeypatch.setattr(proc, "tutte", lambda *_: tuple(proc._righe(csv_procedure)))


# ------------------------------------------------------------------ lettura del file

def test_i_passi_si_leggono_separati(csv_procedure):
    procedure = proc._righe(csv_procedure)
    ritiro = next(p for p in procedure if p.canale == "ritiro_domicilio")
    assert ritiro.passi == ["Chiama", "Aspetta", "Esponi"]
    assert ritiro.nota == "Gratuito."
    assert ritiro.da_verificare == "recapiti"


def test_un_file_assente_non_fa_esplodere_niente(tmp_path):
    """Senza procedure il sistema risponde come prima: dice dove va, non come."""
    assert proc._righe(tmp_path / "non-esiste.csv") == []


@pytest.mark.parametrize("sforzo, da_casa", [(1, True), (2, True), (3, False), (5, False)])
def test_lo_sforzo_dice_se_si_fa_da_casa(sforzo, da_casa):
    assert proc.Procedura("C", "x", sforzo, "t").da_casa is da_casa


# ------------------------------------------------------------------ scelta e ordine

def test_le_alternative_sono_ordinate_dalla_piu_comoda(_caricate):
    """L'ordine è il messaggio: chi legge deve trovare per prima l'opzione che può fare da
    casa, e solo dopo quella che gli chiede di prendere la macchina."""
    trovate = proc.per_canali("Testopoli", ["centro_raccolta", "ritiro_domicilio"])
    assert [p.canale for p in trovate] == ["ritiro_domicilio", "centro_raccolta"]


def test_l_ordinaria_sparisce_quando_c_e_altro(_caricate):
    """Tutti sanno cos'è un sacco: spiegarlo occuperebbe il posto di ciò che va spiegato."""
    trovate = proc.per_canali("Testopoli", ["raccolta_ordinaria", "centro_raccolta"])
    assert [p.canale for p in trovate] == ["centro_raccolta"]


def test_l_ordinaria_resta_se_e_l_unica(_caricate):
    """Da sola non toglie il posto a nessuno, e serve a dire in quali giorni esporre."""
    assert [p.canale for p in proc.per_canali("Testopoli", ["raccolta_ordinaria"])] \
        == ["raccolta_ordinaria"]


def test_un_canale_ripetuto_non_si_ripete(_caricate):
    """Due destinazioni dello stesso canale ("Isola Estesa" e "Isola Ridotta") sono un
    gesto solo: la procedura si scrive una volta."""
    trovate = proc.per_canali("Testopoli", ["centro_raccolta", "centro_raccolta"])
    assert len(trovate) == 1


def test_un_canale_senza_procedura_viene_saltato(_caricate):
    assert proc.per_canali("Testopoli", ["canale_inventato"]) == []


def test_un_comune_senza_procedure_non_ne_inventa(_caricate):
    assert proc.per_canali("Altrove", ["centro_raccolta"]) == []


def test_il_ripiego_e_il_centro_di_raccolta(_caricate):
    """Al livello 3 "non lo so" è onesto ma inutile: chi ha l'oggetto in mano deve
    comunque buttarlo da qualche parte."""
    assert proc.di_ripiego("Testopoli").canale == "centro_raccolta"
    assert proc.di_ripiego("Altrove") is None


# ------------------------------------------------- il file vero, quello che va in produzione

def test_ogni_coppia_comune_canale_dei_dati_ha_la_sua_procedura():
    """Se i dati introducono un canale nuovo e nessuno scrive la procedura, l'utente si
    ritrova con una destinazione e nessuna istruzione: meglio accorgersene qui."""
    import sqlite3

    from ecoscan.db.vettorizza import DB

    if not DB.is_file():
        pytest.skip("database non costruito")
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    coppie = {(c, ca) for c, ca in db.execute(
        "SELECT c.nome, d.canale FROM destinazione d JOIN comune c ON c.id = d.comune_id")}
    db.close()
    scritte = {(p.comune, p.canale) for p in proc.tutte()}
    assert not coppie - scritte, f"canali senza procedura: {sorted(coppie - scritte)}"


def test_nessuna_procedura_promette_orari_o_numeri_che_non_abbiamo():
    """Una procedura inventata manda una persona a un cancello chiuso. Finché indirizzi e
    orari non sono nei dati, la colonna `da_verificare` dichiara cosa manca invece di
    riempire il vuoto con qualcosa di verosimile."""
    import re

    for procedura in proc.tutte():
        testo = " ".join([procedura.titolo, *procedura.passi, procedura.nota])
        assert not re.search(r"\b\d{2}[:.]\d{2}\b", testo), f"orario inventato in {procedura.canale}"
        assert not re.search(r"\b(?:800|0\d{1,3})[\s.-]?\d{6,}", testo), \
            f"numero di telefono inventato in {procedura.canale}"


def test_le_procedure_fuori_casa_dichiarano_cosa_manca():
    """Quelle che chiedono di spostarsi sono inutili senza un indirizzo: finché non c'è,
    va detto che manca."""
    for procedura in proc.tutte():
        if not procedura.da_casa:
            assert procedura.da_verificare, f"{procedura.comune}/{procedura.canale}"


# ------------------------------------------- una procedura per contenitore, non per canale

def test_un_contenitore_dedicato_spiega_solo_se_stesso():
    """Il difetto del 25/09: per una cintura di pelle a Torino la risposta spiegava anche
    farmaci, pile e olio esausto, e portava la nota "l'olio va in una bottiglia chiusa".

    Stavano tutti nello stesso canale (`contenitore_dedicato`) e la procedura era una sola.
    Informazione non richiesta in una risposta non è generosità: è rumore che toglie credito
    a quella richiesta.
    """
    abiti = proc.per("Torino", "contenitore_dedicato", "abiti")
    testo = " ".join([abiti.titolo, *abiti.passi, abiti.nota]).lower()
    assert "abiti" in testo or "indumenti" in testo
    for estraneo in ("olio", "farmac", "pile", "tabaccaio"):
        assert estraneo not in testo, f"la procedura degli abiti parla di {estraneo}"


def test_la_riga_generica_resta_come_ripiego():
    """Si specializza dove serve, non ovunque: l'economia di D166 — nove coppie invece di
    902 voci — non va persa per un caso particolare."""
    generica = proc.per("Torino", "contenitore_dedicato")
    assert generica is not None and not generica.destinazione
    ignota = proc.per("Torino", "contenitore_dedicato", "contenitore_che_non_esiste")
    assert ignota is generica


def test_ogni_contenitore_dedicato_dei_dati_ha_la_sua_procedura():
    """Se domani nasce un contenitore dedicato nuovo, questo test lo scopre: senza riga
    propria erediterebbe quella generica, che non dice dove andare."""
    import sqlite3
    from ecoscan.percorsi import DATI
    percorso = DATI / "ecoscan.db"
    if not percorso.is_file():
        import pytest
        pytest.skip("database non costruito")
    db = sqlite3.connect(f"file:{percorso}?mode=ro", uri=True)
    senza = []
    for comune, destinazione in db.execute(
            "SELECT c.nome, d.nome FROM destinazione d JOIN comune c ON c.id = d.comune_id "
            "WHERE d.canale = 'contenitore_dedicato'"):
        trovata = proc.per(comune, "contenitore_dedicato", destinazione)
        if trovata is None or not trovata.destinazione:
            senza.append(f"{comune}/{destinazione}")
    assert not senza, f"contenitori dedicati senza procedura propria: {senza}"
