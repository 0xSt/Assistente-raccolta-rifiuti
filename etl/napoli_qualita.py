"""Funzioni pure per la pulizia delle voci ASIA Napoli.

Nessuna dipendenza da rete o HTML: si testano sui valori reali osservati sul sito.
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
    """Elenco dei problemi di un record grezzo, nel formato della tabella problema_qualita."""
    out = []
    nome, slug = record["nome_originale"], record["slug"]
    if e_placeholder(record.get("avvertenza")):
        out.append({"codice": "placeholder", "dettaglio": record["avvertenza"]})
    if (extra := info_nello_slug(nome, slug)):
        out.append({"codice": "info_nello_slug", "dettaglio": extra})
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
