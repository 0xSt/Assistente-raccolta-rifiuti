"""Interfaccia a chat: si allega una foto e si riceve una risposta.

"""
from __future__ import annotations

import streamlit as st

from ecoscan import configurazione as conf
from ecoscan.frontend import presentazione
from ecoscan.frontend.cliente import ClienteAPI, ErroreBackend

BENVENUTO = (
    "Ciao! Dimmi un oggetto da buttare e ti dico dove va, secondo le regole del tuo comune.\n\n"
    "Puoi **fotografarlo** con la graffetta qui sotto, oppure **scriverne il nome**. "
    "Se vuoi, aggiungi un dettaglio: \"è vuota\", \"è unto\"."
)

# Quattro esempi da cui partire: uno schermo vuoto non dice cosa si può chiedere, e questi
# quattro lo dimostrano in quattro clic perché portano a **comportamenti diversi** (D202).
# Il secondo rende visibile la ragione per cui l'app esiste: stessa cosa, due comuni, due
# contenitori (D7).
ESEMPI = (
    ("cartone della pizza", "ti fa una domanda"),
    ("bicchiere di vetro", "cambia col comune"),
    ("lavatrice", "non basta il dove"),
    ("tavola da surf", "ammette di non saperlo"),
)


# Lo stato di una conversazione: il nome del campo e il suo valore iniziale. Scriverlo
# qui, una volta, e' cio' che impedisce ad "apri l'app" e "nuova conversazione" di
# divergere — e divergevano gia': il pulsante dimenticava `comune` e in piu' toglieva
# `ultima`, che all'avvio non esiste.
def _conversazione_vuota() -> dict:
    return {"messaggi": [{"ruolo": "assistente", "testo": BENVENUTO}],
            "contesto": None,           # l'ultimo consegnato dal backend
            "attende_risposta": False,  # c'è un chiarimento in sospeso
            "ultima": None}


def prepara_stato() -> None:
    for campo, valore in _conversazione_vuota().items():
        st.session_state.setdefault(campo, valore)
    st.session_state.setdefault("comune", None)


def azzera_conversazione() -> None:
    """Ricomincia da capo, tenendo il comune scelto: e' un'impostazione, non un messaggio."""
    st.session_state.update(_conversazione_vuota())


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


def etichette_destinazioni(base: str, comune: str) -> dict[str, dict]:
    """Nome interno -> come si mostra: etichetta, colore, canale.

    Il **colore** è un dato del comune che finora si buttava via: sta nella tabella
    `destinazione`, `/destinazioni` lo espone, e nessuno lo mostrava. È l'informazione con
    cui una persona cerca il bidone per strada.
    """
    return {d["nome"]: {"etichetta": d["etichetta"], "colore": d.get("colore"),
                        "canale": d.get("canale")}
            for d in elenco_destinazioni(base, comune)}


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
                pallino = presentazione.segno(d["nome"], {d["nome"]: d})
                riga = f"- {pallino} {d['etichetta']}".replace("-  ", "- ")
                if nota := d.get("note"):
                    riga += f" — {nota}"
                st.markdown(riga)


def _selettore_comune(comuni: list[dict]) -> str:
    """Due comuni in un menù a tendina sono due clic per una scelta che si vede tutta: il
    controllo a segmenti li mostra entrambi e ne basta uno."""
    nomi = [c["nome"] for c in comuni]
    comune = st.segmented_control("Comune", nomi, default=nomi[0],
                                  help="Le regole cambiano da comune a comune: "
                                       "la risposta vale solo per quello scelto.") or nomi[0]
    scelto = next(c for c in comuni if c["nome"] == comune)
    st.caption(f"{scelto['gestore']} · {scelto['voci']} voci · {scelto['regole']} regole")
    return comune


def _pannello_servizi(cliente: ClienteAPI) -> None:
    """In fondo e chiuso: è un pannello per chi sviluppa, non per chi butta la spazzatura."""
    with st.expander("Stato dei servizi"):
        try:
            salute = cliente.salute()
            for servizio in ("database", "qdrant", "ollama"):
                st.write(f"{'🟢' if salute[servizio] else '🔴'} {servizio}")
            st.caption(f"{salute.get('schede_indicizzate', '?')} schede · "
                       f"modello {salute['modello_visione']}")
        except ErroreBackend as errore:
            st.error(str(errore))


def barra_laterale(cliente: ClienteAPI) -> str | None:
    """Il comune scelto, o `None` se il backend non risponde: senza comune non c'è risposta."""
    with st.sidebar:
        st.markdown("### ♻️ EcoScan")
        st.caption("Assistente per la raccolta differenziata. Funziona in locale.")
        try:
            comuni = elenco_comuni(cliente.base)
        except ErroreBackend as errore:
            st.error(str(errore))
            return None

        comune = _selettore_comune(comuni)
        st.divider()
        legenda(cliente.base, comune)
        if st.button("Nuova conversazione", width="stretch"):
            azzera_conversazione()
            st.rerun()
        st.divider()
        _pannello_servizi(cliente)
    return comune


# Il livello di evidenza smette di essere una frase in fondo e diventa il riquadro in cui
# la risposta sta: quanto fidarsi si vede prima di leggere (D200).
RIQUADRO = {presentazione.INCERTO: st.info, presentazione.ATTENZIONE: st.warning}

# La terza via davanti a un chiarimento. Non è fra le `opzioni` che manda il backend perché
# non è una risposta alla domanda: è il modo di uscire dalla domanda senza rispondere.
NON_LO_SO = "non lo so"


def mostra_messaggio(messaggio: dict) -> None:
    with st.chat_message("user" if messaggio["ruolo"] == "utente" else "assistant"):
        if immagine := messaggio.get("immagine"):
            st.image(immagine, width=220)
        # cosa ha visto il modello sta PRIMA della risposta: è il passaggio che l'utente
        # deve poter smentire, e dopo la risposta non lo leggerebbe più
        if visto := messaggio.get("riconoscimento"):
            st.caption(visto)
        if testo := messaggio.get("testo"):
            # si sceglie la funzione e POI la si chiama: scritto come espressione
            # condizionale, il valore restituito resta "nudo" nello script e la magia di
            # Streamlit lo stampa — cioè stampa il DeltaGenerator con tutto il suo aiuto
            RIQUADRO.get(messaggio.get("tono") or "", st.markdown)(testo)
        if nota := messaggio.get("nota"):
            st.caption(nota)
        if meta := messaggio.get("meta"):
            st.caption(meta)


def aggiungi_risposta(risposta: dict, etichette: dict[str, dict],
                      risposto: str | None = None, secondi: float | None = None) -> None:
    st.session_state.messaggi.append({
        "ruolo": "assistente",
        "riconoscimento": presentazione.frase_riconoscimento(risposta),
        "testo": presentazione.messaggio(risposta, etichette, risposto),
        "nota": presentazione.nota_fonte(risposta),
        "meta": presentazione.nota_esecuzione(risposta, secondi),
        "tono": presentazione.tono(risposta),
    })
    # il contesto si conserva SEMPRE: serve al chiarimento, ma anche a correggere
    # l'oggetto riconosciuto dopo una risposta già data
    st.session_state.contesto = risposta.get("contesto") or None
    st.session_state.attende_risposta = bool(risposta.get("chiarimento"))
    st.session_state.ultima = risposta


FASI_FOTO = ("guardo la foto", "cerco nel dizionario del comune", "scelgo fra le voci trovate")
FASI_TESTO = ("cerco nel dizionario del comune", "scelgo fra le voci trovate")


def attendi(azione, argomenti: tuple, fasi: tuple[str, ...]) -> tuple[dict, float]:
    """Esegue la chiamata mostrando che il tempo passa, e cosa sta succedendo (D203).

    Su CPU una foto sono minuti, e uno spinner con una scritta ferma non distingue "sta
    lavorando" da "si è piantato": è l'unico punto dell'interfaccia in cui l'utente resta
    solo abbastanza a lungo da chiederselo.

    **Non si finge di sapere a che fase è arrivato.** Il backend risponde una volta sola, e
    inventare un avanzamento a tempo sarebbe una barra di caricamento finta. Si dicono i
    passaggi che farà — che sono tre, e spiegano da soli perché ci mette tanto — e si mostra
    il cronometro, che è l'unica cosa vera che si sappia. La chiamata va in un thread perché
    Streamlit disegna solo dal principale: il thread aspetta la rete, il principale aggiorna
    l'etichetta.
    """
    import concurrent.futures
    import time

    elenco = " · ".join(fasi)
    with st.status(f"Ci penso… {elenco}", expanded=False) as stato:
        inizio = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            lavoro = pool.submit(azione, *argomenti)
            while not lavoro.done():
                time.sleep(0.4)
                stato.update(label=f"Ci penso da {int(time.monotonic() - inizio)}s… {elenco}")
            risposta = lavoro.result()
        secondi = time.monotonic() - inizio
        stato.update(label=f"Fatto in {secondi:.0f}s", state="complete")
    # il tempo esce di qui e finisce sotto la risposta: il riquadro dell'attesa si chiude,
    # e con lui sparirebbe l'unico posto in cui quel numero era scritto
    return risposta, secondi


def chiedi(etichette: dict[str, dict], azione, *argomenti, risposto: str | None = None,
           fasi: tuple[str, ...] = FASI_TESTO) -> None:
    """Una chiamata al backend, con l'attesa e l'errore gestiti una volta sola.

    `risposto` si passa solo quando questo giro nasce da una **domanda** dell'assistente:
    è la parola che la risposta riprenderà in apertura ("Ok, unto: …").
    """
    try:
        risposta, secondi = attendi(azione, argomenti, fasi)
        aggiungi_risposta(risposta, etichette, risposto, secondi)
    except ErroreBackend as errore:
        st.session_state.messaggi.append({"ruolo": "assistente", "testo": f"⚠️ {errore}",
                                          "tono": presentazione.ATTENZIONE})


def pulsanti_chiarimento(cliente: ClienteAPI, etichette: dict[str, dict]) -> None:
    """Le opzioni del chiarimento come pulsanti.

    Le condizioni sono note (vengono dalle varianti del documento), quindi non c'è motivo
    di far indovinare all'utente come si scrivono. Il pulsante manda a /continua lo stesso
    testo che avrebbe scritto: il backend non cambia.

    **«Non lo so» è una via d'uscita, non una risposta.** Chi non sa se il cartone è unto
    non ha modo di proseguire: due pulsanti senza terza via lasciano come unica mossa
    chiudere la conversazione. Il terzo pulsante mostra tutti i rami e **non chiama il
    backend** — la risposta non dipende da altri dati, dipende da un'informazione che ha
    solo l'utente — e lascia la domanda aperta, così dopo aver letto la regola può ancora
    rispondere.
    """
    ultima = st.session_state.get("ultima") or {}
    opzioni = ultima.get("opzioni") or []
    if not (st.session_state.attende_risposta and opzioni):
        return
    tutte = presentazione.strade(ultima, etichette)
    voci = [*opzioni, NON_LO_SO] if tutte else list(opzioni)
    colonne = st.columns(min(len(voci), 4))
    for colonna, voce in zip(colonne, voci, strict=False):
        if not colonna.button(presentazione.maiuscola(voce), key=f"opzione-{voce}",
                              width="stretch"):
            continue
        st.session_state.messaggi.append({"ruolo": "utente", "testo": voce})
        if voce == NON_LO_SO:
            st.session_state.messaggi.append({"ruolo": "assistente", "testo": tutte,
                                              "tono": presentazione.INCERTO})
        else:
            chiedi(etichette, cliente.continua, st.session_state.contesto, voce, risposto=voce)
        st.rerun()


def esempi(cliente: ClienteAPI, etichette: dict[str, dict]) -> None:
    """I pulsanti di `ESEMPI`, finché la conversazione non è cominciata.

    Spariscono al primo messaggio: servono a partire, non a restare.
    """
    if len(st.session_state.messaggi) > 1 or st.session_state.attende_risposta:
        return
    st.caption("Oppure prova con uno di questi:")
    for colonna, (oggetto, cosa) in zip(st.columns(len(ESEMPI)), ESEMPI, strict=False):
        if colonna.button(oggetto, key=f"esempio-{oggetto}", width="stretch", help=cosa):
            st.session_state.messaggi.append({"ruolo": "utente", "testo": oggetto})
            chiedi(etichette, cliente.domanda, st.session_state.comune, oggetto, None)
            st.rerun()


def mostra_conversazione(cliente: ClienteAPI, etichette: dict[str, dict]) -> None:
    """I messaggi e i comandi che accompagnano l'ultima risposta."""
    for messaggio in st.session_state.messaggi:
        mostra_messaggio(messaggio)
    pulsanti_chiarimento(cliente, etichette)
    esempi(cliente, etichette)


def gestisci_invio(cliente: ClienteAPI, inserito, comune: str,
                   etichette: dict[str, dict]) -> None:
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
        chiedi(etichette, cliente.analizza, foto.getvalue(), foto.name, comune, testo or None,
               fasi=FASI_FOTO)
    elif contesto:
        chiedi(etichette, cliente.continua, contesto, testo, risposto=testo)
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
    # nello stato, perché `esempi()` lo legge da lì invece di riceverlo come argomento
    st.session_state.comune = comune

    etichette = etichette_destinazioni(cliente.base, comune)
    mostra_conversazione(cliente, etichette)

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
