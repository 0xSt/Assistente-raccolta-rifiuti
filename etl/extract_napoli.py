"""Estrattore ASIA Napoli -> livello grezzo.

Sorgenti:
  - dizionario "Dove lo butto": una pagina per voce (/dove-lo-butto/<slug>/) + indice paginato
  - pagine delle frazioni (/servizi/materiali-da-differenziare/<frazione>/): regole di categoria

Il parsing non usa classi CSS (Elementor le rigenera): si appoggia a elementi stabili
del contenuto, cioè URL delle voci, titolo "Dove buttare X?", intestazioni di colonna
("Contenitore", "Avvertenza") e la lista di destinazioni tra parentesi.

Uso:
  python etl/extract_napoli.py --recon            # scarica indice + 3 voci e stampa cosa trova
  python etl/extract_napoli.py                    # estrazione completa in data/grezzo/napoli
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from napoli_qualita import normalizza_spazi, problemi_qualita, split_destinazioni

BASE = "https://www.asianapoli.it"
DIZIONARIO = f"{BASE}/dove-lo-butto/"
FRAZIONI = ["umido-organico", "plastica-e-metalli", "carta-e-cartone", "vetro", "non-riciclabile", "altre-raccolte"]
SITEMAP_CANDIDATI = ["/wp-sitemap.xml", "/sitemap_index.xml", "/sitemap.xml"]
VOCE_RE = re.compile(r"^/dove-lo-butto/([a-z0-9-]+)/?$")
USER_AGENT = "EcoScanLocal-ETL/0.1 (progetto universitario)"
PAUSA_S = 1.5
VERSIONE_ESTRATTORE = "napoli-0.1"
COLONNE = {"Contenitore", "Avvertenza"}  # intestazioni delle colonne osservate nelle liste


# ----------------------------------------------------------------------------- download

@dataclass
class Snapshot:
    url: str
    recuperato_il: str
    sha256: str
    stato_http: int
    html: str


def canonico(url: str) -> str:
    p = urlparse(url)
    path = p.path if p.path.endswith("/") else p.path + "/"
    return f"{BASE}{path}"


class Fetcher:
    """Download educato con cache su disco: ogni pagina viene scaricata una sola volta."""

    def __init__(self, cache: Path, pausa: float = PAUSA_S):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.sessione = requests.Session()
        self.sessione.headers["User-Agent"] = USER_AGENT
        self.pausa, self._ultimo = pausa, 0.0
        self.robots = robotparser.RobotFileParser()
        r = self.sessione.get(urljoin(BASE, "/robots.txt"), timeout=30)  # errori di rete: eccezione esplicita
        if r.status_code == 404:
            self.robots.parse([])  # nessun robots.txt: tutto consentito
        elif r.status_code == 200:
            self.robots.parse(r.text.splitlines())
        else:
            raise RuntimeError(f"robots.txt non leggibile (HTTP {r.status_code}): interrompo per prudenza")

    def get(self, url: str) -> Snapshot | None:
        chiave = hashlib.sha1(url.encode()).hexdigest()[:16]
        meta_p, html_p = self.cache / f"{chiave}.json", self.cache / f"{chiave}.html"
        if meta_p.exists():
            return Snapshot(**json.loads(meta_p.read_text()), html=html_p.read_text(encoding="utf-8"))
        if not self.robots.can_fetch(USER_AGENT, url):
            raise PermissionError(f"robots.txt non consente {url}")
        attesa = self.pausa - (time.monotonic() - self._ultimo)
        if attesa > 0:
            time.sleep(attesa)
        r = self.sessione.get(url, timeout=30)
        self._ultimo = time.monotonic()
        if r.status_code != 200:
            return None
        r.encoding = r.encoding or "utf-8"
        meta = {"url": url, "recuperato_il": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(r.content).hexdigest(), "stato_http": r.status_code}
        html_p.write_text(r.text, encoding="utf-8")
        meta_p.write_text(json.dumps(meta))
        return Snapshot(**meta, html=r.text)


# ----------------------------------------------------------------------------- scoperta

def scopri_da_sitemap(f: Fetcher) -> list[str]:
    """Strategia 1: sitemap XML di WordPress (core o plugin SEO)."""
    trovate, coda, visti = set(), [urljoin(BASE, p) for p in SITEMAP_CANDIDATI], set()
    while coda:
        u = coda.pop()
        if u in visti:
            continue
        visti.add(u)
        snap = f.get(u)
        if not snap:
            continue
        try:
            radice = ET.fromstring(snap.html.encode())
        except ET.ParseError:
            continue
        for el in radice.iter():
            if el.tag.endswith("loc") and el.text:
                loc = el.text.strip()
                if loc.endswith(".xml"):
                    coda.append(loc)
                elif VOCE_RE.match(urlparse(loc).path):
                    trovate.add(canonico(loc))
    return sorted(trovate)


def scopri_da_indice(f: Fetcher, max_pagine: int = 60) -> list[str]:
    """Strategia 2: indice del dizionario seguendo i link di paginazione server-side.

    Se la paginazione è solo AJAX questa strategia trova solo la prima pagina:
    il controllo di completezza in main() lo segnala.
    """
    trovate, da_visitare, visitate = set(), [DIZIONARIO], set()
    while da_visitare and len(visitate) < max_pagine:
        u = da_visitare.pop(0)
        if u in visitate:
            continue
        visitate.add(u)
        snap = f.get(u)
        if not snap:
            continue
        for a in BeautifulSoup(snap.html, "lxml").find_all("a", href=True):
            href = urljoin(u, a["href"])
            p = urlparse(href)
            if not p.netloc.endswith("asianapoli.it"):
                continue
            if VOCE_RE.match(p.path) and not p.query:
                trovate.add(canonico(href))
            elif p.path.startswith("/dove-lo-butto") and (
                re.search(r"/page/\d+/?$", p.path) or re.search(r"page\w*=\d+", p.query)
            ):
                da_visitare.append(href)
    return sorted(trovate)


# ----------------------------------------------------------------------------- parsing

def _slug(url: str) -> str | None:
    m = VOCE_RE.match(urlparse(url).path)
    return m.group(1) if m else None


def _card(link):
    """Il più grande antenato del link che non contiene altri link a voci: la 'riga' della lista."""
    nodo = link
    while nodo.parent is not None:
        link_voce = [a for a in nodo.parent.find_all("a", href=True) if _slug(urljoin(BASE, a["href"]))]
        if len(link_voce) > 1:
            return nodo
        nodo = nodo.parent
    return nodo


def parse_liste(html: str, url_pagina: str) -> list[dict]:
    """Righe delle liste di voci: indice (colonna 'Contenitore') o pagine voce (colonna 'Avvertenza')."""
    soup = BeautifulSoup(html, "lxml")
    righe = []
    for a in soup.find_all("a", href=True):
        slug = _slug(urljoin(url_pagina, a["href"]))
        if not slug:
            continue
        nome = normalizza_spazi(a.get_text(" ", strip=True))
        extra = normalizza_spazi(_card(a).get_text(" ", strip=True).replace(a.get_text(" ", strip=True), "", 1))
        intestazione = a.find_previous("h3")
        colonna = intestazione.get_text(strip=True) if intestazione else None
        if not nome or slug == _slug(url_pagina) or colonna not in COLONNE:
            continue  # link alla voce corrente o fuori dalle liste (es. voce in evidenza nel box di ricerca)
        righe.append({"slug": slug, "nome": nome, "colonna": colonna, "testo": extra or None})
    return righe


def parse_pagina_voce(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    titolo = normalizza_spazi(h1.get_text(" ", strip=True)) if h1 else ""
    m = re.fullmatch(r"Dove buttare\s+(.+?)\s*\?", titolo)
    nome = m.group(1) if m else titolo

    destinazioni = []
    if h1:
        for s in h1.find_all_next(string=True, limit=500):
            if (mm := re.fullmatch(r"\((.+)\)", s.strip())):
                destinazioni = split_destinazioni(mm.group(1))
                break

    # Descrizione di ogni destinazione: blocco con icona il cui testo inizia con il nome
    descrizioni = {}
    for img in soup.find_all("img", alt=re.compile(r"^Icona", re.I)):
        blocco = img.find_parent(["li", "div"])
        testo = normalizza_spazi(blocco.get_text(" ", strip=True)) if blocco else ""
        for d in destinazioni:
            if testo.startswith(d) and d not in descrizioni:
                descrizioni[d] = testo[len(d):].strip() or None

    return {"slug": _slug(url), "url": url, "nome_originale": nome,
            "destinazioni": destinazioni, "descrizioni_destinazioni": descrizioni}


def parse_pagina_frazione(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    nome = normalizza_spazi(soup.find("h1").get_text(" ", strip=True))
    colore = None
    for h2 in soup.find_all("h2"):
        if (m := re.search(r"colore\s+(\w+)", h2.get_text(" ", strip=True), re.I)):
            colore = m.group(1).lower()
            break
    regole, note = [], []
    for h3 in soup.find_all("h3"):
        t = normalizza_spazi(h3.get_text(" ", strip=True))
        if not re.match(r"cosa (non )?differenziare", t, re.I):
            continue
        polarita = "escluso" if re.search(r"\bnon\b", t, re.I) else "ammesso"
        for el in h3.find_all_next(["strong", "b", "h3", "h4"]):
            if el.name in ("h3", "h4"):
                break
            testo = normalizza_spazi(el.get_text(" ", strip=True))
            if testo:
                dettaglio = el.next_sibling.strip() if isinstance(el.next_sibling, str) and el.next_sibling.strip() else None
                regole.append({"polarita": polarita, "testo": testo, "dettaglio": dettaglio})
    for h4 in soup.find_all("h4"):
        t = normalizza_spazi(h4.get_text(" ", strip=True))
        if t and not re.match(r"(devi buttare|utilizza la nostra|consentono ai cittadini)", t, re.I):
            note.append(t)
    return {"url": url, "nome_frazione": nome, "colore": colore, "regole": regole, "note": note}


# ----------------------------------------------------------------------------- orchestrazione

def estrai(out: Path, f: Fetcher, limite: int | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    urls = scopri_da_sitemap(f)
    strategia = "sitemap"
    if not urls:
        urls, strategia = scopri_da_indice(f), "indice"
    print(f"Scoperta via {strategia}: {len(urls)} voci")

    # L'indice fornisce una seconda lettura delle destinazioni, usata come controllo incrociato
    indice = {r["slug"]: split_destinazioni(r["testo"]) for r in parse_liste(f.get(DIZIONARIO).html, DIZIONARIO)
              if r["colonna"] == "Contenitore" and r["testo"]}
    avvertenze: dict[str, str] = {}
    records = []
    for url in urls[:limite]:
        snap = f.get(url)
        if not snap:
            print(f"  ! non scaricata: {url}")
            continue
        rec = parse_pagina_voce(snap.html, url)
        for riga in parse_liste(snap.html, url):
            if riga["colonna"] == "Avvertenza" and riga["testo"]:
                avvertenze.setdefault(riga["slug"], riga["testo"])
        rec.update({"fonte": "asia_napoli_dove_lo_butto", "sha256": snap.sha256,
                    "recuperato_il": snap.recuperato_il, "versione_estrattore": VERSIONE_ESTRATTORE,
                    "destinazioni_indice": indice.get(rec["slug"])})
        records.append(rec)

    for rec in records:
        rec["avvertenza"] = avvertenze.get(rec["slug"])
        rec["problemi"] = problemi_qualita(rec)

    with open(out / "napoli_voci.jsonl", "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    frazioni = []
    for slug in FRAZIONI:
        url = f"{BASE}/servizi/materiali-da-differenziare/{slug}/"
        if (snap := f.get(url)):
            frazioni.append({**parse_pagina_frazione(snap.html, url), "sha256": snap.sha256,
                             "recuperato_il": snap.recuperato_il, "versione_estrattore": VERSIONE_ESTRATTORE})
    (out / "napoli_frazioni.json").write_text(json.dumps(frazioni, ensure_ascii=False, indent=1), encoding="utf-8")

    # Controlli di completezza: falliscono in modo esplicito invece di produrre dati parziali
    senza_dest = [r["slug"] for r in records if not r["destinazioni"]]
    print(f"Voci estratte: {len(records)} | senza destinazione: {len(senza_dest)} | "
          f"con avvertenza: {sum(1 for r in records if r['avvertenza'])} | frazioni: {len(frazioni)}")
    if strategia == "indice" and len(urls) <= len(indice):
        print("ATTENZIONE: trovata solo la prima pagina dell'indice. La paginazione è probabilmente AJAX: "
              "controlla nella scheda Rete del browser quale richiesta carica le pagine successive.")
    assert len(senza_dest) < max(3, len(records) * 0.02), f"troppe voci senza destinazione: {senza_dest[:10]}"


def recon(f: Fetcher) -> None:
    """Verifica di fattibilità: mostra cosa il parser legge su poche pagine reali."""
    print("Sitemap:", len(scopri_da_sitemap(f)), "voci")
    righe = parse_liste(f.get(DIZIONARIO).html, DIZIONARIO)
    print(f"Indice pagina 1: {len(righe)} righe, colonne {sorted({str(r['colonna']) for r in righe})}")
    for r in righe[:3]:
        print("  ", r)
    for slug in ["specchio", "bacinella-in-plastica", "ago-per-prelievi-proteggere-lago-con-il-cappuccio"]:
        url = f"{DIZIONARIO}{slug}/"
        rec = parse_pagina_voce(f.get(url).html, url)
        print(json.dumps(rec, ensure_ascii=False, indent=1)[:600])
    fr = parse_pagina_frazione(f.get(f"{BASE}/servizi/materiali-da-differenziare/plastica-e-metalli/").html, "")
    print(json.dumps(fr, ensure_ascii=False, indent=1)[:800])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/grezzo/napoli"))
    ap.add_argument("--cache", type=Path, default=Path("data/cache/napoli"))
    ap.add_argument("--recon", action="store_true")
    ap.add_argument("--limite", type=int, default=None)
    args = ap.parse_args()
    fetcher = Fetcher(args.cache)
    recon(fetcher) if args.recon else estrai(args.out, fetcher, args.limite)
