"""Il testo delle voci: pulizia, confronto e difetti. Funzioni pure, nessun I/O.

Si chiamava `napoli_qualita` ed era una bugia: lo importavano l'estrattore di Torino, il
motore di normalizzazione e quello delle regole. Alcune funzioni nascono davvero dalla
fonte napoletana — `slugify_wp` riproduce `sanitize_title` di WordPress, `e_placeholder`
riconosce un testo segnaposto visto su quel sito — ma sono utilizzabili ovunque, ed erano
l'unico motivo per cui mezza pagina di codice condiviso portava il nome di un comune.

Due gruppi di funzioni:

- **pulizia e confronto** — `normalizza_spazi`, `senza_accenti`, `slugify_wp`,
  `split_destinazioni`, `chiave_confronto`, `possibili_duplicati`;
- **difetti** — `problemi_qualita` trova ciò che è rotto *nella fonte*, `difetti` e
  `motivo` ciò che si è rotto **durante la normalizzazione**, cioè i nomi rimasti
  sgrammaticati quando la condizione stava in mezzo al nome.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

PLACEHOLDER_RE = re.compile(r"eventuale messaggio che [èe] possibile specificare", re.IGNORECASE)
WP_SUFFIX_RE = re.compile(r"-(\d+)$")  # WordPress aggiunge "-2", "-3" agli slug duplicati


def normalizza_spazi(testo: str) -> str:
    """Compatta gli spazi e corregge le parentesi con spazi interni, es. 'Quantità )'."""
    t = unicodedata.normalize("NFKC", testo)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\(\s+", "(", t)
    return re.sub(r"\s+\)", ")", t)


def senza_accenti(testo: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", testo) if unicodedata.category(c) != "Mn")


def slugify_wp(testo: str) -> str:
    """Approssima sanitize_title di WordPress: minuscole, niente accenti, apostrofi rimossi."""
    t = senza_accenti(testo).lower()
    t = re.sub(r"['’`]", "", t)
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-")


def split_destinazioni(testo: str) -> list[str]:
    """'Isola Ecologica Estesa, Numero Verde Gratuito' -> lista ordinata senza duplicati."""
    visti, out = set(), []
    for parte in testo.split(","):
        p = normalizza_spazi(parte)
        if p and p not in visti:
            visti.add(p)
            out.append(p)
    return out


def e_placeholder(avvertenza: str | None) -> bool:
    return bool(avvertenza) and bool(PLACEHOLDER_RE.search(avvertenza))


def info_nello_slug(nome: str, slug: str) -> str | None:
    """Testo presente nello slug ma non nel nome visibile (istruzioni troncate dal titolo).

    'Ago per prelievi' + 'ago-per-prelievi-proteggere-lago-con-il-cappuccio'
    -> 'proteggere lago con il cappuccio'. Il testo è lossy (apostrofi e accenti persi):
    va sempre revisionato a mano prima di diventare una condizione o un'avvertenza.
    """
    base = slugify_wp(nome)
    s = WP_SUFFIX_RE.sub("", slug)
    if s.startswith(base) and len(s) > len(base):
        extra = s[len(base):].strip("-")
        return extra.replace("-", " ") or None
    return None


def suffisso_duplicato(slug: str) -> int | None:
    m = WP_SUFFIX_RE.search(slug)
    return int(m.group(1)) if m else None


def chiave_confronto(nome: str) -> str:
    """Chiave grezza per scovare possibili duplicati: minuscole, niente accenti, desinenza tolta."""
    parole = re.findall(r"[a-z0-9]+", senza_accenti(normalizza_spazi(nome)).lower())
    return " ".join(re.sub(r"[aeio]$", "", p) if len(p) > 3 else p for p in parole)


def possibili_duplicati(nomi: list[str]) -> list[list[str]]:
    gruppi = defaultdict(list)
    for n in nomi:
        gruppi[chiave_confronto(n)].append(n)
    return [g for g in gruppi.values() if len(g) > 1]


def problemi_qualita(record: dict) -> list[dict]:
    """Elenco dei problemi di un record grezzo, nel formato della tabella problema_qualita.

    Va chiamata DOPO aver assegnato l'avvertenza: la sua presenza cambia la gravità
    dell'informazione nascosta nello slug.
    """
    out = []
    nome, slug = record["nome_originale"], record["slug"]
    if e_placeholder(record.get("avvertenza")):
        out.append({"codice": "placeholder", "dettaglio": record["avvertenza"]})
    extra = info_nello_slug(nome, slug)
    if extra and not record.get("avvertenza"):
        # senza un'avvertenza pulita, il testo dello slug è l'unica traccia: va revisionato
        out.append({"codice": "info_nello_slug", "dettaglio": extra})
    elif extra:
        # l'avvertenza riporta la stessa informazione con accenti e apostrofi corretti
        out.append({"codice": "info_nello_slug_coperta", "dettaglio": extra, "risolto": True})
    if suffisso_duplicato(slug) is not None and info_nello_slug(nome, slug) is None:
        out.append({"codice": "slug_duplicato", "dettaglio": slug})
    if nome != normalizza_spazi(nome):
        out.append({"codice": "spaziatura", "dettaglio": nome})
    if not record.get("destinazioni"):
        out.append({"codice": "senza_destinazione", "dettaglio": slug})
    if record.get("destinazioni_indice") and record["destinazioni_indice"] != record["destinazioni"]:
        out.append({"codice": "indice_incoerente",
                    "dettaglio": f"indice={record['destinazioni_indice']} pagina={record['destinazioni']}"})
    return out


# ---------------------------------------------------------------- nomi sgrammaticati
#
# Il Transform toglie dal nome tutto cio' che non e' l'oggetto: condizioni, esempi,
# sinonimi. Quasi sempre il resto e' un nome pulito — "Cartone da pizza pulito" diventa
# "Cartone da pizza" — ma quando la condizione sta IN MEZZO al nome, il resto puo' essere
# un frammento di sintassi invece di un oggetto:
#
#     "Stovaglie monouso in materiale compostabile"  ->  "Stovaglie in materiale"
#     "Tovaglioli di carta bagnati o unti di cibo"   ->  "Tovaglioli di carta o di cibo"
#
# Non e' un difetto estetico: il nome finisce nel testo indicizzato e nel confronto con
# l'oggetto riconosciuto, quindi un nome rotto e' un documento che il recupero non trova
# mai. E' un problema di retrieval travestito da problema di dati.
#
# Si riconoscono dalla GRAMMATICA, non dalla lunghezza: togliere meta' del nome e' spesso
# giusto, e i nomi corti sono spesso sigle legittime (CD, PC). Sono controlli stretti, e su
# 902 voci ne segnalano cinque: la precisione conta piu' della copertura, perche' un
# controllo che grida al lupo viene disattivato.

CONTROLLI: dict[str, re.Pattern] = {
    # "Stovaglie in materiale": il materiale è annunciato e la parola che lo diceva è stata
    # tolta con la condizione
    "materiale annunciato e non detto": re.compile(r"\b(in|di)\s+materiale\s*$", re.I),
    # "Tovaglioli di carta o di cibo": è rimasta la congiunzione di due condizioni
    "congiunzione seguita da preposizione": re.compile(r"\s[eo]\s+(di|in|da|per|con)\s", re.I),
    "congiunzione orfana": re.compile(r"^\s*[eo]\s|\s+[eo]\s*$", re.I),
    # "Giocattolo o elettrico": il primo termine della congiunzione era una condizione
    # ("di grosse dimensioni") ed e stato tolto, lasciando un oggetto congiunto a un aggettivo
    "congiunzione seguita da aggettivo": re.compile(
        r"^\S+\s+[eo]\s+\w+(ico|ica|ale|ato|ata|ito|ita|oso|osa|ivo|iva)\b", re.I),
    "preposizioni consecutive": re.compile(r"\b(di|in|da|per|con|a)\s+(di|in|da|per|con)\b", re.I),
    "parola ripetuta": re.compile(r"\b(\w{4,})\b\s+\1\b", re.I),
    "finisce con una preposizione": re.compile(
        r"\b(in|di|da|per|con|del|della|dei|delle|al|alla|sul)\s*$", re.I),
    "spazi doppi": re.compile(r"\s{2,}"),
}


def difetti(nome: str) -> list[str]:
    """I difetti grammaticali di un nome normalizzato. Lista vuota se il nome è sano."""
    return [etichetta for etichetta, regex in CONTROLLI.items() if regex.search(nome or "")]


def motivo(nome: str) -> str | None:
    """Il difetto come motivo di revisione, nella forma usata dal Transform."""
    trovati = difetti(nome)
    if not trovati:
        return None
    return f"nome sgrammaticato dopo la normalizzazione ({', '.join(trovati)}): verificare"
