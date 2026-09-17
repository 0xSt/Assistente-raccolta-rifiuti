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
    st.session_state.setdefault("contesto", None)      # l'ultimo consegnato dal backend
    st.session_state.setdefault("attende_risposta", False)   # c'è un chiarimento in sospeso
    st.session_state.setdefault("comune", None)


@st.cache_data(ttl=60, show_spinner=False)
def elenco_comuni(base: str) -> list[dict]:
    return ClienteAPI(base).comuni()


@st.cache_data(ttl=600, show_spinner=False)
def etichette_destinazioni(base: str, comune: str) -> dict[str, str]:
    """Nome interno -> nome leggibile. Cambiano solo quando cambiano i dati, quindi si
    chiedono una volta; se il backend non risponde si ripiega sui nomi interni resi
    leggibili, invece di lasciare l'utente senza risposta."""
    try:
        return {d["nome"]: d["etichetta"] for d in ClienteAPI(base).destinazioni(comune)}
    except ErroreBackend:
        return {}


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


def chiedi(cliente: ClienteAPI, etichette: dict[str, str], azione, *argomenti) -> None:
    """Una chiamata al backend, seguita fase per fase.

    L'attesa su CPU dura minuti: invece di uno spinner fermo si scrive cosa sta facendo, e
    appena il modello ha riconosciuto l'oggetto lo si mostra. Se ha visto la cosa sbagliata
    l'utente lo sa subito, senza aspettare il resto per scoprirlo.
    """
    try:
        with st.status("Ci penso… su CPU può volerci qualche minuto",
                       expanded=True) as avanzamento:
            risposta = None
            for evento in azione(*argomenti):
                if riga := presentazione.descrizione_fase(evento):
                    avanzamento.write(riga)
                    avanzamento.update(label=riga)
                if evento["fase"] == "risposta":
                    risposta = evento["risposta"]
                elif evento["fase"] == "errore":
                    raise ErroreBackend(evento.get("dettaglio", "errore del backend"))
            if risposta is None:
                raise ErroreBackend("Il backend ha interrotto la risposta a metà. Riprova.")
            avanzamento.update(label="Fatto", state="complete", expanded=False)
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
    for colonna, opzione in zip(colonne, opzioni):
        if colonna.button(opzione.capitalize(), key=f"opzione-{opzione}", width="stretch"):
            st.session_state.messaggi.append({"ruolo": "utente", "testo": opzione})
            chiedi(cliente, etichette, cliente.continua_a_fasi,
                   st.session_state.contesto, opzione)
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
            chiedi(cliente, etichette, cliente.correggi_a_fasi,
                   st.session_state.contesto, oggetto.strip())
            st.rerun()


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

    etichette = etichette_destinazioni(cliente.base, comune)

    for messaggio in st.session_state.messaggi:
        mostra_messaggio(messaggio)
    pulsanti_chiarimento(cliente, etichette)
    riscontro(cliente, comune)
    correzione(cliente, etichette)

    inserito = st.chat_input("Scrivi o allega una foto…", accept_file=True,
                             file_type=["jpg", "jpeg", "png", "webp"])
    if not inserito:
        return

    testo = (inserito.text or "").strip()
    allegati = inserito.files or []
    contesto = st.session_state.contesto if st.session_state.attende_risposta else None

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

    if foto:
        chiedi(cliente, etichette, cliente.analizza_a_fasi, foto.getvalue(), foto.name, comune,
               testo or None)
    else:
        chiedi(cliente, etichette, cliente.continua_a_fasi, contesto, testo)
    st.rerun()


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
