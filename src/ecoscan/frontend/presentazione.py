"""Come una risposta dell'API diventa un messaggio leggibile.

Sta separato dall'interfaccia perché è la parte che si sbaglia più facilmente e che vale la
pena verificare: una regola di esclusione presentata male dice l'opposto del vero, e il
livello di evidenza dev'essere visibile senza che l'utente debba conoscere il progetto.

Due principi guidano cosa si mostra:

- **i nomi interni non si mostrano.** Le risposte portano il nome con cui la destinazione è
  scritta nei dati (a Torino `carta_e_cartone`); qui si traduce con le etichette che il
  backend espone su `/destinazioni`. Il nome interno resta la chiave, l'etichetta è ciò che
  l'utente legge;
- **ciò che dice il comune resta distinto da ciò che ha capito l'assistente.** Il
  riconoscimento della foto è dell'assistente e può essere sbagliato: si mostra a parte,
  perché l'utente possa correggerlo. La destinazione viene dai dati del comune, e si cita il
  documento da cui arriva.
"""
from __future__ import annotations

from ecoscan import condizioni as condizioni_

VERBO = {"escluso": "**non** va in", "ammesso": "va in"}

SPIEGAZIONE_LIVELLO = {
    1: "Il comune elenca proprio questo oggetto.",
    2: "Il comune non elenca l'oggetto: questa è la regola generale del contenitore.",
    3: "Il comune non dice nulla su questo oggetto.",
}

ETICHETTA_LIVELLO = {1: "voce del dizionario", 2: "regola di categoria", 3: "nessuna regola"}

# Le fonti hanno codici buoni per i dati e illeggibili per una persona
NOME_FONTE = {
    "asia_napoli_dove_lo_butto": "Dizionario \"Dove lo butto\" di ASIA Napoli",
    "asia_napoli_frazioni": "ASIA Napoli, materiali da differenziare",
    "amiat_rifiutologo_2025": "Rifiutologo AMIAT 2025",
}

SICUREZZA = ((0.7, "sicurezza alta"), (0.4, "sicurezza media"), (0.0, "sicurezza bassa"))

MOTIVO_SCELTA = {
    "stesso_oggetto": "è proprio questo oggetto",
    "sinonimo": "è un altro nome dello stesso oggetto",
    "stesso_materiale": "è lo stesso materiale",
    "categoria": "l'oggetto rientra in questa categoria",
}

# Oltre tre alternative la spiegazione torna a leggersi come la tabella di diagnostica da
# cui è nata per allontanarsi
MASSIME_ALTERNATIVE = 3


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


def titolo(risposta: dict, etichette: dict[str, str] | None = None) -> str:
    """La prima riga: dove va, o che non si sa."""
    destinazioni = risposta.get("destinazioni") or []
    if not destinazioni:
        return "Non so dove va questo oggetto."
    verbo = VERBO.get(risposta.get("polarita") or "", "va in")
    oggetto = (risposta.get("oggetto") or "l'oggetto").capitalize()
    nomi = " oppure ".join(etichette_di(destinazioni, etichette))
    return f"{oggetto}: {verbo} **{nomi}**"


def corpo(risposta: dict, etichette: dict[str, str] | None = None) -> str:
    """Il resto del messaggio: condizioni, varianti, avvertenza, livello di evidenza."""
    righe: list[str] = []

    if frase := condizioni_.frase(risposta.get("condizioni") or []):
        righe.append(frase)
    if alternative := altre_varianti(risposta, etichette):
        righe.append(alternative)
    if avvertenza := risposta.get("avvertenza"):
        righe.append(f"⚠️ {avvertenza}")

    livello = risposta.get("livello_evidenza", 3)
    righe.append(SPIEGAZIONE_LIVELLO.get(livello, ""))

    if livello == 3:
        righe.append("Puoi controllare sul sito del comune o portarlo a un centro di raccolta.")
    if risposta.get("contraddizione"):
        righe.append("Attenzione: la fonte del comune indica destinazioni diverse per lo "
                     "stesso caso.")
    if chiarimento := risposta.get("chiarimento"):
        righe.append(f"**{chiarimento}**")

    return "\n\n".join(r for r in righe if r)


def documento_scelto(risposta: dict) -> dict | None:
    """Il candidato da cui viene la risposta. Senza, non si può citare nulla."""
    scelto = risposta.get("scelto_id")
    if not scelto:
        return None
    return next((c for c in risposta.get("candidati") or [] if c.get("id") == scelto), None)


def altre_varianti(risposta: dict, etichette: dict[str, str] | None = None) -> str:
    """Le altre varianti dello stesso oggetto, quando la risposta ne ha scelta una.

    Mostrarle anche dopo la scelta insegna la regola: "se è pulito → Carta e cartone · **se
    è unto → Organico** ✓" vale più di un "vale se è: unto" da solo.
    """
    scelto = documento_scelto(risposta)
    varianti = (scelto or {}).get("varianti") or []
    if len(varianti) < 2:
        return ""
    condizioni_scelte = " e ".join(risposta.get("condizioni") or [])
    pezzi = []
    for variante in varianti:
        condizione = variante.get("condizione")
        dove = " oppure ".join(etichette_di(variante.get("destinazioni") or [], etichette)) or "?"
        premessa = condizioni_.premessa([condizione]) if condizione else ""
        riga = f"{premessa} → {dove}" if premessa else f"negli altri casi → {dove}"
        pezzi.append(f"**{riga}** ✓" if condizione and condizione in condizioni_scelte else riga)
    return "Le varianti di questo oggetto: " + " · ".join(pezzi) + "."


def frase_riconoscimento(risposta: dict) -> str:
    """Cosa ha visto l'assistente nella foto.

    Si mostra sempre, anche quando la risposta è giusta: è il passaggio più fragile della
    catena, e l'utente può accorgersi dell'errore solo se lo vede.
    """
    riconoscimento = risposta.get("riconoscimento") or {}
    oggetto = (riconoscimento.get("oggetto") or "").strip()
    if not oggetto:
        return ""
    dettagli = [d for d in (riconoscimento.get("categoria"),
                            ", ".join(riconoscimento.get("materiali") or []),
                            riconoscimento.get("stato")) if d]
    confidenza = float(riconoscimento.get("confidenza") or 0.0)
    sicurezza = next(parola for soglia, parola in SICUREZZA if confidenza >= soglia)
    coda = f" ({'; '.join(dettagli)})" if dettagli else ""
    return f"👁️ Ho riconosciuto: **{oggetto}**{coda} · {sicurezza}"


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
    """Livello di evidenza e provenienza, sotto la risposta."""
    fonte, riferimento = risposta.get("fonte"), risposta.get("riferimento")
    if not fonte and not riferimento:
        return ""
    livello = ETICHETTA_LIVELLO.get(risposta.get("livello_evidenza", 3), "")
    return " · ".join(p for p in (livello, provenienza(fonte, riferimento)) if p)


def citazione(risposta: dict) -> str:
    """Il testo del comune da cui viene la risposta, parola per parola.

    È la prova che la destinazione non è inventata dal modello: il modello sceglie fra
    documenti esistenti, non li scrive.
    """
    scelto = documento_scelto(risposta)
    if not scelto:
        return ""
    nome = scelto.get("nome") or f"documento di livello {scelto.get('livello', '?')}"
    return f"> {(scelto.get('testo') or '').strip()}\n\n— {nome}"


def perche(risposta: dict) -> str:
    """Perché l'assistente ha scelto quel documento, in una riga."""
    tipo = risposta.get("tipo_corrispondenza") or ""
    pezzi = [MOTIVO_SCELTA.get(tipo, tipo.replace("_", " ")), risposta.get("motivo") or ""]
    testo = " · ".join(p for p in pezzi if p)
    return f"L'ho scelto perché {testo}." if testo else ""


def alternative(risposta: dict, etichette: dict[str, str] | None = None) -> list[str]:
    """Le altre voci considerate e non scelte, con la loro destinazione.

    Servono a rendere visibile che c'era una scelta: senza, la risposta sembra l'unica
    possibile anche quando era in bilico.
    """
    scelto = risposta.get("scelto_id")
    righe = []
    for candidato in risposta.get("candidati") or []:
        if candidato.get("id") == scelto:
            continue
        nome = candidato.get("nome") or (candidato.get("testo") or "")[:60]
        dove = " oppure ".join(etichette_di(candidato.get("destinazioni") or [], etichette))
        righe.append(f"{nome} → {dove}" if dove else nome)
        if len(righe) == MASSIME_ALTERNATIVE:
            break
    return righe


def spiegazione(risposta: dict, etichette: dict[str, str] | None = None) -> str:
    """Il contenuto di "Come ci sono arrivato": citazione, motivo, alternative scartate."""
    parti = [citazione(risposta), perche(risposta)]
    if not documento_scelto(risposta) and risposta.get("candidati"):
        parti.append("Nessuna delle voci trovate corrispondeva all'oggetto.")
    if scartate := alternative(risposta, etichette):
        parti.append("Altre voci che ho considerato e scartato:\n"
                     + "\n".join(f"- {r}" for r in scartate))
    return "\n\n".join(p for p in parti if p)


def messaggio(risposta: dict, etichette: dict[str, str] | None = None) -> str:
    return "\n\n".join(p for p in (titolo(risposta, etichette), corpo(risposta, etichette)) if p)


def riassunto_candidati(risposta: dict, etichette: dict[str, str] | None = None) -> list[dict]:
    """Righe per la tabella dei candidati: la vista tecnica, per chi sviluppa."""
    scelto = risposta.get("scelto_id")
    return [{
        "scelto": "✓" if c.get("id") == scelto else "",
        "livello": c.get("livello"),
        "documento": c.get("testo"),
        "destinazioni": " oppure ".join(etichette_di(c.get("destinazioni") or [], etichette)) or "-",
        "somiglianza": round(c.get("punteggio") or 0.0, 3),
    } for c in risposta.get("candidati") or []]
