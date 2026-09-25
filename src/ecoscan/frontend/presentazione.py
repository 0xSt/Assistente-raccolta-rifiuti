"""Come una risposta dell'API diventa un messaggio leggibile.

Sta separato dall'interfaccia perché è la parte che si sbaglia più facilmente e che vale la
pena verificare: una regola di esclusione presentata male dice l'opposto del vero, e il
livello di evidenza dev'essere visibile senza che l'utente debba conoscere il progetto.

Quattro principi guidano cosa si mostra:

- **i nomi interni non si mostrano.** Le risposte portano il nome con cui la destinazione è
  scritta nei dati (a Torino `carta_e_cartone`); qui si traduce con le etichette che il
  backend espone su `/destinazioni`. Il nome interno resta la chiave, l'etichetta è ciò che
  l'utente legge;
- **ciò che dice il comune resta distinto da ciò che ha capito l'assistente.** Il
  riconoscimento della foto è dell'assistente e può essere sbagliato: si mostra a parte,
  perché l'utente possa correggerlo. La destinazione viene dai dati del comune, e si cita la
  fonte da cui arriva;
- **una cosa si dice una volta sola** (D192). La condizione che ha deciso la risposta stava
  in tre punti — nel riconoscimento, in un "Vale se è unto." tutto suo, e nella riga delle
  varianti: ora sta nel titolo, dove decide qualcosa, e l'altra strada diventa una frase;
- **si parla quando c'è un'eccezione** (D193). Una frase che compare in ogni risposta non
  informa: diventa arredamento che l'occhio salta, e porta con sé quelle che invece
  contavano. "Il comune elenca proprio questo oggetto" era vera nella grande maggioranza dei
  casi, quindi taceva proprio dove serviva. Ora il livello di evidenza si scrive solo quando
  **non** è il caso normale: categoria, livello 2, livello 3.
"""
from __future__ import annotations

from ecoscan import condizioni as condizioni_
from ecoscan.procedure import ORDINARIO

VERBO = {"escluso": "**non** va in", "ammesso": "va in"}

# Al livello 1 non si scrive niente: la voce nomina l'oggetto, che è ciò che l'utente si
# aspetta già. Restano i casi in cui la risposta vale **meno** di così, e lì si dichiara.
SPIEGAZIONE_LIVELLO = {
    2: "Il comune non elenca l'oggetto: questa è la regola generale del contenitore.",
    3: "Il comune non dice nulla su questo oggetto.",
}

# Al livello 1 la frase dipende da COME la voce corrisponde: dire "elenca proprio questo
# oggetto" quando la voce è la categoria afferma più di quanto il sistema sappia, e la fonte
# citata rimanda a un altro oggetto. L'utente perde così il motivo per dubitare (D163).
SPIEGAZIONE_CORRISPONDENZA = {
    "categoria": "Il comune non elenca proprio questo oggetto, ma la categoria a cui "
                 "appartiene.",
}


def spiegazione_livello(risposta: dict) -> str:
    """Perché la risposta vale, quando c'è qualcosa da dire."""
    livello = risposta.get("livello_evidenza", 3)
    if livello == 1:
        return SPIEGAZIONE_CORRISPONDENZA.get(risposta.get("tipo_corrispondenza") or "", "")
    return SPIEGAZIONE_LIVELLO.get(livello, "")


ETICHETTA_LIVELLO = {1: "voce del dizionario", 2: "regola di categoria", 3: "nessuna regola"}

# Le fonti hanno codici buoni per i dati e illeggibili per una persona
NOME_FONTE = {
    "asia_napoli_dove_lo_butto": "Dizionario \"Dove lo butto\" di ASIA Napoli",
    "asia_napoli_frazioni": "ASIA Napoli, materiali da differenziare",
    "amiat_rifiutologo_2025": "Rifiutologo AMIAT 2025",
}

# Oltre due varianti la frase sola non regge e si torna all'elenco
VARIANTI_IN_FRASE = 2


def etichetta(nome: str, etichette: dict[str, str] | None = None) -> str:
    """Il nome di una destinazione come va scritto all'utente.

    Senza elenco (backend più vecchio, o chiamata di prova) si ripiega sul nome interno reso
    leggibile: meglio "Carta e cartone" che `carta_e_cartone`, e meglio il nome interno che
    niente.
    """
    if etichette and nome in etichette:
        return etichette[nome]
    leggibile = nome.replace("_", " ").strip()
    return leggibile[:1].upper() + leggibile[1:] if leggibile else nome


def etichette_di(destinazioni: list[str], etichette: dict[str, str] | None = None) -> list[str]:
    return [etichetta(d, etichette) for d in destinazioni]


def maiuscola(testo: str) -> str:
    """Iniziale maiuscola senza toccare il resto: `capitalize()` abbasserebbe le altre."""
    return testo[:1].upper() + testo[1:]


def ripresa_di(condizioni: list[str], risposto: str | None, destinazioni: str) -> str:
    """"Ok, unto:" — la ripresa di ciò che l'utente ha appena risposto (D196).

    Vale solo quando il messaggio precedente era una **domanda**: è quella parola che fa di
    due messaggi affiancati uno scambio. Si riprende la condizione **applicata**, non le
    parole dell'utente: vengono dai dati del comune, quindi sono sempre scritte bene, anche
    quando lui aveva scritto "è tutta unta". Solo se non c'è nessuna condizione si ripete
    ciò che ha detto, che è l'unica cosa rimasta.

    Non si riprende una parola che è già nel nome del contenitore: "Ok, vetro: va in Vetro"
    è peggio del titolo normale.
    """
    if risposto is None:
        return ""
    detto = ", ".join(c for c in condizioni if c) or (risposto or "").strip()
    if not detto or detto.lower() in destinazioni.lower():
        return ""
    return f"Ok, {detto}:"


def titolo(risposta: dict, etichette: dict[str, str] | None = None,
           risposto: str | None = None) -> str:
    """La prima riga: dove va, a quale condizione, o che non si sa.

    La condizione sta **qui** e non su una riga sua: "va in Organico se è unto" è una frase,
    "va in Organico." seguito da "Vale se è unto." sono due affermazioni che l'utente deve
    rimettere insieme da solo.
    """
    destinazioni = risposta.get("destinazioni") or []
    if not destinazioni:
        return "Non so dove va questo oggetto."
    verbo = VERBO.get(risposta.get("polarita") or "", "va in")
    nomi = " oppure ".join(etichette_di(destinazioni, etichette))
    condizioni = risposta.get("condizioni") or []
    if apertura := ripresa_di(condizioni, risposto, nomi):
        return f"{apertura} {verbo} **{nomi}**."
    oggetto = maiuscola((risposta.get("oggetto") or "l'oggetto").strip())
    coda = f" {premessa}" if (premessa := condizioni_.premessa(condizioni)) else ""
    return f"{oggetto}: {verbo} **{nomi}**{coda}."


def corpo(risposta: dict, etichette: dict[str, str] | None = None) -> str:
    """Il resto del messaggio: l'altra strada, l'avvertenza, il come, il livello.

    L'altra strada si scrive **anche** dopo una domanda (D198): è lì che si impara la regola,
    perché una delle due è la risposta per l'oggetto che si ha in mano. La domanda, che ora è
    solo una domanda, non l'ha anticipata.
    """
    righe: list[str] = []

    if alternative := altre_varianti(risposta, etichette):
        righe.append(alternative)
    if avvertenza := risposta.get("avvertenza"):
        righe.append(f"⚠️ {avvertenza}")

    if passi := procedure(risposta):
        righe.append(passi)

    if spiegazione := spiegazione_livello(risposta):
        righe.append(spiegazione)

    if risposta.get("livello_evidenza", 3) == 3:
        righe.append(ripiego(risposta)
                     or "Puoi controllare sul sito del comune o portarlo a un centro di raccolta.")
    if risposta.get("contraddizione"):
        righe.append("Attenzione: la fonte del comune indica destinazioni diverse per lo "
                     "stesso caso.")

    return "\n\n".join(r for r in righe if r)


def procedure(risposta: dict) -> str:
    """Come si conferisce, quando non basta un sacco.

    Per la raccolta ordinaria non si scrive niente: tutti sanno cos'è un cassonetto, e una
    procedura lì trasformerebbe ogni risposta in un elenco puntato. Il backend la toglie già
    quando ci sono altri canali; **quando è l'unica la toglie questa funzione** (D193), che
    è il caso della maggioranza delle risposte: tre righe uguali sotto ogni oggetto sono la
    definizione di rumore.

    **Quando i canali sono più d'uno** (115 voci a Napoli) diventano alternative numerate e
    ordinate per sforzo: chi legge trova per prima quella che può fare da casa, e solo dopo
    quella che gli chiede di prendere la macchina. L'ordine è il messaggio.
    """
    elenco = risposta.get("procedure") or []
    if len(elenco) == 1 and (elenco[0].get("canale") or "") == ORDINARIO:
        return ""
    if not elenco:
        return ""
    pezzi = []
    if len(elenco) > 1:
        pezzi.append("**Puoi fare in due modi:**" if len(elenco) == 2
                     else f"**Puoi fare in {len(elenco)} modi:**")
    for numero, procedura in enumerate(elenco, start=1):
        capo = procedura.get("titolo") or procedura.get("canale", "")
        if len(elenco) > 1:
            capo = f"{numero}. {capo}" + ("  ·  *il più comodo*" if numero == 1 else "")
        pezzi.append(f"**{capo}**" if len(elenco) == 1 else capo)
        pezzi.extend(f"   - {passo}" for passo in procedura.get("passi") or [])
        if nota := procedura.get("nota"):
            pezzi.append(f"   ℹ️ {nota}")
    return "\n".join(pezzi)


def ripiego(risposta: dict) -> str:
    """Al livello 3: il comune non dice nulla, ma l'oggetto va comunque buttato.

    Non è indovinare la destinazione — quello resterebbe scorretto. È dire **dove si
    chiede**: il centro di raccolta accetta le tipologie che il dizionario non elenca.
    """
    procedura = risposta.get("ripiego")
    if not procedura:
        return ""
    passi = "\n".join(f"   - {p}" for p in procedura.get("passi") or [])
    return "\n".join(filter(None, [
        "Puoi comunque portarlo dove si accettano le tipologie che il dizionario non elenca.",
        f"**{procedura.get('titolo') or 'Centro di raccolta'}**", passi]))


def documento_scelto(risposta: dict) -> dict | None:
    """Il candidato da cui viene la risposta. Senza, non si può dire nulla delle varianti."""
    scelto = risposta.get("scelto_id")
    if not scelto:
        return None
    return next((c for c in risposta.get("candidati") or [] if c.get("id") == scelto), None)


def varianti_di(risposta: dict) -> list[dict]:
    return (documento_scelto(risposta) or {}).get("varianti") or []


def dove_va(variante: dict, etichette: dict[str, str] | None = None) -> str:
    return " oppure ".join(etichette_di(variante.get("destinazioni") or [], etichette)) or "?"


def altre_varianti(risposta: dict, etichette: dict[str, str] | None = None) -> str:
    """Le altre varianti dello stesso oggetto, quando la risposta ne ha scelta una.

    Mostrarle anche dopo la scelta insegna la regola per la volta dopo. **Come** mostrarle
    dipende da quante sono (D192): due varianti sono la stragrande maggioranza, e con due
    rami l'altro è uno solo, quindi si può nominare in una frase — "Se invece è pulito:
    Carta e cartone." Da tre in su la frase non regge e resta l'elenco, che lì è la forma
    giusta perché il confronto è fra più righe.
    """
    varianti = varianti_di(risposta)
    if len(varianti) < 2:
        return ""
    condizioni_scelte = " e ".join(risposta.get("condizioni") or [])
    scelte = [v for v in varianti
              if (v.get("condizione") or "") and v["condizione"] in condizioni_scelte]
    if len(varianti) == VARIANTI_IN_FRASE and len(scelte) == 1:
        altra = next(v for v in varianti if v is not scelte[0])
        apertura = condizioni_.controfattuale(altra.get("condizione") or "") or "negli altri casi"
        return f"{maiuscola(apertura)}: **{dove_va(altra, etichette)}**."
    pezzi = []
    for variante in varianti:
        condizione = variante.get("condizione")
        premessa = condizioni_.premessa([condizione]) if condizione else ""
        riga = f"{premessa} → {dove_va(variante, etichette)}" if premessa \
            else f"negli altri casi → {dove_va(variante, etichette)}"
        pezzi.append(f"**{riga}** ✓" if condizione and condizione in condizioni_scelte else riga)
    return "Le varianti di questo oggetto: " + " · ".join(pezzi) + "."


def domanda(risposta: dict) -> str:
    """Il messaggio quando l'assistente chiede, che è **solo** la domanda (D194, D198).

    Prima la domanda era l'ultima riga di una risposta completa: l'utente leggeva una
    destinazione, delle procedure e una fonte, e solo in fondo scopriva che non era una
    risposta. Chi si fermava prima portava via un contenitore che l'assistente non si sentiva
    di garantire — e la metrica `domanda_dovuta` lo contava come un successo.

    **Nemmeno la posta in gioco** (D198). Elencare prima i due contenitori fra cui cambia la
    risposta sembrava spiegare la domanda; in realtà la anticipava, e davanti a due pulsanti
    che portano le stesse parole della domanda non c'è niente da spiegare. Le due strade si
    imparano meglio **dopo**, sotto la risposta, dove una è quella giusta per l'oggetto che
    si ha in mano.

    Se chiede, chiede: una riga e i pulsanti.
    """
    testo = risposta.get("chiarimento")
    return f"**{testo}**" if testo else ""


def frase_riconoscimento(risposta: dict) -> str:
    """Cosa ha visto l'assistente nella foto.

    Si mostra sempre, anche quando la risposta è giusta: è il passaggio più fragile della
    catena, e l'utente può accorgersi dell'errore solo se lo vede. Ma si mostra **ciò che
    lui può smentire**, non i campi del riconoscimento (D195): la categoria è una parola di
    tassonomia che nessuno userebbe, e la confidenza è un giudizio che l'assistente dà su di
    sé e su cui l'utente non può fare niente — quando è troppo bassa il sistema chiede già di
    rifare la foto, che è la forma utile della stessa informazione.

    Restano l'oggetto, lo stato — la cosa più facile da sbagliare e quella che più spesso
    cambia il contenitore — e i materiali **solo se hanno deciso**, cioè se compaiono fra le
    condizioni applicate: è il caso degli omonimi, "bicchiere" di vetro contro di plastica.
    """
    riconoscimento = risposta.get("riconoscimento") or {}
    oggetto = (riconoscimento.get("oggetto") or "").strip()
    if not oggetto:
        return ""
    applicate = {c.lower() for c in risposta.get("condizioni") or []}
    dettagli = [d for d in [(riconoscimento.get("stato") or "").strip()] if d]
    dettagli += [m for m in riconoscimento.get("materiali") or []
                 if m.lower() in applicate and m.lower() not in {d.lower() for d in dettagli}]
    coda = f", {', '.join(dettagli)}" if dettagli else ""
    return f"Ho riconosciuto: **{oggetto}**{coda}"


def provenienza(fonte: str | None, riferimento: str | None) -> str:
    """Da dove viene la regola: un link se la fonte è una pagina, altrimenti il documento.

    Tre casi, e vanno tenuti distinti: l'URL di una voce di Napoli diventa un link; il
    riferimento di Torino nomina già il documento ("Rifiutologo AMIAT 2025, pagina 17") e
    ripetere il nome lo direbbe due volte; negli altri casi nome e riferimento si affiancano.
    """
    nome = NOME_FONTE.get(fonte or "", (fonte or "").replace("_", " "))
    riferimento = riferimento or ""
    if riferimento.startswith(("http://", "https://")):
        return f"[{nome or 'apri la fonte'}]({riferimento})"
    if nome and riferimento.lower().startswith(nome.lower()):
        return riferimento
    return " · ".join(p for p in (nome, riferimento) if p)


def nota_fonte(risposta: dict) -> str:
    """Livello di evidenza e provenienza, sotto la risposta.

    Sotto una **domanda** non si scrive: non c'è ancora niente di cui dichiarare la fonte, e
    una nota di provenienza darebbe alla domanda l'aria di una risposta.
    """
    if risposta.get("chiarimento"):
        return ""
    fonte, riferimento = risposta.get("fonte"), risposta.get("riferimento")
    if not fonte and not riferimento:
        return ""
    livello = ETICHETTA_LIVELLO.get(risposta.get("livello_evidenza", 3), "")
    return " · ".join(p for p in (livello, provenienza(fonte, riferimento)) if p)


def messaggio(risposta: dict, etichette: dict[str, str] | None = None,
              risposto: str | None = None) -> str:
    """Il messaggio dell'assistente: una domanda, oppure una risposta.

    `risposto` è ciò che l'utente ha appena detto a una domanda, e serve solo a riprenderlo
    nel titolo: fuori dal chiarimento resta `None`.
    """
    if chiede := domanda(risposta):
        return chiede
    return "\n\n".join(p for p in (titolo(risposta, etichette, risposto),
                                   corpo(risposta, etichette)) if p)
