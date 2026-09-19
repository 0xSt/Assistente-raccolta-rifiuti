"""I documenti: ciò che viene indicizzato e restituito dalla ricerca.

Sostituiscono le vecchie "schede", che erano frammenti di due o tre parole in italiano
storto ("Scarpe utilizzabile", "Carta unto"). Un embedding calcolato su un frammento del
genere discrimina male, e la ricerca ne risentiva.

Tre tipi, con ruoli diversi:

- **oggetto** — uno per ogni oggetto del dizionario, con TUTTE le sue varianti insieme.
  "Cartone per pizze" è un documento solo, che dice dove va se è pulito e dove se è unto.
  Il modello deve così riconoscere l'oggetto, non la variante: la variante la sceglie il
  codice in base alla condizione dichiarata, o la si chiede.
- **regola** — una per ogni voce delle regole di categoria (livello 2), corta e specifica,
  con la polarità dentro la frase: "Nella carta NON va la carta con residui di cibo".
  Restano separate e brevi perché è così che si trovano: un testo lungo che mescola ammessi
  ed esclusi produce un embedding medio che non somiglia a nulla.
- **destinazione** — un testo per contenitore, che NON si indicizza: serve a spiegare la
  risposta quando si arriva al livello 2.

Il testo contiene anche le destinazioni: serve a cercare. La risposta però si legge dal
payload strutturato, mai dal testo.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, dataclass, field

from ecoscan import configurazione as conf

TIPI = ("oggetto", "regola", "destinazione")


@dataclass
class Variante:
    """Un modo di essere dell'oggetto e dove va di conseguenza."""

    condizioni: list[str]
    destinazioni: list[str]
    avvertenza: str | None = None
    voce_id: int | None = None
    slug: str | None = None
    codice_materiale: str | None = None

    @property
    def chiave(self) -> tuple:
        """Due varianti con stesse condizioni e stessa destinazione sono la stessa cosa."""
        return (tuple(sorted(self.condizioni)), tuple(self.destinazioni))

    @property
    def condizione(self) -> str | None:
        """Forma breve, per il payload e per i confronti con ciò che dice l'utente."""
        return " e ".join(self.condizioni) if self.condizioni else None


@dataclass
class Documento:
    id: str
    comune: str
    tipo: str
    testo: str                       # ciò che viene vettorizzato
    livello: int | None = None       # 1 oggetto, 2 regola, None destinazione
    nome: str | None = None
    indicizzabile: bool = True
    varianti: list[Variante] = field(default_factory=list)
    alias: list[str] = field(default_factory=list)
    codice_materiale: str | None = None
    polarita: str | None = None      # solo per le regole
    destinazione: str | None = None  # solo per regole e destinazioni
    fonte: str | None = None
    riferimento: str | None = None
    contraddizione: bool = False     # la fonte dà risposte diverse per lo stesso caso

    def payload(self) -> dict:
        """Ciò che accompagna il vettore: da qui si compone la risposta, non dal testo."""
        dati = asdict(self)
        dati["varianti"] = [{**asdict(v), "condizione": v.condizione} for v in self.varianti]
        return dati


# --------------------------------------------------------------------------- frasi

def leggibile(nome: str) -> str:
    """I nomi interni delle destinazioni di Torino sono chiavi ("carta_e_cartone").

    Nel testo indicizzato vanno scritte come si leggono: il modello di embedding lavora sul
    linguaggio, non sui nostri identificatori. Nel payload resta il nome originale, che è
    quello con cui si risponde.
    """
    return nome.replace("_", " ")


def _maiuscola(frase: str) -> str:
    """Solo la prima lettera: `capitalize()` minuscolerebbe tutto il resto, compresi i nomi
    propri dei contenitori."""
    return frase[0].upper() + frase[1:] if frase else frase


def _elenco(voci: list[str], congiunzione: str = "oppure") -> str:
    voci = [v for v in voci if v]
    if len(voci) <= 1:
        return voci[0] if voci else ""
    return f"{', '.join(voci[:-1])} {congiunzione} {voci[-1]}"


def frase_varianti(varianti: list[Variante]) -> str:
    """Da dove va l'oggetto a una frase leggibile.

    Con una variante sola: "Va nella Carta e Cartoncino."
    Con più varianti: "Se è pulito va nella Carta e Cartoncino; se è unto va nell'Organico."
    """
    if not varianti:
        return ""
    # Se tutte le varianti finiscono nello stesso posto, la condizione non cambia la
    # risposta: dirla sarebbe rumore. "Di norma va in Organico; se è spento va in Organico"
    # diventa "Va in Organico". Le CLAUSOLE però restano, perché limitano l'ammissibilità:
    # "solo in piccole quantità" non è un dettaglio superfluo.
    destinazioni = {tuple(v.destinazioni) for v in varianti}
    if len(destinazioni) == 1 and not any(_clausole_di(v) for v in varianti):
        return f"Va in {_elenco([leggibile(d) for d in varianti[0].destinazioni])}."
    return _maiuscola("; ".join(_frase_variante(v) for v in varianti)) + "."


# Alcune "condizioni" non sono aggettivi ma clausole di ammissibilità: "solo se certificato
# compostabile". Messe insieme agli aggettivi producono frasi storte come "se è solo se
# compostabile certificato e sporco".
INIZI_DI_CLAUSOLA = ("solo ", "non ha ", "contenitore ", "contenitori ", "privata ", "anche ")
# Anche le quantità sono clausole: "se è piccole quantità" non è italiano,
# "ma solo in piccole quantità" sì.
INIZI_DI_QUANTITA = ("piccole ", "grandi ", "grosse ")


def _clausola(condizione: str) -> str:
    minuscola = condizione.lower()
    if minuscola.startswith(INIZI_DI_QUANTITA):
        return f"solo in {condizione}"
    if minuscola.startswith(("contenitore ", "contenitori ")):
        return f"solo i {condizione}"
    return condizione


def _clausole_di(v: Variante) -> list[str]:
    inizi = INIZI_DI_CLAUSOLA + INIZI_DI_QUANTITA
    return [_clausola(c) for c in v.condizioni if c.lower().startswith(inizi)]


def _frase_variante(v: Variante) -> str:
    dove = _elenco([leggibile(d) for d in v.destinazioni])
    inizi = INIZI_DI_CLAUSOLA + INIZI_DI_QUANTITA
    clausole = _clausole_di(v)
    aggettivi = [c for c in v.condizioni if not c.lower().startswith(inizi)]

    if not aggettivi:
        frase = f"di norma va in {dove}"
    elif len(aggettivi) == 1 and aggettivi[0].lower().startswith("non "):
        # "se è non utilizzabile" non è italiano: "se non è utilizzabile" sì
        frase = f"se non è {aggettivi[0][4:]} va in {dove}"
    else:
        frase = f"se è {_elenco(aggettivi, 'e')} va in {dove}"
    return f"{frase}, ma {_elenco(clausole, 'e')}" if clausole else frase


def unisci_varianti(varianti: list[Variante]) -> list[Variante]:
    """Fonde le varianti indistinguibili.

    "Simbolo GL o GLS" esiste tre volte, per i codici 70, 71 e 72, ma tutte e tre vanno nel
    vetro: senza unirle il testo direbbe tre volte la stessa cosa.
    """
    unite: dict[tuple, Variante] = {}
    for v in varianti:
        if (esistente := unite.get(v.chiave)) is None:
            unite[v.chiave] = v
        else:
            esistente.avvertenza = esistente.avvertenza or v.avvertenza
    return list(unite.values())


def testo_oggetto(nome: str, varianti: list[Variante], alias: list[str],
                  codici: list[str] | None = None, contraddizione: bool = False,
                  arricchimento: list[str] | None = None) -> str:
    righe = [f"{nome}."]
    if alias:
        righe.append(f"Chiamato anche: {', '.join(alias)}.")
    if codici:
        etichetta = "Codici del materiale" if len(codici) > 1 else "Codice del materiale"
        righe.append(f"{etichetta} sull'imballaggio: {', '.join(codici)}.")
    righe.append(frase_varianti(varianti))
    if contraddizione:
        righe.append("Il comune indica destinazioni diverse per lo stesso caso: "
                     "la fonte non è univoca.")
    avvertenze = [v.avvertenza for v in varianti if v.avvertenza]
    righe.extend(dict.fromkeys(avvertenze))
    # L'arricchimento va in coda: il nome e la destinazione restano le prime parole del
    # documento, che è ciò che l'embedding pesa di più.
    righe.extend(arricchimento or [])
    return " ".join(r for r in righe if r)


# --------------------------------------------------------- arricchimento dalla fonte

"""Perché arricchire, e perché *non* con un modello.

I documenti oggetto sono corti — 65 caratteri di media — e questo è il caso in cui
l'espansione del documento aiuta di più: più parole, più modi di arrivarci. La tentazione è
farle scrivere a un modello ("descrivi un bicchiere di vetro"), ed è una cattiva idea qui
per due motivi.

Il primo è di verità: a Napoli il bicchiere di vetro **non è riciclabile**, e qualunque
modello, descrivendolo, direbbe il contrario — perché è vero quasi ovunque. Quella frase
finirebbe nel testo indicizzato e nell'elenco che legge il modello di scelta, cioè
esattamente dove il progetto ha deciso che la regola arriva solo dai dati (D9).

Il secondo è di discriminazione: descritti da un modello, "Bicchiere di vetro" e "Bottiglia
in vetro" diventano *più simili fra loro*, e vanno in contenitori diversi. Il difetto che
questo sistema deve combattere non è la povertà semantica, è la confusione fra vicini.

L'arricchimento dalla fonte fa lo stesso lavoro con dati che ci sono già:

- il **canale**, quando non è la raccolta ordinaria: è il gesto che l'utente deve compiere,
  e la ragione per cui "Numero Verde Gratuito" da solo non dice niente;
- i **flussi di materiale** della destinazione, ma solo le parole che il testo non ha già:
  è ciò che dà a "Numero Verde Gratuito" la parola "ingombranti";
- le **regole di categoria che nominano l'oggetto**. È la parte che vale di più, perché
  *allontana* i vicini invece di avvicinarli: al bicchiere di vetro di Napoli aggancia
  "Nel contenitore Vetro NON va: Bicchieri", che è esattamente la frase per cui quella voce
  non sta nel vetro.
"""

# Preposizioni e articoli: non dicono nulla sull'oggetto. Duplicano l'elenco di
# `agente/recupero.py` invece di importarlo perché il livello dei dati non dipende da
# quello del ragionamento (vedi le regole di dipendenza in docs/architettura.md).
PAROLE_DI_SERVIZIO = {"di", "in", "da", "del", "della", "dei", "degli", "delle", "e", "o",
                      "con", "per", "a", "al", "alla", "il", "lo", "la", "i", "gli", "le",
                      "un", "uno", "una", "altri", "altre", "anche"}

GESTI = {"centro_raccolta": "Si porta al centro di raccolta.",
         "ritiro_domicilio": "Si prenota il ritiro a domicilio.",
         "raccolta_itinerante": "Si porta a un punto di raccolta itinerante.",
         "contenitore_dedicato": "Si conferisce in un contenitore dedicato."}

# I codici di flusso sono chiavi ("raee"): nel testo vanno scritte come le direbbe una
# persona, perché è su quelle parole che l'utente cerca.
NOMI_FLUSSO = {"raee": "apparecchiatura elettrica o elettronica",
               "tessili": "tessile o abbigliamento", "oli": "olio esausto",
               "ingombranti": "ingombrante", "residuo": "residuo indifferenziato"}


def _radice(parola: str) -> str:
    """Toglie la vocale finale alle parole lunghe: la fonte scrive "Bicchieri" e la voce
    "Bicchiere di vetro"."""
    return parola[:-1] if len(parola) >= 5 and parola[-1] in "aeio" else parola


def parole(testo: str) -> set[str]:
    return {_radice(p) for p in re.findall(r"[a-zà-ù0-9]+", (testo or "").lower())
            if p not in PAROLE_DI_SERVIZIO}


def regole_che_nominano(nome: str, regole: list[tuple[str, str, str]],
                        massimo: int = 2) -> list[tuple[str, str, str]]:
    """Le regole di categoria che parlano proprio di questo oggetto.

    Il criterio è stretto: **tutte** le parole significative del nome devono comparire nella
    regola, contando anche il nome del contenitore, perché la regola si legge come "Nel
    contenitore Vetro NON va: Bicchieri" e il materiale sta lì. È lo stesso principio di
    D159 — precisione prima di copertura — e la ragione è la stessa: un arricchimento che
    aggancia la regola sbagliata peggiora il recupero invece di migliorarlo.

    Le voci dal nome di una parola sola ("Carta", "Abito") non si agganciano mai: con un
    token solo il criterio non discrimina più niente e "Carta" prenderebbe sette regole,
    compresa una sui fondi di caffè.

    Le esclusioni vengono prima: sono quelle che spiegano perché un oggetto *non* sta dove
    ci si aspetterebbe, cioè l'informazione che il nome da solo non porta.
    """
    cercate = parole(nome)
    if len(cercate) < 2:
        return []
    trovate = [r for r in regole if cercate <= parole(f"{r[2]} {r[0].replace('_', ' ')}")]
    return sorted(trovate, key=lambda r: r[1] != "escluso")[:massimo]


def arricchimento_da_fonte(nome: str, varianti: list[Variante], canali: dict[str, str],
                           flussi: dict[str, list[str]],
                           regole: list[tuple[str, str, str]], testo_base: str) -> list[str]:
    """Le frasi in più da aggiungere al documento, tutte ricavate dai dati."""
    destinazioni = list(dict.fromkeys(d for v in varianti for d in v.destinazioni))
    righe = []

    # il gesto, solo quando non è il cassonetto sotto casa: dirlo per la raccolta ordinaria
    # aggiungerebbe la stessa frase a metà del corpus, che è rumore identico per tutti (D167)
    gesti = dict.fromkeys(GESTI[canali[d]] for d in destinazioni
                          if canali.get(d) in GESTI)
    righe.extend(gesti)

    # i flussi, ma solo le parole che il testo non ha già: "Plastica e Metalli" non ha
    # bisogno che gli si dica che riguarda plastica e metalli
    presenti = parole(testo_base + " " + " ".join(righe))
    nuovi = dict.fromkeys(
        NOMI_FLUSSO.get(f, f) for d in destinazioni for f in flussi.get(d, [])
        if not parole(NOMI_FLUSSO.get(f, f)) <= presenti)
    if nuovi:
        righe.append(f"Tipo di rifiuto: {', '.join(nuovi)}.")

    # le regole che nominano l'oggetto: la parte che separa i vicini invece di avvicinarli
    righe.extend(testo_regola(destinazione, polarita, testo, None)
                 for destinazione, polarita, testo in regole_che_nominano(nome, regole))
    return righe


def testo_regola(destinazione: str, polarita: str, testo: str, dettaglio: str | None) -> str:
    """La polarità sta DENTRO la frase: una regola di esclusione letta senza il "non" dice
    l'opposto del vero, e l'embedding non conosce il nostro campo `polarita`."""
    verbo = {"ammesso": "va", "escluso": "NON va"}.get(polarita, "riguarda")
    frase = f"Nel contenitore {leggibile(destinazione)} {verbo}: {testo.rstrip('.')}."
    return f"{frase} {dettaglio}" if dettaglio else frase


def testo_destinazione(nome: str, canale: str, colore: str | None, ammessi: list[str],
                       esclusi: list[str], note: list[str]) -> str:
    canali = {"raccolta_ordinaria": "contenitore della raccolta ordinaria",
              "contenitore_dedicato": "contenitore dedicato",
              "centro_raccolta": "centro di raccolta",
              "raccolta_itinerante": "punto di raccolta itinerante",
              "ritiro_domicilio": "ritiro a domicilio su prenotazione"}
    righe = [f"{leggibile(nome)}: {canali.get(canale, canale)}"
             + (f", colore {colore}." if colore else ".")]
    if ammessi:
        righe.append(f"Ci vanno: {'; '.join(ammessi)}.")
    if esclusi:
        righe.append(f"NON ci vanno: {'; '.join(esclusi)}.")
    righe.extend(note)
    return " ".join(righe)


# --------------------------------------------------------------------------- costruzione

def _varianti_per_oggetto(db: sqlite3.Connection) -> dict[tuple[str, str], list[Variante]]:
    codici = _codici(db)
    righe = db.execute("""
        SELECT c.nome, v.nome, v.id, v.slug, v.avvertenza,
               (SELECT group_concat(vc.condizione, '|') FROM voce_condizione vc
                 WHERE vc.voce_id = v.id ORDER BY vc.condizione),
               (SELECT group_concat(d.nome, '|') FROM voce_destinazione vd
                  JOIN destinazione d ON d.id = vd.destinazione_id
                 WHERE vd.voce_id = v.id ORDER BY vd.ordine)
        FROM voce v JOIN comune c ON c.id = v.comune_id
        ORDER BY c.nome, v.nome, v.id""").fetchall()
    per_oggetto: dict[tuple[str, str], list[Variante]] = {}
    for comune, nome, voce_id, slug, avvertenza, condizioni, destinazioni in righe:
        codice = codici.get(voce_id)
        per_oggetto.setdefault((comune, nome), []).append(Variante(
            condizioni=condizioni.split("|") if condizioni else [],
            destinazioni=destinazioni.split("|") if destinazioni else [],
            avvertenza=avvertenza, voce_id=voce_id, slug=slug, codice_materiale=codice))
    return per_oggetto


def _alias_per_voce(db: sqlite3.Connection) -> dict[int, list[str]]:
    per_voce: dict[int, list[str]] = {}
    for voce_id, alias in db.execute("SELECT voce_id, alias FROM voce_alias ORDER BY alias"):
        per_voce.setdefault(voce_id, []).append(alias)
    return per_voce


def _provenienza(db: sqlite3.Connection) -> dict[int, tuple[str | None, str | None]]:
    """Fonte e riferimento di ogni voce: è ciò che permette a una risposta di livello 1 di
    dire da dove viene, e all'interfaccia di offrire il link alla pagina del comune."""
    return {voce_id: (fonte, riferimento) for voce_id, fonte, riferimento in db.execute(
        "SELECT id, fonte, riferimento FROM voce")}


def _codici(db: sqlite3.Connection) -> dict[int, str]:
    return dict(db.execute(
        "SELECT id, codice_materiale FROM voce WHERE codice_materiale IS NOT NULL").fetchall())


def _chiave(comune: str, nome: str) -> str:
    piatto = "".join(c if c.isalnum() else "-" for c in nome.lower()).strip("-")
    return f"oggetto:{comune}:{piatto}"


def _canali_e_flussi(db: sqlite3.Connection) -> tuple[dict, dict]:
    """Canale e flussi di materiale di ogni destinazione, per comune."""
    canali, flussi = {}, {}
    for comune, nome, canale in db.execute(
            "SELECT c.nome, d.nome, d.canale FROM destinazione d "
            "JOIN comune c ON c.id = d.comune_id"):
        canali[(comune, nome)] = canale
    for comune, nome, flusso in db.execute(
            "SELECT c.nome, d.nome, f.flusso_codice FROM destinazione_flusso f "
            "JOIN destinazione d ON d.id = f.destinazione_id "
            "JOIN comune c ON c.id = d.comune_id ORDER BY f.flusso_codice"):
        flussi.setdefault((comune, nome), []).append(flusso)
    return canali, flussi


def _regole_per_comune(db: sqlite3.Connection) -> dict[str, list[tuple[str, str, str]]]:
    per_comune: dict[str, list[tuple[str, str, str]]] = {}
    for comune, destinazione, polarita, testo in db.execute("""
            SELECT c.nome, d.nome, r.polarita, r.testo FROM regola r
              JOIN destinazione d ON d.id = r.destinazione_id
              JOIN comune c ON c.id = d.comune_id
             WHERE r.polarita IN ('ammesso', 'escluso') ORDER BY r.id"""):
        per_comune.setdefault(comune, []).append((destinazione, polarita, testo))
    return per_comune


def documenti_oggetto(db: sqlite3.Connection, arricchisci: bool | None = None) -> list[Documento]:
    arricchisci = conf.ARRICCHIMENTO if arricchisci is None else arricchisci
    alias_per_voce = _alias_per_voce(db)
    provenienza = _provenienza(db)
    canali, flussi = _canali_e_flussi(db)
    regole_comune = _regole_per_comune(db)
    documenti = []
    for (comune, nome), tutte in _varianti_per_oggetto(db).items():
        alias = list(dict.fromkeys(a for v in tutte for a in alias_per_voce.get(v.voce_id, [])))
        codici = list(dict.fromkeys(v.codice_materiale for v in tutte if v.codice_materiale))
        varianti = unisci_varianti(tutte)

        # due varianti indistinguibili ma con destinazioni diverse: la fonte si contraddice
        per_condizione: dict[tuple, set[tuple[str, ...]]] = {}
        for v in tutte:
            per_condizione.setdefault(tuple(sorted(v.condizioni)), set()).add(tuple(v.destinazioni))
        contraddizione = any(len(d) > 1 for d in per_condizione.values())

        # più voci fuse in un oggetto solo: si cita la prima che dichiara una provenienza,
        # perché il documento è uno e il link dev'essere uno
        fonte, riferimento = next(
            (p for v in tutte if any(p := provenienza.get(v.voce_id, (None, None)))),
            (None, None))

        base = testo_oggetto(nome, varianti, alias, codici, contraddizione)
        arricchimento = arricchimento_da_fonte(
            nome, varianti,
            {d: canali.get((comune, d), "") for v in varianti for d in v.destinazioni},
            {d: flussi.get((comune, d), []) for v in varianti for d in v.destinazioni},
            regole_comune.get(comune, []), base) if arricchisci else []

        documenti.append(Documento(
            id=_chiave(comune, nome), comune=comune, tipo="oggetto", livello=1, nome=nome,
            testo=testo_oggetto(nome, varianti, alias, codici, contraddizione, arricchimento),
            varianti=varianti, alias=alias, codice_materiale=", ".join(codici) or None,
            fonte=fonte, riferimento=riferimento, contraddizione=contraddizione))
    return documenti


def documenti_regola(db: sqlite3.Connection) -> list[Documento]:
    righe = db.execute("""
        SELECT r.id, c.nome, d.nome, r.polarita, r.testo, r.dettaglio, r.fonte, r.riferimento
        FROM regola r JOIN destinazione d ON d.id = r.destinazione_id
        JOIN comune c ON c.id = d.comune_id
        WHERE r.polarita IN ('ammesso', 'escluso') ORDER BY r.id""").fetchall()
    return [Documento(
        id=f"regola:{regola_id}", comune=comune, tipo="regola", livello=2,
        testo=testo_regola(destinazione, polarita, testo, dettaglio),
        polarita=polarita, destinazione=destinazione, fonte=fonte, riferimento=riferimento,
        varianti=[Variante(condizioni=[], destinazioni=[destinazione])],
    ) for regola_id, comune, destinazione, polarita, testo, dettaglio, fonte, riferimento in righe]


def documenti_destinazione(db: sqlite3.Connection) -> list[Documento]:
    """Un testo per contenitore, NON indicizzato: serve a spiegare la risposta di livello 2."""
    documenti = []
    for dest_id, comune, nome, canale, colore in db.execute("""
            SELECT d.id, c.nome, d.nome, d.canale, d.colore FROM destinazione d
            JOIN comune c ON c.id = d.comune_id ORDER BY c.nome, d.nome"""):
        regole = db.execute("SELECT polarita, testo FROM regola WHERE destinazione_id = ?",
                            (dest_id,)).fetchall()
        ammessi = [t for p, t in regole if p == "ammesso"]
        esclusi = [t for p, t in regole if p == "escluso"]
        note = [t for p, t in regole if p == "nota"]
        if not (ammessi or esclusi or note):
            continue
        documenti.append(Documento(
            id=f"destinazione:{dest_id}", comune=comune, tipo="destinazione", nome=nome,
            destinazione=nome, indicizzabile=False,
            testo=testo_destinazione(nome, canale, colore, ammessi, esclusi, note)))
    return documenti


def costruisci(db: sqlite3.Connection) -> list[Documento]:
    return [*documenti_oggetto(db), *documenti_regola(db), *documenti_destinazione(db)]


# --------------------------------------------------------------------------- comando

def main() -> None:
    """Costruisce i documenti e li mostra: servono a essere letti prima di indicizzarli.

    Uso:
      uv run ecoscan-documenti --comune Napoli --cerca pizza
      uv run ecoscan-documenti --tipo regola -n 10
    """
    import argparse
    import json
    from pathlib import Path

    from ecoscan.db.vettorizza import DB

    ap = argparse.ArgumentParser(description="Costruisce e mostra i documenti da indicizzare.")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--comune")
    ap.add_argument("--tipo", choices=TIPI)
    ap.add_argument("--cerca", help="mostra solo i documenti il cui testo contiene questa parola")
    ap.add_argument("-n", type=int, default=8, help="quanti mostrarne")
    ap.add_argument("--payload", action="store_true", help="mostra anche il payload")
    args = ap.parse_args()

    if not args.db.is_file():
        raise SystemExit(f"Database non trovato: {args.db}\nLancia prima: uv run ecoscan-carica")

    with sqlite3.connect(args.db) as db:
        documenti = costruisci(db)

    scelti = [d for d in documenti
              if (not args.comune or d.comune == args.comune)
              and (not args.tipo or d.tipo == args.tipo)
              and (not args.cerca or args.cerca.lower() in d.testo.lower())]

    print(f"{len(documenti)} documenti in tutto "
          f"({', '.join(f'{t}: {sum(1 for d in documenti if d.tipo == t)}' for t in TIPI)}), "
          f"di cui {sum(1 for d in documenti if d.indicizzabile)} indicizzabili")
    lunghezze = sorted(len(d.testo) for d in documenti if d.indicizzabile)
    if lunghezze:
        print(f"lunghezza del testo indicizzato: minima {lunghezze[0]}, "
              f"mediana {lunghezze[len(lunghezze) // 2]}, massima {lunghezze[-1]} caratteri")
    print(f"\nMostro {min(args.n, len(scelti))} di {len(scelti)} documenti scelti:\n")
    for d in scelti[:args.n]:
        print(f"[{d.id}]")
        print(f"  {d.testo}")
        if args.payload:
            print(f"  payload: {json.dumps(d.payload(), ensure_ascii=False)[:400]}")
        print()
