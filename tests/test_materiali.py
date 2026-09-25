"""Quando due materiali si escludono.

Il caso che ha fatto nascere questo modulo: una forchetta d'acciaio a cui il sistema ha
risposto "Non Riciclabile" citando "Forchetta in plastica". Il modello aveva riconosciuto
l'acciaio e l'aveva scritto nel motivo della scelta.

La regola deve essere prudente in una direzione sola: meglio lasciar passare un documento
dubbio che escludere quello giusto perché il riconoscimento ha sbagliato materiale.
"""
from ecoscan import materiali


def test_le_parole_della_stessa_famiglia_si_riconoscono():
    assert materiali.famiglia("acciaio") == materiali.famiglia("alluminio") == "metallo"
    assert materiali.famiglia("polistirolo") == "plastica"
    assert materiali.famiglia("forchetta") is None


def test_le_famiglie_si_leggono_da_un_testo_libero():
    assert materiali.famiglie_nel_testo("Forchetta in plastica.") == {"plastica"}
    assert materiali.famiglie_nel_testo("Barattolo in alluminio a acciaio.") == {"metallo"}
    assert materiali.famiglie_nel_testo("Barattolo in metallo o plastica") == {"metallo", "plastica"}
    assert materiali.famiglie_nel_testo("Scatolette per tonno e altri alimenti.") == set()


def test_il_confronto_e_per_parola_intera():
    """"Gommone" non è di gomma e "incartamento" non è di carta: una sottostringa non basta."""
    assert materiali.famiglie_nel_testo("gommone") == set()
    assert materiali.famiglie_nel_testo("incartamento") == set()
    assert materiali.famiglie_nel_testo("scatola in banda stagnata") == {"metallo"}


def test_il_caso_della_forchetta():
    """La riga che il sistema avrebbe dovuto rifiutare."""
    assert materiali.incompatibili("Forchetta in plastica. Va in Non Riciclabile.", ["acciaio"])
    assert not materiali.incompatibili("Stoviglie in metallo. Va in Plastica e Metalli.",
                                       ["acciaio", "acciaio inossidabile"])


def test_chi_tace_non_viene_escluso():
    """Non sapere di che materiale è non è una ragione per scartare un documento."""
    assert not materiali.incompatibili("Scatolette per tonno.", ["acciaio"])
    assert not materiali.incompatibili("Forchetta in plastica.", [])
    assert not materiali.incompatibili("Forchetta in plastica.", ["oggetto lucido"])


def test_un_documento_che_nomina_piu_materiali_e_compatibile_con_ognuno():
    """"Barattolo in metallo o plastica" vale sia per l'uno sia per l'altro."""
    testo = "Barattolo in metallo o plastica per alimenti in polvere."
    assert not materiali.incompatibili(testo, ["acciaio"])
    assert not materiali.incompatibili(testo, ["plastica"])
    assert materiali.incompatibili(testo, ["vetro"])


def test_il_nome_del_contenitore_non_e_il_materiale_dell_oggetto():
    """A Napoli il contenitore si chiama "Plastica e Metalli": letto dentro il testo di un
    documento faceva sembrare di plastica una scatoletta di metallo, e la faceva scartare.
    Il filtro guarda il nome del documento, e il plurale "Metalli" ora si riconosce."""
    assert materiali.famiglie_nel_testo("Va in Plastica e Metalli.") == {"plastica", "metallo"}
    assert not materiali.incompatibili(
        "Scatolette per tonno e altri alimenti. Va in Plastica e Metalli.", ["acciaio"])


def test_le_voci_reali_di_napoli_che_il_filtro_deve_tenere():
    """I candidati veri restituiti da /cerca per "forchetta acciaio": di tutti questi
    l'unico che va escluso è la forchetta di plastica."""
    acciaio = ["acciaio inossidabile"]
    da_tenere = ["Scatolette di metallo per alimenti e cibo per animali",
                 "Scatoletta metallica per alimenti", "Scatolette per tonno e altri alimenti",
                 "Scatola in acciaio", "Barattolo in alluminio a acciaio",
                 "Barattolo in metallo o plastica per alimenti in polvere",
                 "Stoviglie in metallo", "Vaschetta in alluminio per alimenti"]
    assert not any(materiali.incompatibili(nome, acciaio) for nome in da_tenere)
    assert materiali.incompatibili("Forchetta in plastica", acciaio)


# --------------------------------------- il rovescio: quando il materiale NON lo sappiamo

def test_due_omonimi_di_materiali_diversi_chiedono_una_domanda():
    """Il difetto che restava scoperto: "bicchiere" a Napoli può essere di vetro (Non
    Riciclabile) o di plastica (Plastica e Metalli), e la risposta cambia del tutto."""
    assert materiali.distinzione([
        ("Bicchiere di vetro", ("Non Riciclabile",)),
        ("Bicchiere in plastica", ("Plastica e Metalli",))]) == ["plastica", "vetro"]


def test_non_si_chiede_se_la_risposta_non_cambierebbe():
    """Alluminio e latta sono due materiali, ma a Napoli vanno nello stesso contenitore:
    la domanda costerebbe un giro all'utente per niente."""
    assert materiali.distinzione([
        ("Barattolo in alluminio", ("Plastica e Metalli",)),
        ("Barattolo in latta", ("Plastica e Metalli",))]) == []


def test_non_si_chiede_con_un_materiale_solo():
    assert materiali.distinzione([("Bottiglia in vetro", ("Vetro",))]) == []


def test_un_documento_che_nomina_due_materiali_non_distingue_niente():
    """"Barattolo in metallo o plastica" risponderebbe a entrambe le risposte: come opzione
    di una domanda non separa nulla."""
    assert materiali.dichiarato("Barattolo in metallo o plastica") is None
    assert materiali.distinzione([
        ("Barattolo in metallo o plastica", ("Plastica e Metalli",)),
        ("Barattolo in vetro", ("Vetro",))]) == []


def test_un_documento_che_tace_il_materiale_non_entra_nella_domanda():
    assert materiali.dichiarato("Scatolette per tonno") is None
