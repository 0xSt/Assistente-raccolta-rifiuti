"""Motore del Transform, comune a tutti i comuni.

Le regole che cambiano da una fonte all'altra (condizioni, locuzioni, sigle, voci da
scartare) stanno in un `Profilo`; qui c'è solo la meccanica. I profili sono in
`transform_napoli.py` e `transform_torino.py`.

Cinque operazioni:

1. SCARTO delle voci non reali (es. la voce di prova pubblicata sul sito di Napoli).
2. NOME: normalizzazione di spazi e maiuscole, preservando sigle e nomi propri.
3. CONDIZIONE: estratta dalle parentesi oppure da parole-condizione nel nome
   ("Cartone pulito per pizze" vs "Cartone unto per pizze").
4. ALIAS: da sinonimi tra parentesi, esempi, codici materiale e voci composte.
5. DEDUPLICAZIONE: voci con stesso nome+condizione; conflitto se le destinazioni differiscono.

Ogni trasformazione incerta NON viene applicata in silenzio: produce un record con
`da_revisionare = True` e il motivo, così la revisione manuale è mirata.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from ecoscan.etl.napoli_qualita import chiave_confronto, normalizza_spazi, senza_accenti

# --------------------------------------------------------------------------- profilo


@dataclass(frozen=True)
class Profilo:
    """Regole specifiche di una fonte. I default valgono per entrambi i comuni."""

    comune: str
    nomi_da_scartare: frozenset[str] = frozenset()
    condizioni_extra: tuple[tuple[str, str], ...] = ()      # (nome canonico, pattern) inline
    locuzioni_extra: tuple[tuple[str, str], ...] = ()       # (pattern, nome canonico)
    invarianti_extra: frozenset[str] = frozenset()
    locuzioni_fisse: tuple[str, ...] = ()                   # espressioni da non separare mai
    # Provenienza della singola voce: senza di essa una risposta di livello 1 non può
    # mostrare all'utente da dove viene la regola (D129)
    fonte: str = ""
    modello_riferimento: str = ""                           # formattato con il record grezzo

    def riferimento(self, record: dict) -> str | None:
        if not self.modello_riferimento:
            return None
        try:
            testo = self.modello_riferimento.format_map(record)
        except KeyError:                                     # il grezzo non porta il campo
            return None
        return testo or None

    def condizioni_inline(self) -> dict[str, str]:
        return {**CONDIZIONI_INLINE, **dict(self.condizioni_extra)}

    def locuzioni(self) -> list[tuple[str, str]]:
        return [*self.locuzioni_extra, *CONDIZIONI_LOCUZIONE]

# --------------------------------------------------------------------------- nome

# Sigle e nomi propri da non minuscolizzare (osservati nelle 584 voci)
INVARIANTI = {
    "PAP", "PCB", "ALU", "FE", "FOR", "GL", "GLS", "LDPE", "PE-LD", "PE-HD", "PET", "PP", "PS",
    "TEX", "COT", "OTHER", "RAEE", "R4", "CD", "CD-ROM", "DVD", "VHS", "USB", "MP3", "TV", "PC",
    "C/PAP", "TE/OF",
    "T", "F", "Natale", "Tetra", "Pak", "Moka",
}
_INVARIANTI_MIN = {p.lower(): p for p in INVARIANTI}


def normalizza_nome(nome: str, profilo: Profilo | None = None) -> str:
    """Minuscole tranne la prima parola e le sigle: 'Biro E Pena A Sfera' -> 'Biro e pena a sfera'."""
    invarianti = dict(_INVARIANTI_MIN)
    if profilo:
        invarianti.update({p.lower(): p for p in profilo.invarianti_extra})
    parole = normalizza_spazi(nome).split()
    out = []
    for i, p in enumerate(parole):
        nudo = p.strip(".,;:()")
        if (fisso := invarianti.get(nudo.lower())):
            out.append(p.replace(nudo, fisso))
        elif i == 0:
            out.append(p[0].upper() + p[1:].lower() if p[1:].isupper() or p[1:].islower() is False else p)
        else:
            out.append(p.lower())
    testo = " ".join(out)
    return testo[0].upper() + testo[1:] if testo else testo


# --------------------------------------------------------------------------- condizioni

# Parole-condizione che possono comparire ovunque nel nome, con le loro varianti di genere/numero.
# Ognuna distingue voci con destinazioni diverse: è questo che le rende condizioni e non aggettivi.
CONDIZIONI_INLINE = {
    "pulito": r"pulit[oaie]",
    "sporco": r"sporch?[oaie]",
    "unto": r"unt[oaie]",
    "umido": r"umid[oaie]",
    "vuoto": r"vuot[oaie]",
    "pieno": r"pien[oaie]",
    "usato": r"usat[oaie]",
    "scaduto": r"scadut[oaie]",
    "utilizzabile": r"utilizzabil[ei]",
    "compostabile": r"compostabil[ei]",
    "biodegradabile": r"biodegra[dt]abil[ei]",  # la fonte scrive anche "biodegratabile"
    "rotto": r"rott[oaie]",
    "spento": r"spent[oaie]",
    "monouso": r"monouso",
}

# Condizioni espresse come locuzione (di solito tra parentesi, a volte no)
CONDIZIONI_LOCUZIONE = [
    (r"(in )?(grandi|grosse) quantit[aà]", "grandi quantità"),
    (r"(in )?piccole quantit[aà]", "piccole quantità"),
    (r"(di )?(grandi|grosse) dimensioni", "grandi dimensioni"),
    (r"(di )?piccole dimensioni", "piccole dimensioni"),
    (r"contenitore vuot[oaie]", "contenitore vuoto"),
    (r"contenitor[ie] vuot[ie]", "contenitore vuoto"),
    (r"contenitore pieno o con tracce", "contenitore pieno o con tracce"),
    (r"barattoli pieni o con tracce", "contenitore pieno o con tracce"),
    (r"anche vuot[ae]", "anche vuoto"),
    (r"con residu[oi]", "con residuo"),
    (r"senza residu[oi]", "senza residuo"),
    (r"con feci", "con feci"),
    (r"senza feci", "senza feci"),
    (r"da uten[zc][ea] domestic[aho]+", "utenza domestica"),
    (r"da piccola lavorazione domestica", "utenza domestica"),
    (r"non plastificat[oa]", "non plastificato"),
    (r"rotto o in lastre", "rotto"),
    (r"privat[ao] di cannula ago e dosatore", "privata di cannula, ago e dosatore"),
]

def _estrai_condizioni_inline(nome: str, profilo: Profilo) -> tuple[str, list[str]]:
    """Rimuove dal nome le parole-condizione, gestendo la negazione ('non utilizzabili')."""
    trovate, testo = [], nome
    for canonica, pattern in profilo.condizioni_inline().items():
        regex = re.compile(rf"\b(non\s+)?({pattern})\b", re.IGNORECASE)
        if (m := regex.search(testo)):
            trovate.append(("non " if m.group(1) else "") + canonica)
            testo = regex.sub(" ", testo, count=1)
    return _pulisci_congiunzioni(testo), trovate


# --------------------------------------------------------------------------- parentesi

CODICE = re.compile(r"^\d{2}$")
# Parentesi che elencano materiali o provenienza descrivono una variante dell'oggetto,
# non un sinonimo: "Involucro cioccolatini (alluminio)" vs "(plastica argentata)".
MATERIALI = {"alluminio", "plastica", "metallo", "vetro", "carta", "cartone", "legno", "tessuto",
             "acciaio", "polistirolo", "sughero", "ceramica", "gomma", "terracotta", "ferro",
             "argentata", "chimica", "termica", "sabbia", "segatura", "pile"}
SIGLA_O_SINONIMO = re.compile(r"^[\w\s/\-]+$")


def classifica_parentesi(contenuto: str, profilo: Profilo | None = None) -> tuple[str, str]:
    """Restituisce (tipo, valore): 'condizione' | 'codice' | 'alias' | 'esempi' | 'ignoto'.

    Dai dati reali: '(40)' è il codice materiale, '(tetrapak)' un sinonimo,
    '(scatola di pelati, tonno, ...)' degli esempi, '(contenitore Vuoto)' una condizione.
    """
    profilo = profilo or Profilo(comune="?")
    c = normalizza_spazi(contenuto)
    piatto = senza_accenti(c).lower()
    for pattern, canonica in profilo.locuzioni():
        if re.fullmatch(pattern, piatto) or re.fullmatch(pattern, c.lower()):
            return "condizione", canonica
    for canonica, pattern in profilo.condizioni_inline().items():
        if re.fullmatch(rf"(non )?{pattern}", piatto):
            return "condizione", ("non " if piatto.startswith("non ") else "") + canonica
    if CODICE.fullmatch(c):
        return "codice", c
    if re.fullmatch(r"in \w+", piatto):  # '(in Plastica)', '(in Vetro)': specificano il materiale
        return "condizione", c.lower()
    parole = {w.strip(".,") for w in re.split(r"[\s/]+", piatto)}
    if parole & MATERIALI and parole <= MATERIALI | {"in", "o", "e", "di", "da", "con"}:
        return "condizione", c.lower()
    if piatto.startswith("di "):  # provenienza: "(di finestre e porte)"
        return "condizione", c.lower()
    if re.search(r"\bvuot[oaie]\b|\bpien[oaie]\b", piatto):
        # '(flacone o sacchetto vuoto)', '(contenitori vuoti in Vetro)': stato e materiale del contenitore
        return "condizione", c.lower()
    if "," in c or re.search(r"\becc\b|\.\.\.", piatto):
        return "esempi", c
    if SIGLA_O_SINONIMO.fullmatch(c) and len(c.split()) <= 3:
        return "alias", c
    return "ignoto", c


def _pulisci_congiunzioni(testo: str) -> str:
    """Toglie congiunzioni e preposizioni rimaste sospese dopo la rimozione di una condizione."""
    testo = re.sub(r"\s+[eo]\s*$", " ", testo, flags=re.IGNORECASE)
    testo = re.sub(r"^\s*[eo]\s+", " ", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+(e|o|di|da|in|per|del|della)\s*$", " ", testo, flags=re.IGNORECASE)
    return normalizza_spazi(re.sub(r"\s*,\s*$", "", normalizza_spazi(testo)))


# --------------------------------------------------------------------------- voci composte

# 'Biro e pena a sfera' sono due oggetti; 'Cotton fioc biodegradabile e compostabile' no.
# Si separa solo quando entrambi i lati reggono da soli: nessuna parola-condizione e
# nessun attributo (il lato destro non deve iniziare per aggettivo noto).
PAROLE_NON_SEPARABILI = set(CONDIZIONI_INLINE) | {
    "simili", "altri", "altre", "tisane", "verdura", "animali", "brasare", "bicchieri", "sintetico",
}


def separa_voce_composta(nome: str, profilo: Profilo | None = None) -> list[str]:
    """Restituisce i componenti se la voce è composta, altrimenti lista vuota."""
    if ":" in nome or senza_accenti(nome).lower().startswith("simbolo"):
        return []  # 'Simbolo GL o GLS (70)' è un codice materiale, non due oggetti
    if "," in nome:
        pezzi = [normalizza_spazi(p) for p in re.split(r",| e ", nome) if normalizza_spazi(p)]
        # composta solo se ogni pezzo ha almeno due parole (sono descrizioni autonome)
        # \becc\b e non "ecc": la sottostringa compare dentro parole come "apparecchi"
        elenco_aperto = re.search(r"\becc\b|\.{2,}", nome, re.IGNORECASE)
        if len(pezzi) >= 3 and all(len(p.split()) >= 2 for p in pezzi) and not elenco_aperto:
            return pezzi
        return []
    for fissa in (profilo.locuzioni_fisse if profilo else ()):
        if re.search(rf"\b{re.escape(fissa)}\b", nome, re.IGNORECASE):
            return []  # locuzione fissa della fonte, non due oggetti
    # solo " e ": la " o " indica quasi sempre materiali alternativi dello stesso oggetto
    # ("Guanti in pelle o lana", "Stendino in metallo o plastica")
    if (m := re.search(r"^(.*?)\s+e\s+(.*)$", nome, re.IGNORECASE)):
        sinistra, destra = normalizza_spazi(m.group(1)), normalizza_spazi(m.group(2))
        prima_destra = senza_accenti(destra.split()[0]).lower() if destra.split() else ""
        if prima_destra in PAROLE_NON_SEPARABILI or not sinistra or len(destra.split()) > 4:
            return []
        if len(sinistra.split()) > 3:
            # un lato sinistro lungo indica un elenco di attributi, non due oggetti
            return []
        preposizioni = {"in", "di", "da", "per", "con"}
        qualif_destra = preposizioni & {w.lower() for w in destra.split()}
        qualif_sinistra = preposizioni & {w.lower() for w in sinistra.split()}
        if qualif_destra and not qualif_sinistra:
            # "Pentola e padella in acciaio": il materiale vale per entrambi, non è una voce composta
            return []
        if qualif_sinistra and len(destra.split()) == 1:
            # "Olio per automobili e macchinari": la destra continua l'elenco degli usi
            return []
        return [sinistra, destra]
    return []


# --------------------------------------------------------------------------- pipeline

@dataclass
class VoceNormalizzata:
    slug: str
    comune: str
    nome_originale: str
    nome: str
    condizioni: list[str] = field(default_factory=list)
    alias: list[str] = field(default_factory=list)
    codice_materiale: str | None = None
    destinazioni: list[str] = field(default_factory=list)
    avvertenza: str | None = None
    fonte: str | None = None
    riferimento: str | None = None
    slug_uniti: list[str] = field(default_factory=list)
    da_revisionare: bool = False
    motivi: list[str] = field(default_factory=list)

    @property
    def chiave(self) -> str:
        """Chiave di deduplicazione insensibile al numero: 'Assorbente' e 'Assorbenti' coincidono."""
        return "|".join([chiave_confronto(self.nome), self.codice_materiale or "",
                         *sorted(self.condizioni)])


@dataclass
class Estratti:
    """Ciò che si stacca dal nome di una voce mentre la si normalizza.

    Nome, condizioni, alias, codice materiale e motivi di revisione crescono insieme lungo
    tutta la trasformazione: tenerli in un oggetto solo evita di passare cinque liste da un
    passaggio all'altro, e rende ogni passaggio leggibile da solo.
    """

    nome: str
    condizioni: list[str] = field(default_factory=list)
    alias: list[str] = field(default_factory=list)
    codice_materiale: str | None = None
    motivi: list[str] = field(default_factory=list)


def _togli_asterisco(estratti: Estratti) -> None:
    """L'asterisco rimanda a una nota a piè di pagina che non estraiamo: si toglie dal nome
    e si segnala, perché quella nota può cambiare la regola."""
    if "*" not in estratti.nome:
        return
    estratti.nome = normalizza_spazi(estratti.nome.replace("*", " "))
    estratti.motivi.append("asterisco: la fonte rimanda a una nota non estratta")


def _svuota_parentesi(estratti: Estratti, profilo: Profilo) -> None:
    """Le parentesi del nome portano cose diverse — condizioni, codici, sinonimi, esempi —
    e ognuna va nel suo campo. Quelle non classificate diventano un motivo di revisione:
    meglio una voce da guardare che una parentesi inventata."""
    for contenuto in re.findall(r"\(([^)]*)\)", estratti.nome):
        tipo, valore = classifica_parentesi(contenuto, profilo)
        if tipo == "condizione":
            estratti.condizioni.append(valore)
        elif tipo == "codice":
            estratti.codice_materiale = valore
        elif tipo == "alias":
            estratti.alias.append(valore)
        elif tipo == "esempi":
            estratti.alias.extend(_esempi(valore))
        else:
            estratti.motivi.append(f"parentesi non classificata: ({valore})")
    estratti.nome = normalizza_spazi(re.sub(r"\s*\([^)]*\)", " ", estratti.nome))


def _esempi(valore: str) -> list[str]:
    """Gli esempi elencati fra parentesi diventano alias, scartando i riempitivi."""
    pezzi = (normalizza_spazi(p) for p in valore.split(","))
    return [p for p in pezzi if p and not re.fullmatch(r"\.{2,}|ecc\.?", p)]


def _stacca_locuzioni(estratti: Estratti, profilo: Profilo) -> None:
    """Le locuzioni note ("usa e getta", "da cucina") sono condizioni scritte dentro il
    nome: si spostano fra le condizioni e il nome resta l'oggetto."""
    piatto = senza_accenti(estratti.nome).lower()
    for pattern, canonica in profilo.locuzioni():
        if m := re.search(pattern, piatto):
            estratti.condizioni.append(canonica)
            estratti.nome = normalizza_spazi(
                estratti.nome[:m.start()] + " " + estratti.nome[m.end():])
            piatto = senza_accenti(estratti.nome).lower()


def _separa_composta(estratti: Estratti, profilo: Profilo) -> None:
    """Una voce che ne elenca due ("Piatti e bicchieri") tiene il primo nome e mette gli
    altri fra gli alias, segnalando che vanno verificati."""
    if componenti := separa_voce_composta(estratti.nome, profilo):
        estratti.alias.extend(componenti[1:])
        estratti.nome = componenti[0]
        estratti.motivi.append("voce composta separata: verificare gli alias")


def trasforma_voce(record: dict, profilo: Profilo | None = None,
                   separa: bool = True) -> VoceNormalizzata | None:
    """Da una voce grezza a una normalizzata: nome pulito, condizioni e alias a parte.

    I passaggi sono in quest'ordine perché ognuno lavora su ciò che il precedente ha
    lasciato nel nome: prima si tolgono le parentesi, poi le locuzioni che restano nel
    testo, poi si separano le voci composte.
    """
    profilo = profilo or Profilo(comune="?")
    nome = normalizza_spazi(record["nome_originale"])
    if senza_accenti(nome).lower() in profilo.nomi_da_scartare:
        return None

    estratti = Estratti(nome=nome)
    _togli_asterisco(estratti)
    _svuota_parentesi(estratti, profilo)
    _stacca_locuzioni(estratti, profilo)
    estratti.nome, inline = _estrai_condizioni_inline(estratti.nome, profilo)
    estratti.condizioni.extend(inline)
    if separa:
        _separa_composta(estratti, profilo)

    nome = normalizza_nome(estratti.nome, profilo)
    if not nome:
        estratti.motivi.append("nome vuoto dopo la normalizzazione")
        nome = normalizza_spazi(record["nome_originale"])

    return VoceNormalizzata(
        slug=record["slug"], comune=profilo.comune,
        nome_originale=record["nome_originale"], nome=nome,
        condizioni=sorted(set(estratti.condizioni)),
        alias=[normalizza_nome(a, profilo) for a in dict.fromkeys(estratti.alias)],
        codice_materiale=estratti.codice_materiale, destinazioni=record["destinazioni"],
        avvertenza=record.get("avvertenza"), fonte=profilo.fonte or None,
        riferimento=profilo.riferimento(record), da_revisionare=bool(estratti.motivi),
        motivi=estratti.motivi,
    )


def deduplica(voci: list[VoceNormalizzata]) -> tuple[list[VoceNormalizzata], list[list[VoceNormalizzata]]]:
    """Unisce le voci con stesso nome e condizioni; segnala i conflitti di destinazione."""
    gruppi: dict[str, list[VoceNormalizzata]] = defaultdict(list)
    for v in voci:
        gruppi[v.chiave].append(v)

    unite, conflitti = [], []
    for gruppo in gruppi.values():
        if len(gruppo) == 1:
            unite.append(gruppo[0])
            continue
        destinazioni = {tuple(sorted(v.destinazioni)) for v in gruppo}
        if len(destinazioni) > 1:
            conflitti.append(gruppo)
            for v in gruppo:
                v.da_revisionare = True
                v.motivi.append("stesso nome, destinazioni diverse: la fonte si contraddice")
            unite.extend(gruppo)
            continue
        principale = max(gruppo, key=lambda v: (bool(v.avvertenza), len(v.nome_originale)))
        for altra in gruppo:
            if altra is principale:
                continue
            principale.slug_uniti.append(altra.slug)
            principale.alias.extend(a for a in [altra.nome, *altra.alias] if a != principale.nome)
            principale.avvertenza = principale.avvertenza or altra.avvertenza
        principale.alias = list(dict.fromkeys(principale.alias))
        unite.append(principale)
    return unite, conflitti
