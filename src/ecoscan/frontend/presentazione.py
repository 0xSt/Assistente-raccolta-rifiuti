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

VERBO = {"escluso": "**non** va in", "ammesso": " "}

# Al livello 1 non si scrive niente: la voce nomina l'oggetto, che è ciò che l'utente si
# aspetta già. Restano i casi in cui la risposta vale **meno** di così, e lì si dichiara.
SPIEGAZIONE_LIVELLO = {
    2: "Il comune non elenca l'oggetto: questa è la regola generale del contenitore.",
    3: "Il comune non dice nulla su questo oggetto.",
}

# Al livello 1 la frase dipende da COME la voce corrisponde: dire "elenca proprio questo
# oggetto" quando la voce è la categoria afferma più di quanto il sistema sappia, e la fonte
# citata rimanda a un altro oggetto. L'utente perde così il motivo per dubitare (D163).
CATEGORIA = "Il comune non elenca proprio questo oggetto, ma la categoria a cui appartiene"


def spiegazione_livello(risposta: dict) -> str:
    """Perché la risposta vale, quando c'è qualcosa da dire.

    Con una corrispondenza per **categoria** si nomina la voce (D199): "ma la categoria a cui
    appartiene" senza dire quale lascia l'utente con un'affermazione che non può controllare,
    ed è proprio il punto in cui la scelta sbaglia più spesso. Con il nome davanti — «la
    regola di *Braccioli, canottini, materassini e altri gonfiabili*» — chiunque vede in un
    secondo se la categoria regge, e per una tavola da surf non regge.
    """
    livello = risposta.get("livello_evidenza", 3)
    if livello != 1:
        return SPIEGAZIONE_LIVELLO.get(livello, "")
    if (risposta.get("tipo_corrispondenza") or "") != "categoria":
        return ""
    voce = (documento_scelto(risposta) or {}).get("nome") or ""
    return f"{CATEGORIA}: la voce è quella di «{voce}»." if voce else f"{CATEGORIA}."


# Quanto fidarsi, come lo vede l'interfaccia: il livello di evidenza smette di essere una
# frase da leggere e diventa il colore del riquadro (D200).
NORMALE, INCERTO, ATTENZIONE = "normale", "incerto", "attenzione"


def tono(risposta: dict) -> str:
    """Che aria deve avere il messaggio.

    `attenzione` quando la fonte si contraddice: è l'unico caso in cui il comune dice due
    cose diverse, e l'utente deve saperlo prima di agire. `incerto` quando la risposta non
    viene dalla voce dell'oggetto — livello 3, livello 2, o livello 1 per categoria: sono i
    casi in cui una persona farebbe bene a controllare. `normale` per il resto.
    """
    if risposta.get("contraddizione"):
        return ATTENZIONE
    if risposta.get("chiarimento"):
        return NORMALE
    livello = risposta.get("livello_evidenza", 3)
    if livello != 1 or (risposta.get("tipo_corrispondenza") or "") == "categoria":
        return INCERTO
    return NORMALE


ETICHETTA_LIVELLO = {1: "voce del dizionario", 2: "regola di categoria", 3: "nessuna regola"}

# Il colore del contenitore è **un dato del comune**, non una decorazione: sta nella tabella
# `destinazione` e arriva da `/destinazioni`. È anche l'informazione con cui una persona
# cerca il bidone per strada, e fra i due comuni non coincide — la carta è blu a Napoli e
# gialla a Torino, il giallo a Napoli è la plastica. Chi si è trasferito sbaglia con
# sicurezza, ed è la dimostrazione visiva di D7: le regole non si prestano fra comuni (D201).
PALLINO = {"marrone": "🟤", "giallo": "🟡", "blu": "🔵", "verde": "🟢",
           "grigio": "⚫", "grigio chiaro": "⚪", "bianco": "⚪", "rosso": "🔴",
           "arancione": "🟠", "viola": "🟣", "nero": "⚫"}

# Dove il colore non c'è (contenitori dedicati, centri, ritiri) il canale dice il **gesto**,
# che è l'altra cosa che una persona vuole sapere a colpo d'occhio: lo butto sotto casa o
# devo prendere la macchina?
SEGNO_CANALE = {"raccolta_ordinaria": "🗑️", "contenitore_dedicato": "📦",
                "centro_raccolta": "🏭", "ritiro_domicilio": "🚚",
                "raccolta_itinerante": "🚐"}

# Le fonti hanno codici buoni per i dati e illeggibili per una persona
NOME_FONTE = {
    "asia_napoli_dove_lo_butto": "Dizionario \"Dove lo butto\" di ASIA Napoli",
    "asia_napoli_frazioni": "ASIA Napoli, materiali da differenziare",
    "amiat_rifiutologo_2025": "Rifiutologo AMIAT 2025",
}

# Oltre due varianti la frase sola non regge e si torna all'elenco
VARIANTI_IN_FRASE = 2


def contenitore(nome: str, etichette: dict | None = None) -> dict:
    """Ciò che si sa di una destinazione: etichetta, colore, canale.

    L'elenco può arrivare in due forme: `{nome: "Etichetta"}`, che è quella storica e quella
    delle prove, oppure `{nome: {"etichetta":…, "colore":…, "canale":…}}`, che è quella che
    passa l'interfaccia da quando mostra anche il colore. Accettarle entrambe evita di
    dover riscrivere ogni chiamata per una decorazione.
    """
    voce = (etichette or {}).get(nome)
    if isinstance(voce, dict):
        return voce
    if isinstance(voce, str):
        return {"etichetta": voce}
    return {}


def etichetta(nome: str, etichette: dict | None = None) -> str:
    """Il nome di una destinazione come va scritto all'utente.

    Senza elenco (backend più vecchio, o chiamata di prova) si ripiega sul nome interno reso
    leggibile: meglio "Carta e cartone" che `carta_e_cartone`, e meglio il nome interno che
    niente.
    """
    if scritta := contenitore(nome, etichette).get("etichetta"):
        return scritta
    leggibile = nome.replace("_", " ").strip()
    return maiuscola(leggibile) if leggibile else nome


def segno(nome: str, etichette: dict | None = None) -> str:
    """Il pallino del colore del contenitore, o l'icona del canale se colore non ne ha."""
    dati = contenitore(nome, etichette)
    colore = (dati.get("colore") or "").strip().lower()
    return PALLINO.get(colore) or SEGNO_CANALE.get(dati.get("canale") or "", "")


def etichette_di(destinazioni: list[str], etichette: dict | None = None) -> list[str]:
    """I nomi da mostrare, ciascuno col suo pallino davanti quando si sa di che colore è."""
    return [" ".join(p for p in (segno(d, etichette), etichetta(d, etichette)) if p)
            for d in destinazioni]


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
    verbo = VERBO.get(risposta.get("polarita") or "", " ")
    nomi = " oppure ".join(etichette_di(destinazioni, etichette))
    condizioni = risposta.get("condizioni") or []
    if apertura := ripresa_di(condizioni, risposto, nomi):
        return f"{apertura} {verbo} **{nomi}**."
    oggetto = maiuscola((risposta.get("oggetto") or "l'oggetto").strip())
    coda = f" {premessa}" if (premessa := condizioni_.premessa(condizioni)) else ""
    return f"{oggetto}: {verbo} **{nomi}**{coda}."


def corpo(risposta: dict, etichette: dict[str, str] | None = None,
          risposto: str | None = None) -> str:
    """Il resto del messaggio: l'altra strada, l'avvertenza, il come, il livello.

    **Dopo una domanda l'altra strada non si scrive** (D219, che riduce D198). Chi ha appena
    risposto «pulito» ha già deciso: l'oggetto ce l'ha in mano, e l'altro ramo è quello che
    ha appena escluso. Rimetterglielo sotto la risposta lo obbliga a rileggere due
    destinazioni per capire quale delle due lo riguarda, che è esattamente il lavoro che la
    domanda gli aveva tolto.

    Resta invece quando la risposta arriva **senza** che sia stata fatta una domanda: lì le
    varianti sono l'unico posto in cui la regola si impara, perché nessuno ha chiesto niente.
    """
    righe: list[str] = []

    if risposto is None and (alternative := altre_varianti(risposta, etichette)):
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
    if not elenco or (len(elenco) == 1 and (elenco[0].get("canale") or "") == ORDINARIO):
        return ""
    if len(elenco) == 1:
        return _una_procedura(elenco[0])
    quante = "due" if len(elenco) == 2 else str(len(elenco))
    return "\n".join([f"**Puoi fare in {quante} modi:**",
                      *(_una_procedura(p, numero) for numero, p in enumerate(elenco, start=1))])


def _una_procedura(procedura: dict, numero: int = 0) -> str:
    """Una procedura come righe di testo. Con `numero` è un'alternativa fra altre, e la
    prima porta l'etichetta: l'ordine per sforzo è già arrivato così dal backend."""
    capo = procedura.get("titolo") or procedura.get("canale", "")
    if numero:
        capo = f"{numero}. {capo}" + ("  ·  *il più comodo*" if numero == 1 else "")
    righe = [capo if numero else f"**{capo}**",
             *(f"   - {passo}" for passo in procedura.get("passi") or [])]
    if nota := procedura.get("nota"):
        righe.append(f"   ℹ️ {nota}")
    return "\n".join(righe)


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


def nota_esecuzione(risposta: dict, secondi: float | None = None) -> str:
    """Il comune a cui la risposta si riferisce, e quanto ci ha messo.

    **Il comune** perché appena in chat ci sono risposte di comuni diversi — ed è
    esattamente ciò che si vuole mostrare, visto che la stessa cosa cambia contenitore — non
    si distingue più a quale delle due si riferisca un messaggio salito di qualche riga. Il
    selettore dice dove si è *adesso*, non dov'era la risposta di prima.

    **Il tempo** perché su CPU sono minuti, e nasconderlo non lo accorcia. Dichiararlo rende
    il costo dell'esecuzione locale una caratteristica misurata invece di un difetto
    imbarazzato, ed è lo stesso numero che la valutazione riporta come p50.
    """
    pezzi = [(risposta.get("comune") or "").strip()]
    if secondi is not None:
        pezzi.append(f"risposto in {secondi:.0f} s")
    return " · ".join(p for p in pezzi if p)


def strade(risposta: dict, etichette: dict[str, str] | None = None) -> str:
    """Tutte le strade possibili, per chi alla domanda non sa rispondere.

    Davanti a «è pulito o unto?» l'utente che non lo sa resta fermo: i due pulsanti non
    hanno una terza via, e chiudere la conversazione è l'unica uscita. Mostrare **entrambi i
    rami** non risponde alla sua domanda — nessuno può farlo al posto suo — ma gli dà ciò
    che gli serve davvero, cioè la regola: guardando l'oggetto capirà da sé in quale ramo
    sta.

    Vale solo quando i rami si leggono dalle varianti del documento scelto, cioè per le
    domande sulla **condizione**. Per quelle sul materiale i rami stanno in voci diverse, e
    ricostruirli qui significherebbe indovinare quale voce risponde a quale materiale: è
    proprio il genere di deduzione che questo progetto tiene fuori dalla presentazione. Chi
    ha l'oggetto in mano, del resto, il materiale lo vede.
    """
    varianti = varianti_di(risposta)
    if len(varianti) < 2:
        return ""
    righe = []
    for variante in varianti:
        condizione = variante.get("condizione")
        premessa = condizioni_.premessa([condizione]) if condizione else ""
        righe.append(f"- {maiuscola(premessa) if premessa else 'Negli altri casi'} → "
                     f"**{dove_va(variante, etichette)}**")
    return "\n".join(["Dipende, e le possibilità sono queste:", *righe])


def messaggio(risposta: dict, etichette: dict[str, str] | None = None,
              risposto: str | None = None) -> str:
    """Il messaggio dell'assistente: una domanda, oppure una risposta.

    `risposto` è ciò che l'utente ha appena detto a una domanda, e serve solo a riprenderlo
    nel titolo: fuori dal chiarimento resta `None`.
    """
    if chiede := domanda(risposta):
        return chiede
    return "\n\n".join(p for p in (titolo(risposta, etichette, risposto),
                                   corpo(risposta, etichette, risposto)) if p)
