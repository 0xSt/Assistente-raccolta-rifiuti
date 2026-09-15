"""Test della diagnostica del canale immagine.

Il PNG generato a mano deve essere un PNG valido: se non lo fosse, la diagnosi
incolperebbe il modello di un difetto nostro.
"""
import struct
import zlib

from ecoscan.agente.diagnostica import COLORI, png_tinta_unita


def test_il_png_ha_firma_e_dimensioni_giuste():
    dati = png_tinta_unita(COLORI["rosso"], lato=32)
    assert dati[:8] == b"\x89PNG\r\n\x1a\n"
    larghezza, altezza = struct.unpack(">II", dati[16:24])
    assert (larghezza, altezza) == (32, 32)


def test_i_blocchi_hanno_crc_valido():
    """Un CRC sbagliato farebbe rifiutare l'immagine senza dire perché."""
    dati = png_tinta_unita(COLORI["blu"], lato=8)
    posizione = 8
    tipi = []
    while posizione < len(dati):
        lunghezza = struct.unpack(">I", dati[posizione:posizione + 4])[0]
        corpo = dati[posizione + 4:posizione + 8 + lunghezza]
        atteso = struct.unpack(">I", dati[posizione + 8 + lunghezza:posizione + 12 + lunghezza])[0]
        assert zlib.crc32(corpo) == atteso
        tipi.append(corpo[:4])
        posizione += 12 + lunghezza
    assert tipi == [b"IHDR", b"IDAT", b"IEND"]


def test_i_pixel_sono_davvero_del_colore_chiesto():
    lato = 4
    dati = png_tinta_unita(COLORI["verde"], lato=lato)
    inizio = dati.index(b"IDAT") + 4
    fine = dati.index(b"IEND") - 8
    grezzo = zlib.decompress(dati[inizio:fine])
    riga = grezzo[:1 + 3 * lato]
    assert riga[0] == 0                       # filtro nessuno
    assert tuple(riga[1:4]) == COLORI["verde"]


def test_l_immagine_a_due_meta_ha_i_due_colori_al_posto_giusto():
    """La domanda sulla posizione non si può indovinare: serve che l'immagine sia davvero
    divisa a metà."""
    import zlib

    from ecoscan.agente.diagnostica import png_due_meta

    lato = 8
    dati = png_due_meta(COLORI["verde"], COLORI["rosso"], lato=lato)
    inizio = dati.index(b"IDAT") + 4
    fine = dati.index(b"IEND") - 8
    riga = zlib.decompress(dati[inizio:fine])[:1 + 3 * lato]
    assert tuple(riga[1:4]) == COLORI["verde"]                    # primo pixel a sinistra
    assert tuple(riga[1 + 3 * (lato - 1):1 + 3 * lato]) == COLORI["rosso"]   # ultimo a destra
