"""Interfaccia a chat: si allega una foto e si riceve una risposta.

Il funzionamento ricalca quello dei comuni assistenti: un campo unico in basso dove si
scrive e si allega. La conversazione serve a qualcosa di preciso: quando l'agente non è
sicuro fa una domanda, e la risposta dell'utente arriva come messaggio successivo.

Il frontend non sa nulla di Qdrant, Ollama o del database: parla solo con il backend
(`frontend/cliente.py`). Un test verifica che resti così.
"""
from __future__ import annotations

import streamlit as st

from ecoscan import configurazione as conf
from ecoscan.frontend import presentazione
from ecoscan.frontend.cliente import ClienteAPI, ErroreBackend

BENVENUTO = (
    "Ciao! Dimmi un oggetto da buttare e ti dico dove va, secondo le regole del tuo comune.\n\n"
    "Puoi **fotografarlo** con la graffetta qui sotto, oppure **scriverne il nome**: "
    "\"cartone della pizza\", \"barattolo di vetro\". Se vuoi, aggiungi un dettaglio: "
    "\"è vuota\", \"è unto\"."
)

MOTIVI = {
    "contenitore_sbagliato": "Il contenitore indicato è sbagliato",
    "oggetto_sbagliato": "Non ha capito che oggetto è",
    "altro": "Altro",
}


def prepara_stato() -> None:
    st.session_state.setdefault("messaggi", [{"ruolo": "assistente", "testo": BENVENUTO}])
    st.session_state.setdefault("contesto", None)      # l'ultimo consegnato dal backend
    st.session_state.setdefault("attende_risposta", False)   # c'è un chiarimento in sospeso
    st.session_state.setdefault("comune", None)


@st.cache_data(ttl=60, show_spinner=False)
def elenco_comuni(base: str) -> list[dict]:
    return ClienteAPI(base).comuni()


@st.cache_data(ttl=600, show_spinner=False)
def elenco_destinazioni(base: str, comune: str) -> list[dict]:
    """I contenitori del comune. Cambiano solo quando cambiano i dati, quindi si chiedono
    una volta; se il backend non risponde si resta senza, invece di lasciare l'utente senza
    risposta."""
    try:
        return ClienteAPI(base).destinazioni(comune)
    except ErroreBackend:
        return []


def etichette_destinazioni(base: str, comune: str) -> dict[str, str]:
    """Nome interno -> nome leggibile, per tradurre le risposte."""
    return {d["nome"]: d["etichetta"] for d in elenco_destinazioni(base, comune)}


def legenda(base: str, comune: str) -> None:
    """Dove si può buttare, in questo comune: l'elenco completo dei contenitori.

    Serve a dare all'utente il vocabolario del sistema *prima* di leggere una risposta. Una
    risposta come "Multimateriale" non dice niente a chi non sa quali sono i contenitori del
    suo comune, e l'elenco è anche il modo più onesto di dichiarare i limiti: ciò che non è
    in lista, l'assistente non può indicarlo.

    Raggruppati per canale perché è la distinzione che cambia il gesto: il porta a porta si
    fa da casa, il centro di raccolta richiede di spostarsi.
    """
    contenitori = elenco_destinazioni(base, comune)
    if not contenitori:
        return
    with st.expander(f"Dove si butta a {comune} ({len(contenitori)} contenitori)"):
        st.caption("L'assistente può indicare solo questi. Sono i contenitori previsti dal "
                   "regolamento comunale.")
        canali: dict[str, list[dict]] = {}
        for d in contenitori:
            canali.setdefault(d.get("canale") or "altro", []).append(d)
        for canale, gruppo in canali.items():
            st.markdown(f"**{canale.replace('_', ' ').capitalize()}**")
            for d in gruppo:
                riga = f"- {d['etichetta']}"
                if nota := d.get("note"):
                    riga += f" — {nota}"
                st.markdown(riga)


def barra_laterale(cliente: ClienteAPI) -> str | None:
    with st.sidebar:
        st.markdown("### EcoScan")
        st.caption("Assistente per la raccolta differenziata. Funziona in locale.")
        try:
            comuni = elenco_comuni(cliente.base)
        except ErroreBackend as errore:
            st.error(str(errore))
            return None

        nomi = [c["nome"] for c in comuni]
        comune = st.selectbox("Comune", nomi, index=0,
                              help="Le regole cambiano da comune a comune: "
                                   "la risposta vale solo per quello scelto.")
        scelto = next(c for c in comuni if c["nome"] == comune)
        st.caption(f"{scelto['gestore']} · {scelto['voci']} voci · {scelto['regole']} regole")

        st.divider()
        if st.button("Nuova conversazione", width="stretch"):
            st.session_state.messaggi = [{"ruolo": "assistente", "testo": BENVENUTO}]
            st.session_state.contesto = None
            st.session_state.attende_risposta = False
            st.session_state.pop("ultima", None)
            st.rerun()

        with st.expander("Stato dei servizi"):
            try:
                salute = cliente.salute()
                for servizio in ("database", "qdrant", "ollama"):
                    st.write(f"{'🟢' if salute[servizio] else '🔴'} {servizio}")
                st.caption(f"{salute.get('schede_indicizzate', '?')} schede · "
                           f"modello {salute['modello_visione']}")
            except ErroreBackend as errore:
                st.error(str(errore))
    return comune


def mostra_messaggio(messaggio: dict) -> None:
    with st.chat_message("user" if messaggio["ruolo"] == "utente" else "assistant"):
        if immagine := messaggio.get("immagine"):
            st.image(immagine, width=220)
        # cosa ha visto il modello sta PRIMA della risposta: è il passaggio che l'utente
        # deve poter smentire, e dopo la risposta non lo leggerebbe più
        if visto := messaggio.get("riconoscimento"):
            st.caption(visto)
        if messaggio.get("testo"):
            st.markdown(messaggio["testo"])
        if nota := messaggio.get("nota"):
            st.caption(nota)
        if spiegazione := messaggio.get("spiegazione"):
            with st.expander("Come ci sono arrivato"):
                st.markdown(spiegazione)
                if candidati := messaggio.get("candidati"):
                    with st.expander("Tutti i documenti trovati"):
                        st.dataframe(candidati, hide_index=True, width="stretch")


def aggiungi_risposta(risposta: dict, etichette: dict[str, str]) -> None:
    st.session_state.messaggi.append({
        "ruolo": "assistente",
        "riconoscimento": presentazione.frase_riconoscimento(risposta),
        "testo": presentazione.messaggio(risposta, etichette),
        "nota": presentazione.nota_fonte(risposta),
        "spiegazione": presentazione.spiegazione(risposta, etichette),
        "candidati": presentazione.riassunto_candidati(risposta, etichette),
    })
    # il contesto si conserva SEMPRE: serve al chiarimento, ma anche a correggere
    # l'oggetto riconosciuto dopo una risposta già data
    st.session_state.contesto = risposta.get("contesto") or None
    st.session_state.attende_risposta = bool(risposta.get("chiarimento"))
    st.session_state.ultima = risposta


def chiedi(etichette: dict[str, str], azione, *argomenti) -> None:
    """Una chiamata al backend, con l'attesa e l'errore gestiti una volta sola."""
    try:
        with st.spinner("Ci penso… su CPU può volerci qualche minuto"):
            risposta = azione(*argomenti)
        aggiungi_risposta(risposta, etichette)
    except ErroreBackend as errore:
        st.session_state.messaggi.append({"ruolo": "assistente", "testo": f"⚠️ {errore}"})


def pulsanti_chiarimento(cliente: ClienteAPI, etichette: dict[str, str]) -> None:
    """Le opzioni del chiarimento come pulsanti.

    Le condizioni sono note (vengono dalle varianti del documento), quindi non c'è motivo
    di far indovinare all'utente come si scrivono. Il pulsante manda a /continua lo stesso
    testo che avrebbe scritto: il backend non cambia.
    """
    ultima = st.session_state.get("ultima") or {}
    opzioni = ultima.get("opzioni") or []
    if not (st.session_state.attende_risposta and opzioni):
        return
    colonne = st.columns(min(len(opzioni), 4))
    for colonna, opzione in zip(colonne, opzioni, strict=False):
        if colonna.button(opzione.capitalize(), key=f"opzione-{opzione}", width="stretch"):
            st.session_state.messaggi.append({"ruolo": "utente", "testo": opzione})
            chiedi(etichette, cliente.continua, st.session_state.contesto, opzione)
            st.rerun()


def correzione(cliente: ClienteAPI, etichette: dict[str, str]) -> None:
    """Se il modello ha visto l'oggetto sbagliato, l'utente lo dice e si rifà solo la
    ricerca: la foto non viene riletta, e chi ha l'oggetto in mano ha ragione."""
    ultima = st.session_state.get("ultima")
    if not ultima or not st.session_state.contesto or st.session_state.attende_risposta:
        return
    visto = (ultima.get("riconoscimento") or {}).get("oggetto")
    if not visto:
        return
    with st.expander(f"Non è un/una {visto}?"):
        oggetto = st.text_input("Dimmi tu cos'è", key="correzione",
                                placeholder="per esempio: cartone della pizza")
        if st.button("Rifai la ricerca", disabled=not oggetto.strip()):
            st.session_state.messaggi.append({"ruolo": "utente", "testo": f"È un {oggetto}."})
            chiedi(etichette, cliente.correggi, st.session_state.contesto, oggetto.strip())
            st.rerun()


def riscontro(cliente: ClienteAPI, comune: str, etichette: dict[str, str]) -> None:
    """Il giudizio dell'utente, raccolto in modo che diventi misurabile.

    Il pollice su basta da solo: l'attesa sono le destinazioni appena date, e il caso serve
    a non regredire. Il pollice giù da solo invece non misura niente — sapere che una
    risposta è sbagliata senza sapere quale fosse quella giusta non si può rieseguire — per
    questo chiede **dove andava davvero**, scegliendolo fra i contenitori del comune.

    Il motivo separa i due difetti che il sistema affronta in punti diversi: "non ha capito
    che oggetto è" riguarda il modello di visione, "il contenitore è sbagliato" riguarda
    recupero e scelta. Solo il secondo diventa un caso di valutazione.
    """
    ultima = st.session_state.get("ultima")
    if not ultima or not ultima.get("destinazioni"):
        return
    oggetto = (ultima.get("riconoscimento") or {}).get("oggetto")
    date = ultima.get("destinazioni") or []
    contesto = ultima.get("contesto", {})

    sinistra, destra, _ = st.columns([1, 1, 6])
    if sinistra.button("👍", help="La risposta è giusta"):
        cliente.riscontro(comune, True, oggetto=oggetto, destinazioni_date=date,
                          contesto=contesto)
        st.session_state.pop("segnala", None)
        st.toast("Grazie: ora è un caso da non sbagliare più.")
    if destra.button("👎", help="La risposta è sbagliata"):
        st.session_state.segnala = True

    if not st.session_state.get("segnala"):
        return
    with st.form("segnalazione"):
        st.caption("Cosa non andava?")
        motivo = st.radio("Motivo", list(MOTIVI), format_func=MOTIVI.get,
                          label_visibility="collapsed")
        # si sceglie il nome INTERNO mostrando l'etichetta: l'attesa deve essere confrontabile
        # con le destinazioni delle risposte, che portano il nome interno
        attesa = st.selectbox(
            "Dove andava davvero?", [None, *sorted(etichette)],
            format_func=lambda n: "Non lo so" if n is None else etichette.get(n, n),
            help="Se lo sai, questa risposta diventa un caso di prova per l'assistente.")
        nota = st.text_input("Vuoi aggiungere qualcosa?", placeholder="facoltativo")
        if st.form_submit_button("Invia"):
            esito = cliente.riscontro(
                comune, False, oggetto=oggetto, destinazioni_date=date,
                destinazione_attesa=attesa, motivo=motivo, nota=nota or None, contesto=contesto)
            st.session_state.pop("segnala", None)
            st.toast("Grazie: mi servirà a migliorare."
                     if not esito.get("diventato_caso_di_valutazione")
                     else "Grazie: è diventato un caso di prova.")
            st.rerun()


def mostra_conversazione(cliente: ClienteAPI, comune: str, etichette: dict[str, str]) -> None:
    """I messaggi e i comandi che accompagnano l'ultima risposta."""
    for messaggio in st.session_state.messaggi:
        mostra_messaggio(messaggio)
    pulsanti_chiarimento(cliente, etichette)
    riscontro(cliente, comune)
    correzione(cliente, etichette)


def gestisci_invio(cliente: ClienteAPI, inserito, comune: str,
                   etichette: dict[str, str]) -> None:
    """Cosa fare di ciò che l'utente ha appena mandato.

    Tre strade, in ordine di precedenza. La **foto** vince sempre: se c'è, è l'oggetto vero e
    il testo l'accompagna come dettaglio. Poi il **chiarimento** in sospeso, perché lì il
    testo è la risposta a una domanda, non un oggetto nuovo. Altrimenti il testo è il
    **nome dell'oggetto**: si salta il modello di visione e si parte da lì.

    La ricerca testuale non è un ripiego rispetto alla foto: è più veloce di minuti, non
    sbaglia il riconoscimento, e serve a chi l'oggetto non ce l'ha in mano.
    """
    testo = (inserito.text or "").strip()
    allegati = inserito.files or []
    foto = allegati[0] if allegati else None
    contesto = st.session_state.contesto if st.session_state.attende_risposta else None

    if not foto and not contesto and not testo:
        return

    st.session_state.messaggi.append({
        "ruolo": "utente", "testo": testo or None,
        "immagine": foto.getvalue() if foto else None})

    if foto:
        chiedi(etichette, cliente.analizza, foto.getvalue(), foto.name, comune, testo or None)
    elif contesto:
        chiedi(etichette, cliente.continua, contesto, testo)
    else:
        chiedi(etichette, cliente.domanda, comune, testo, None)
    st.rerun()


def principale() -> None:
    st.set_page_config(page_title="EcoScan", page_icon="♻️", layout="centered")
    prepara_stato()
    cliente = ClienteAPI()

    comune = barra_laterale(cliente)
    if not comune:
        st.stop()

    etichette = etichette_destinazioni(cliente.base, comune)
    mostra_conversazione(cliente, comune, etichette)

    inserito = st.chat_input("Scrivi o allega una foto…", accept_file=True,
                             file_type=["jpg", "jpeg", "png", "webp"])
    if inserito:
        gestisci_invio(cliente, inserito, comune, etichette)


def main() -> None:
    """Avvia Streamlit su questo file: `uv run ecoscan-frontend`.

    Dentro un container serve ascoltare su tutte le interfacce, non solo su localhost:
    da qui `--indirizzo`.
    """
    import argparse
    import subprocess
    import sys
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Avvia l'interfaccia di EcoScan.")
    ap.add_argument("--indirizzo", default="localhost",
                    help="in un container: 0.0.0.0, altrimenti non è raggiungibile da fuori")
    ap.add_argument("--porta", type=int, default=8501)
    argomenti = ap.parse_args()

    comando = [sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve()),
               "--server.address", argomenti.indirizzo,
               "--server.port", str(argomenti.porta),
               "--browser.gatherUsageStats", "false"]
    print(f"Frontend in avvio su {argomenti.indirizzo}:{argomenti.porta}. "
          f"Backend atteso su {conf.API}")
    raise SystemExit(subprocess.call(comando))


if __name__ == "__main__":
    principale()
