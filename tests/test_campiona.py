"""Test del campionatore: la meccanica dell'estrazione, non la bontà delle voci.

Quello che deve valere sempre: il campione è riproducibile, copre gli strati piccoli invece
di cancellarli, e non ripropone voci già coperte da un caso esistente.
"""
from ecoscan.valutazione.campiona import Voce, campiona, come_bozza, quote


def voci_finte() -> list[Voce]:
    """Due comuni, tre canali, con uno strato deliberatamente minuscolo (il ritiro a
    domicilio): è lì che una proporzione pura cancellerebbe il caso interessante."""
    voci = []
    for n in range(20):
        voci.append(Voce("Napoli", f"Ordinaria {n}", ["Plastica e Metalli"],
                         ["raccolta_ordinaria"]))
    for n in range(6):
        voci.append(Voce("Napoli", f"Ingombrante {n}", ["Isola Ecologica Estesa"],
                         ["centro_raccolta"]))
    voci.append(Voce("Napoli", "Divano", ["Isola Ecologica Estesa", "Numero Verde"],
                     ["centro_raccolta", "ritiro_domicilio"]))
    # l'unica voce il cui gesto più faticoso è il ritiro a domicilio: uno strato da uno
    voci.append(Voce("Napoli", "Carta patinata", ["Carta e Cartoncino", "Numero Verde"],
                     ["raccolta_ordinaria", "ritiro_domicilio"]))
    for n in range(12):
        voci.append(Voce("Torino", f"Ordinaria {n}", ["carta_e_cartone"],
                         ["raccolta_ordinaria"]))
    return voci


def test_lo_stesso_seme_da_lo_stesso_campione():
    """Un campione che cambia a ogni esecuzione non si può citare in una relazione: non si
    saprebbe di quale campione si sta parlando."""
    voci = voci_finte()
    assert [v.nome for v in campiona(voci, 10, semina=1)] == \
           [v.nome for v in campiona(voci, 10, semina=1)]
    assert [v.nome for v in campiona(voci, 10, semina=1)] != \
           [v.nome for v in campiona(voci, 10, semina=2)]


def test_il_canale_dello_strato_e_il_gesto_piu_faticoso():
    """Una voce che si può buttare nel sacco *oppure* portare al centro di raccolta
    appartiene, per la valutazione, al centro di raccolta: è lì che la risposta deve
    spiegare qualcosa in più."""
    voce = Voce("Napoli", "Divano", ["A", "B"], ["raccolta_ordinaria", "centro_raccolta"])
    assert voce.canale == "centro_raccolta"
    assert voce.strato == ("Napoli", "centro_raccolta", "multipla")


def test_gli_strati_piccoli_non_spariscono():
    """Il ritiro a domicilio è una voce su ventisette, ed è dove il sistema ha sbagliato
    (microonde, divano): una proporzione pura lo escluderebbe dal campione."""
    estratte = campiona(voci_finte(), 12, semina=3)
    assert any(v.canale == "ritiro_domicilio" for v in estratte)


def test_i_due_comuni_pesano_uguale():
    """Napoli ha più voci di Torino, ma sono due fonti con difetti speculari: il campione
    le confronta, non le pesa."""
    estratte = campiona(voci_finte(), 12, semina=5)
    napoli = sum(1 for v in estratte if v.comune == "Napoli")
    torino = sum(1 for v in estratte if v.comune == "Torino")
    assert abs(napoli - torino) <= 3


def test_le_voci_gia_coperte_si_saltano():
    """Un caso ripetuto gonfia le percentuali senza misurare niente di nuovo."""
    escludi = {v.nome for v in voci_finte() if v.comune == "Torino"}
    estratte = campiona(voci_finte(), 10, semina=1, escludi=escludi)
    assert all(v.comune == "Napoli" or v.nome not in escludi for v in estratte)


def test_le_quote_non_chiedono_piu_voci_di_quante_ce_ne_siano():
    strati = {("Napoli", "centro_raccolta", "singola"): [object()]}
    assert quote(strati, 50) == {("Napoli", "centro_raccolta", "singola"): 1}


def test_la_bozza_lascia_vuota_solo_la_domanda():
    """La divisione del lavoro: l'attesa la sa il database, la domanda la sa solo una
    persona. Una bozza che riempie anche l'oggetto produrrebbe casi tautologici."""
    riga = come_bozza(Voce("Napoli", "Vasetto in plastica per alimenti",
                           ["Plastica e Metalli"], ["raccolta_ordinaria"]))
    assert riga["oggetto"] == ""
    assert riga["voce_fonte"] == "Vasetto in plastica per alimenti"
    assert riga["destinazioni_attese"] == ["Plastica e Metalli"]
    assert riga["origine"] == "campione"
    assert riga["strato"] == {"canale": "raccolta_ordinaria", "alternative": 1}
