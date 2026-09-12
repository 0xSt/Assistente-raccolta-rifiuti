"""Transform: dal livello grezzo di Napoli alle voci normalizzate.

Quattro operazioni, tutte dedotte dai dati reali (584 voci, estrazione 12/09/2026):

1. SCARTO delle voci non reali (voce di prova pubblicata sul sito).
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
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

from ecoscan.etl.napoli_qualita import chiave_confronto, normalizza_spazi, senza_accenti

# --------------------------------------------------------------------------- scarto

# Voci pubblicate per errore sul sito: non descrivono un rifiuto reale
NOMI_DA_SCARTARE = {"test di esempio"}

# --------------------------------------------------------------------------- nome

# Sigle e nomi propri da non minuscolizzare (osservati nelle 584 voci)
INVARIANTI = {
    "PAP", "PCB", "ALU", "FE", "FOR", "GL", "GLS", "LDPE", "PE-LD", "PE-HD", "PET", "PP", "PS",
    "TEX", "COT", "OTHER", "RAEE", "R4", "CD", "CD-ROM", "DVD", "VHS", "USB", "MP3", "TV", "PC",
    "C/PAP", "TE/OF",
    "T", "F", "TE/OF", "Natale", "Tetra", "Pak", "Moka",
}
_INVARIANTI_MIN = {p.lower(): p for p in INVARIANTI}


def normalizza_nome(nome: str) -> str:
    """Minuscole tranne la prima parola e le sigle: 'Biro E Pena A Sfera' -> 'Biro e pena a sfera'."""
    parole = normalizza_spazi(nome).split()
    out = []
    for i, p in enumerate(parole):
        nudo = p.strip(".,;:()")
        if (fisso := _INVARIANTI_MIN.get(nudo.lower())):
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
    "biodegradabile": r"biodegradabil[ei]",
    "rotto": r"rott[oaie]",
    "spento": r"spent[oaie]",
    "monouso": r"monouso",
}

# Condizioni espresse come locuzione (di solito tra parentesi, a volte no)
CONDIZIONI_LOCUZIONE = [
    (r"in (grandi|grosse) quantit[aà]", "grandi quantità"),
    (r"in piccole quantit[aà]", "piccole quantità"),
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

NEGAZIONE = re.compile(r"\bnon\s+$", re.IGNORECASE)


def _estrai_condizioni_inline(nome: str) -> tuple[str, list[str]]:
    """Rimuove dal nome le parole-condizione, gestendo la negazione ('non utilizzabili')."""
    trovate, testo = [], nome
    for canonica, pattern in CONDIZIONI_INLINE.items():
        regex = re.compile(rf"\b(non\s+)?({pattern})\b", re.IGNORECASE)
        if (m := regex.search(testo)):
            trovate.append(("non " if m.group(1) else "") + canonica)
            testo = regex.sub(" ", testo, count=1)
    return _pulisci_congiunzioni(testo), trovate


# --------------------------------------------------------------------------- parentesi

CODICE = re.compile(r"^\d{2}$")
SIGLA_O_SINONIMO = re.compile(r"^[\w\s/\-]+$")


def classifica_parentesi(contenuto: str) -> tuple[str, str]:
    """Restituisce (tipo, valore): 'condizione' | 'codice' | 'alias' | 'esempi' | 'ignoto'.

    Dai dati reali: '(40)' è il codice materiale, '(tetrapak)' un sinonimo,
    '(scatola di pelati, tonno, ...)' degli esempi, '(contenitore Vuoto)' una condizione.
    """
    c = normalizza_spazi(contenuto)
    piatto = senza_accenti(c).lower()
    for pattern, canonica in CONDIZIONI_LOCUZIONE:
        if re.fullmatch(pattern, piatto) or re.fullmatch(pattern, c.lower()):
            return "condizione", canonica
    for canonica, pattern in CONDIZIONI_INLINE.items():
        if re.fullmatch(rf"(non )?{pattern}", piatto):
            return "condizione", ("non " if piatto.startswith("non ") else "") + canonica
    if CODICE.fullmatch(c):
        return "codice", c
    if re.fullmatch(r"in \w+", piatto):  # '(in Plastica)', '(in Vetro)': specificano il materiale
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


def separa_voce_composta(nome: str) -> list[str]:
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
    if (m := re.search(r"^(.*?)\s+[eEoO]\s+(.*)$", nome)):
        sinistra, destra = normalizza_spazi(m.group(1)), normalizza_spazi(m.group(2))
        prima_destra = senza_accenti(destra.split()[0]).lower() if destra.split() else ""
        # il lato sinistro corto indica due oggetti affiancati; uno lungo indica un elenco di attributi
        # ('Contenitori creme per viso corpo e abbronzanti' è un oggetto solo)
        if prima_destra in PAROLE_NON_SEPARABILI or not sinistra or len(destra.split()) > 4:
            return []
        if len(sinistra.split()) > 3:
            return []
        return [sinistra, destra]
    return []


# --------------------------------------------------------------------------- pipeline

@dataclass
class VoceNormalizzata:
    slug: str
    nome_originale: str
    nome: str
    condizioni: list[str] = field(default_factory=list)
    alias: list[str] = field(default_factory=list)
    codice_materiale: str | None = None
    destinazioni: list[str] = field(default_factory=list)
    avvertenza: str | None = None
    slug_uniti: list[str] = field(default_factory=list)
    da_revisionare: bool = False
    motivi: list[str] = field(default_factory=list)

    @property
    def chiave(self) -> str:
        """Chiave di deduplicazione insensibile al numero: 'Assorbente' e 'Assorbenti' coincidono."""
        return chiave_confronto(self.nome) + "|" + "|".join(sorted(self.condizioni))


def trasforma_voce(record: dict) -> VoceNormalizzata | None:
    nome = normalizza_spazi(record["nome_originale"])
    if senza_accenti(nome).lower() in NOMI_DA_SCARTARE:
        return None

    motivi, alias, condizioni, codice = [], [], [], None

    if "*" in nome:  # rimando a una nota a piè di pagina della fonte
        nome = normalizza_spazi(nome.replace("*", " "))
        motivi.append("asterisco: la fonte rimanda a una nota non estratta")

    for contenuto in re.findall(r"\(([^)]*)\)", nome):
        tipo, valore = classifica_parentesi(contenuto)
        if tipo == "condizione":
            condizioni.append(valore)
        elif tipo == "codice":
            codice = valore
        elif tipo == "alias":
            alias.append(valore)
        elif tipo == "esempi":
            alias.extend(normalizza_spazi(p) for p in valore.split(",")
                         if normalizza_spazi(p) and not re.fullmatch(r"\.{2,}|ecc\.?", normalizza_spazi(p)))
        else:
            motivi.append(f"parentesi non classificata: ({valore})")
    nome = normalizza_spazi(re.sub(r"\s*\([^)]*\)", " ", nome))

    piatto = senza_accenti(nome).lower()
    for pattern, canonica in CONDIZIONI_LOCUZIONE:
        if (m := re.search(pattern, piatto)):
            condizioni.append(canonica)
            nome = normalizza_spazi(nome[:m.start()] + " " + nome[m.end():])
            piatto = senza_accenti(nome).lower()

    nome, inline = _estrai_condizioni_inline(nome)
    condizioni.extend(inline)

    if (componenti := separa_voce_composta(nome)):
        alias.extend(componenti[1:])
        nome = componenti[0]
        motivi.append("voce composta separata: verificare gli alias")

    nome = normalizza_nome(nome)
    if not nome:
        motivi.append("nome vuoto dopo la normalizzazione")
        nome = normalizza_spazi(record["nome_originale"])

    return VoceNormalizzata(
        slug=record["slug"], nome_originale=record["nome_originale"], nome=nome,
        condizioni=sorted(set(condizioni)), alias=[normalizza_nome(a) for a in dict.fromkeys(alias)],
        codice_materiale=codice, destinazioni=record["destinazioni"],
        avvertenza=record.get("avvertenza"), da_revisionare=bool(motivi), motivi=motivi,
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
