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
    "Ciao! Fotografa un oggetto da buttare e ti dico dove va, secondo le regole del tuo comune.\n\n"
    "Allega la foto con la graffetta qui sotto. Se vuoi, aggiungi un dettaglio: "
    "\"è vuota\", \"è unto\"."
)


def prepara_stato() -> None:
    st.session_state.setdefault("messaggi", [{"ruolo": "assistente", "testo": BENVENUTO}])
    st.session_state.setdefault("contesto", None)      # presente solo dopo un chiarimento
    st.session_state.setdefault("comune", None)


@st.cache_data(ttl=60, show_spinner=False)
def elenco_comuni(base: str) -> list[dict]:
    return ClienteAPI(base).comuni()


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
        if messaggio.get("testo"):
            st.markdown(messaggio["testo"])
        if nota := messaggio.get("nota"):
            st.caption(nota)
        if candidati := messaggio.get("candidati"):
            with st.expander("Come ci sono arrivato"):
                st.dataframe(candidati, hide_index=True, width="stretch")


def aggiungi_risposta(risposta: dict) -> None:
    st.session_state.messaggi.append({
        "ruolo": "assistente",
        "testo": presentazione.messaggio(risposta),
        "nota": presentazione.nota_fonte(risposta),
        "candidati": presentazione.riassunto_candidati(risposta),
    })
    # il contesto si conserva solo se serve una risposta dell'utente
    st.session_state.contesto = risposta.get("contesto") if risposta.get("chiarimento") else None
    st.session_state.ultima = risposta


def riscontro(cliente: ClienteAPI, comune: str) -> None:
    """Due bottoni: ogni giudizio è un esempio etichettato per la valutazione futura."""
    ultima = st.session_state.get("ultima")
    if not ultima or not ultima.get("destinazioni"):
        return
    sinistra, destra, _ = st.columns([1, 1, 6])
    oggetto = (ultima.get("riconoscimento") or {}).get("oggetto")
    if sinistra.button("👍", help="La risposta è giusta"):
        cliente.riscontro(comune, True, oggetto=oggetto, contesto=ultima.get("contesto", {}))
        st.toast("Grazie, annotato.")
    if destra.button("👎", help="La risposta è sbagliata"):
        cliente.riscontro(comune, False, oggetto=oggetto, contesto=ultima.get("contesto", {}))
        st.toast("Grazie, annotato: servirà a migliorare l'assistente.")


def principale() -> None:
    st.set_page_config(page_title="EcoScan", page_icon="♻️", layout="centered")
    prepara_stato()
    cliente = ClienteAPI()

    comune = barra_laterale(cliente)
    if not comune:
        st.stop()

    for messaggio in st.session_state.messaggi:
        mostra_messaggio(messaggio)
    riscontro(cliente, comune)

    inserito = st.chat_input("Scrivi o allega una foto…", accept_file=True,
                             file_type=["jpg", "jpeg", "png", "webp"])
    if not inserito:
        return

    testo = (inserito.text or "").strip()
    allegati = inserito.files or []
    contesto = st.session_state.contesto

    if not allegati and not contesto:
        st.session_state.messaggi.append({"ruolo": "utente", "testo": testo})
        st.session_state.messaggi.append({
            "ruolo": "assistente",
            "testo": "Per rispondere con sicurezza mi serve una foto dell'oggetto: "
                     "allegala con la graffetta qui sotto."})
        st.rerun()

    foto = allegati[0] if allegati else None
    st.session_state.messaggi.append({
        "ruolo": "utente", "testo": testo or None,
        "immagine": foto.getvalue() if foto else None})

    try:
        with st.spinner("Guardo la foto… su CPU può volerci qualche minuto"):
            if foto:
                risposta = cliente.analizza(foto.getvalue(), foto.name, comune, testo or None)
            else:
                risposta = cliente.continua(contesto, testo)
        aggiungi_risposta(risposta)
    except ErroreBackend as errore:
        st.session_state.messaggi.append({"ruolo": "assistente", "testo": f"⚠️ {errore}"})
    st.rerun()


def main() -> None:
    """Avvia Streamlit su questo file: `uv run ecoscan-frontend`."""
    import subprocess
    import sys
    from pathlib import Path

    comando = [sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve()),
               "--browser.gatherUsageStats", "false"]
    print(f"Frontend in avvio. Backend atteso su {conf.API}")
    raise SystemExit(subprocess.call(comando))


if __name__ == "__main__":
    principale()
