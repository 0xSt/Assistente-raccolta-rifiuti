"""Verifica dello schema: carica entrambe le fonti e interroga come farebbe l'agente.

Uso: uv run ecoscan-demo

Torino: tutte le 324 voci estratte dal PDF (Transform minimale: condizione = testo tra parentesi).
Napoli: CAMPIONE di voci e regole osservate sul sito (settembre 2026), in attesa dell'estrazione completa.
"""
import csv
import json
import re
import sqlite3
from ecoscan.percorsi import GREZZO, SCHEMA_SQL


def main() -> None:

    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA_SQL.read_text())
    q = db.execute

    FLUSSI = ["carta", "plastica", "metalli", "vetro", "organico", "residuo", "raee", "ingombranti",
              "tessili", "farmaci", "oli", "pile"]
    db.executemany("INSERT INTO flusso VALUES (?, ?)", [(f, f.capitalize()) for f in FLUSSI])

    # (nome_locale, canale, colore, flussi)
    DESTINAZIONI = {
        "Torino": {
            "rifiuto_non_recuperabile": ("Rifiuto non recuperabile", "raccolta_ordinaria", "grigio", ["residuo"]),
            "carta_e_cartone": ("Carta e cartone", "raccolta_ordinaria", "giallo", ["carta"]),
            "organico": ("Organico", "raccolta_ordinaria", "marrone", ["organico"]),
            "imballaggi_plastica": ("Imballaggi in plastica", "raccolta_ordinaria", "grigio chiaro", ["plastica"]),
            "vetro_e_imballaggi_metallo": ("Vetro e imballaggi in metallo", "raccolta_ordinaria", "blu", ["vetro", "metalli"]),
            "centro_di_raccolta": ("Centro di raccolta", "centro_raccolta", None, []),
            "rifiuti_ingombranti": ("Rifiuti ingombranti", "ritiro_domicilio", None, ["ingombranti"]),
            "abiti": ("Abiti", "contenitore_dedicato", None, ["tessili"]),
            "farmaci": ("Farmaci", "contenitore_dedicato", None, ["farmaci"]),
            "olio_esausto": ("Olio esausto", "contenitore_dedicato", None, ["oli"]),
            "pile": ("Pile", "contenitore_dedicato", None, ["pile"]),
        },
        "Napoli": {
            "Non Riciclabile": ("Non Riciclabile", "raccolta_ordinaria", None, ["residuo"]),
            "Plastica e Metalli": ("Plastica e Metalli", "raccolta_ordinaria", "giallo", ["plastica", "metalli"]),
            "Carta e Cartone": ("Carta e Cartone", "raccolta_ordinaria", None, ["carta"]),
            "Contenitore Abiti Usati": ("Contenitore Abiti Usati", "contenitore_dedicato", None, ["tessili"]),
            "Isola Ecologica Estesa": ("Isola Ecologica Estesa", "centro_raccolta", None, []),
            "Isola Ecologica Ridotta": ("Isola Ecologica Ridotta", "centro_raccolta", None, []),
            "Ecopunto Ingombranti": ("Ecopunto Ingombranti", "raccolta_itinerante", None, ["ingombranti"]),
            "Numero Verde Gratuito": ("Numero Verde Gratuito", "ritiro_domicilio", None, ["ingombranti"]),
        },
    }

    dest_id = {}
    for i, (comune, gestore, codice, formato, url) in enumerate([
        ("Torino", "AMIAT", "amiat_rifiutologo_2025", "pdf", "https://amiat.it/content/dam/amiat/guide/Rifiutologo%20AMIAT%202025%20x%20sito.pdf"),
        ("Napoli", "ASIA Napoli", "asia_napoli_dove_lo_butto", "html", "https://www.asianapoli.it/dove-lo-butto/"),
    ], start=1):
        q("INSERT INTO comune VALUES (?, ?, ?)", (i, comune, gestore))
        q("INSERT INTO fonte (id, codice, comune_id, ente, formato, url) VALUES (?, ?, ?, ?, ?, ?)",
          (i, codice, i, gestore, formato, url))
        for chiave, (nome, canale, colore, flussi) in DESTINAZIONI[comune].items():
            did = q("INSERT INTO destinazione (comune_id, nome_locale, canale, colore) VALUES (?, ?, ?, ?)",
                    (i, nome, canale, colore)).lastrowid
            dest_id[(comune, chiave)] = did
            db.executemany("INSERT INTO destinazione_flusso VALUES (?, ?)", [(did, f) for f in flussi])
    q("INSERT INTO destinazione_alias VALUES (?, ?)", (dest_id[("Napoli", "Carta e Cartone")], "Carta e Cartoncino"))


    def nuovo_record(fonte_id, url, tipo, posizione, payload):
        q("INSERT OR IGNORE INTO snapshot (fonte_id, url, recuperato_il, sha256) VALUES (?, ?, '2026-09-11', ?)",
          (fonte_id, url, f"demo-{fonte_id}-{url}"))
        sid = q("SELECT id FROM snapshot WHERE url = ?", (url,)).fetchone()[0]
        return q("INSERT INTO record_grezzo (snapshot_id, tipo, posizione, payload, versione_estrattore) "
                 "VALUES (?, ?, ?, ?, 'demo')", (sid, tipo, posizione, json.dumps(payload, ensure_ascii=False))).lastrowid


    def carica_voce(comune, comune_id, rid, nome_originale, destinazioni, alias=(), avvertenze=()):
        m = re.fullmatch(r"(.+?)\s*\((.+)\)\s*\*?", nome_originale)  # Transform provvisorio
        nome, cond = (m.group(1), m.group(2)) if m else (nome_originale.rstrip("*"), None)
        vid = q("INSERT INTO voce (comune_id, nome_originale, nome, condizione, origine, record_grezzo_id) "
                "VALUES (?, ?, ?, ?, 'dizionario', ?)", (comune_id, nome_originale, nome, cond, rid)).lastrowid
        for k, d in enumerate(destinazioni):
            q("INSERT INTO voce_destinazione VALUES (?, ?, ?)", (vid, dest_id[(comune, d)], k))
        for a in alias:
            q("INSERT INTO voce_alias VALUES (?, ?, 'slug')", (vid, a))
        for testo, origine in avvertenze:
            q("INSERT INTO avvertenza (voce_id, testo, origine) VALUES (?, ?, ?)", (vid, testo, origine))
        return vid


    # --- Torino: tutte le voci del PDF
    with open(GREZZO / "torino" / "torino_voci_raw.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rid = nuovo_record(1, "Rifiutologo AMIAT 2025", "voce", f"pagina {r['pagina']}", r)
            carica_voce("Torino", 1, rid, r["voce_originale"], r["destinazioni_alternative"].split("|"))

    # --- Napoli: campione osservato
    PLACEHOLDER = "Questo è un eventuale messaggio che è possibile specificare per ogni singolo rifiuto!!!"
    NAPOLI = [
        ("abito-usato", "Abito usato", ["Contenitore Abiti Usati", "Isola Ecologica Estesa", "Isola Ecologica Ridotta"], None),
        ("accendino", "Accendino", ["Non Riciclabile"], None),
        ("acetone", "Acetone", ["Plastica e Metalli"], None),
        ("ammoniaca-contenitore-vuoto", "Ammoniaca", ["Plastica e Metalli"], None),
        ("armadio", "Armadio", ["Ecopunto Ingombranti", "Isola Ecologica Estesa", "Isola Ecologica Ridotta", "Numero Verde Gratuito"], None),
        ("bacinella-in-plastica", "Bacinella in plastica", ["Ecopunto Ingombranti", "Isola Ecologica Estesa", "Numero Verde Gratuito"], PLACEHOLDER),
        ("agenda-in-carta", "Agenda in carta", ["Carta e Cartone"], None),
    ]
    for slug, nome, dests, avv in NAPOLI:
        rid = nuovo_record(2, f"https://www.asianapoli.it/dove-lo-butto/{slug}/", "voce", slug, {"nome": nome, "destinazioni": dests})
        extra = slug[len(nome.lower().replace(" ", "-")):].strip("-").replace("-", " ") or None
        vid = carica_voce("Napoli", 2, rid, nome, dests)
        if extra:  # l'istruzione nello slug diventa condizione, ma resta da revisionare
            q("UPDATE voce SET condizione = ?, stato = 'da_revisionare' WHERE id = ?", (extra, vid))
            q("INSERT INTO problema_qualita (record_grezzo_id, codice, dettaglio) VALUES (?, 'info_nello_slug', ?)", (rid, extra))
        if avv:
            q("INSERT INTO problema_qualita (record_grezzo_id, codice, dettaglio) VALUES (?, 'placeholder', ?)", (rid, avv))

    url_pm = "https://www.asianapoli.it/servizi/materiali-da-differenziare/plastica-e-metalli/"
    for pol, testo, dett, originale in [
        ("ammesso", "Bottiglie e flaconi in plastica, buste in plastica", None, None),
        ("ammesso", "Caffettiere, pentole, padelle in metallo", None, "CCaffettiere, pentole, padelle in metallo"),
        ("ammesso", "Lattine per bevande, barattoli per conserve alimentari", None, None),
        ("ammesso", "Bombolette spray non pericolose", "(non etichettate T e F)", None),
        ("nota", "Piatti e bicchieri in plastica possono essere anche sporchi ma svuotati di ogni residuo", None, None),
    ]:
        rid = nuovo_record(2, url_pm, "regola_categoria", "plastica-e-metalli", {"testo": originale or testo})
        q("INSERT INTO regola_categoria (destinazione_id, polarita, testo, dettaglio, record_grezzo_id) VALUES (?, ?, ?, ?, ?)",
          (dest_id[("Napoli", "Plastica e Metalli")], pol, testo, dett, rid))
        if originale:
            q("INSERT INTO problema_qualita (record_grezzo_id, codice, dettaglio) VALUES (?, 'refuso', ?)", (rid, originale))

    # --- Serving: popolo l'indice trigrammi dalla vista
    q("INSERT INTO scheda_fts SELECT scheda_id, comune_id, testo_ricerca FROM scheda")
    db.commit()

    # =========================================================================== interrogazioni
    def stampa(titolo, sql, params=()):
        print(f"\n## {titolo}")
        for riga in q(sql, params):
            print("  ", riga)

    stampa("Conteggi", """SELECT c.nome, (SELECT count(*) FROM voce v WHERE v.comune_id = c.id),
                                 (SELECT count(*) FROM regola_categoria r JOIN destinazione d ON d.id = r.destinazione_id WHERE d.comune_id = c.id),
                                 (SELECT count(*) FROM voce v WHERE v.comune_id = c.id AND v.condizione IS NOT NULL)
                          FROM comune c""")

    CERCA = """SELECT f.scheda_id, s.livello_evidenza, s.testo_ricerca
               FROM scheda_fts f JOIN scheda s USING (scheda_id)
               WHERE scheda_fts MATCH ? AND f.comune_id = ? ORDER BY bm25(scheda_fts) LIMIT 3"""
    for comune_id, comune in [(1, "Torino"), (2, "Napoli")]:
        stampa(f"Ricerca lessicale 'padell' a {comune}", CERCA, ('"padell"', comune_id))

    stampa("Destinazioni alternative per voce (Torino, cartone pizza e divani)",
           """SELECT v.nome, v.condizione,
                     (SELECT group_concat(x, ' OPPURE ') FROM (
                         SELECT d.nome_locale || ' [' || d.canale || ']' AS x
                         FROM voce_destinazione vd JOIN destinazione d ON d.id = vd.destinazione_id
                         WHERE vd.voce_id = v.id ORDER BY vd.ordine))
              FROM voce v
              WHERE v.comune_id = 1 AND (v.nome LIKE 'Cartone da pizza%' OR v.nome = 'Divani') ORDER BY v.id""")

    stampa("Confronto tra comuni: in quale contenitore ordinario vanno i metalli?",
           """SELECT c.nome, d.nome_locale, group_concat(df2.flusso_codice, '+')
              FROM destinazione d JOIN comune c ON c.id = d.comune_id
              JOIN destinazione_flusso df ON df.destinazione_id = d.id AND df.flusso_codice = 'metalli'
              JOIN destinazione_flusso df2 ON df2.destinazione_id = d.id
              WHERE d.canale = 'raccolta_ordinaria' GROUP BY d.id""")

    stampa("Registro qualità", "SELECT codice, count(*), min(dettaglio) FROM problema_qualita GROUP BY codice")


if __name__ == "__main__":
    main()
