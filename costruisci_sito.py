#!/usr/bin/env python3
"""
Il Corrispondente IA — Costruttore di pagine permalink
Legge docs/posts.json e genera una pagina statica per ogni articolo
sotto docs/{anno}/{mese}/{giorno}/{slug}/index.html

Le pagine già generate per edizioni uscite dalla finestra rolling di
posts.json NON vengono toccate: restano sul disco come permalink stabili.
"""

import glob
import html as html_mod
import json
import os
import re
import shutil
from datetime import datetime

from og_immagine import genera_immagine_og

POSTS_FILE = "docs/posts.json"
SITEMAP_FILE = "docs/sitemap.xml"
SITE_URL = "https://corrispondente.filoclastos.it"
OG_IMAGE = f"{SITE_URL}/assets/img/og-cover.png"
OG_IMG_DIR = "docs/assets/og"
DISCLAIMER_EDITORIALE = (
    "Questa sezione — prospettive e implicazioni — è un'analisi generata "
    "interamente da intelligenza artificiale, non da una redazione umana. "
    "Non è giornalismo verificato da fonti indipendenti: è un esercizio "
    "automatico di lettura multi-angolare della stessa notizia, da leggere "
    "con lo stesso spirito critico di qualsiasi altro contenuto di questo "
    "sito."
)
# Da docs/{anno}/{mese}/{giorno}/{slug}/index.html a docs/ servono 4 livelli
ROOT_REL = "../../../../"


def slug_categoria(cat: str) -> str:
    """Stessa logica di slugCategoria() in index.html, per coerenza di stile."""
    if not cat:
        return ""
    c = cat.lower()
    if "intern" in c:
        return "internazionale"
    if "naz" in c:
        return "nazionale"
    if "econ" in c:
        return "economia"
    if "sport" in c:
        return "sport"
    if "cron" in c:
        return "cronaca"
    if "scien" in c:
        return "scienza"
    if c == "ai" or "intelligenza artificiale" in c:
        return "ai"
    if "wellness" in c:
        return "wellness"
    if "cultura" in c:
        return "cultura"
    return ""


def esc(s) -> str:
    return (str(s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


MESI_IT = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
           "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def tronca(testo: str, n: int = 155) -> str:
    """Tronca un testo a n caratteri su un confine di parola, per meta description."""
    testo = re.sub(r"\s+", " ", testo or "").strip()
    if len(testo) <= n:
        return testo
    tagliato = testo[:n].rsplit(" ", 1)[0]
    return tagliato + "…"


def formatta_data(data_str: str) -> str:
    giorni = ["domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"]
    mesi = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    try:
        d = datetime.strptime(data_str, "%Y-%m-%d")
        return f"{giorni[(d.weekday() + 1) % 7]} {d.day} {mesi[d.month]} {d.year}"
    except Exception:
        return data_str or ""


_COSTI_CACHE = None


def costo_edizione_eur(data_str: str):
    """Costo dell'intera edizione in euro, dal log pubblico dei costi; None se manca."""
    global _COSTI_CACHE
    if _COSTI_CACHE is None:
        try:
            with open(os.path.join("docs", "costi_categoria.json"), encoding="utf-8") as f:
                _COSTI_CACHE = {g.get("data"): g for g in json.load(f).get("generazioni", [])}
        except (OSError, ValueError):
            _COSTI_CACHE = {}
    g = _COSTI_CACHE.get(data_str) or {}
    usd, cambio = g.get("costo_stimato_usd"), g.get("cambio_usd_per_eur")
    if isinstance(usd, (int, float)) and isinstance(cambio, (int, float)) and cambio > 0:
        return usd / cambio
    return None


def minuti_di_lettura(*testi) -> int:
    parole = sum(len((t or "").split()) for t in testi)
    return max(1, round(parole / 200))


def calcola_correlati(archivio: dict, massimo: int = 4) -> dict:
    """Per ogni articolo della finestra rolling: gli altri articoli più recenti della
    stessa sezione, come link interni. Chiave: (data, slug)."""
    per_cat = {}
    for ed in archivio.get("edizioni", []):
        d = ed.get("data", "")
        parti = d.split("-")
        if len(parti) != 3:
            continue
        for p in ed.get("post", []):
            if p.get("slug") and p.get("titolo"):
                per_cat.setdefault(p.get("categoria", ""), []).append((d, parti, p))
    out = {}
    for cat, voci in per_cat.items():
        for d, parti, p in voci:
            altri = [(dd, pp, post) for dd, pp, post in voci if post.get("slug") != p.get("slug")][:massimo]
            out[(d, p["slug"])] = [
                {"titolo": post["titolo"],
                 "href": f"{pp[0]}/{pp[1]}/{pp[2]}/{post['slug']}/",
                 "data": f"{int(pp[2])} {MESI_IT[int(pp[1])][:3]}"}
                for dd, pp, post in altri
            ]
    return out


def costruisci_pagina(post: dict, data_str: str, anno: str, mese: str, giorno: str,
                       og_image_url: str = OG_IMAGE, correlati: list = None) -> str:
    cat = post.get("categoria", "")
    cat_slug = slug_categoria(cat)
    titolo = post.get("titolo", "")
    slug = post.get("slug", "")
    testo = post.get("post_sito") or post.get("post", "")
    fonte = post.get("fonte", "")
    cerca_url = post.get("cerca_url")
    tag = post.get("tag") or []

    canonical = f"{SITE_URL}/{anno}/{mese}/{giorno}/{slug}/"
    descrizione = tronca(testo)
    data_leggibile = formatta_data(data_str)
    data_iso = f"{anno}-{mese}-{giorno}"

    fonte_html = (
        f'Fonte: {esc(fonte or "varie")} &nbsp;&middot;&nbsp; '
        f'<a href="{esc(cerca_url)}" target="_blank" rel="noopener">Cerca notizia →</a>'
        if cerca_url else f'Fonte: {esc(fonte or "varie")}'
    )

    tag_html = ""
    if tag:
        chips = "".join(f'<span class="tag-chip">{esc(t)}</span>' for t in tag)
        tag_html = f'<div class="tag-bar">{chips}</div>'

    editoriale_html = ""
    if post.get("editoriale") is True:
        prospettive = post.get("prospettive") or []
        implicazioni = post.get("implicazioni") or ""
        if prospettive and implicazioni:
            prospettive_html = "".join(
                f'''<div class="prospettiva">
      <div class="prospettiva-etichetta">{esc(pr.get("etichetta"))}</div>
      <div class="prospettiva-testo">{esc(pr.get("testo"))}</div>
    </div>'''
                for pr in prospettive
            )
            editoriale_html = f"""<div class="editoriale-block">
      <div class="editoriale-titolo">Analisi multi-prospettiva</div>
      {prospettive_html}
      <div class="implicazioni-titolo">Implicazioni</div>
      <div class="implicazioni-testo">{esc(implicazioni)}</div>
      <div class="editoriale-disclaimer">{esc(DISCLAIMER_EDITORIALE)}</div>
    </div>"""

    # ── Formato nuovo (dal 10/11/2026): fatti con fonte, lettura, cosa non sappiamo,
    # come è stato generato. Gli articoli senza i campi nuovi restano come prima.
    nuovo_formato = isinstance(post.get("fatti"), list)
    meta_html = f'<div class="post-data">{esc(data_leggibile)}</div>'
    lettura_html = f'<div class="post-testo">{esc(testo)}</div>'
    fatti_html = incerto_html = generato_html = correlati_html = ""
    if nuovo_formato:
        fatti = [f for f in post.get("fatti") if isinstance(f, dict) and f.get("testo")]
        incerto = [t for t in (post.get("incerto") or []) if isinstance(t, str) and t.strip()]
        prosp_testi = " ".join(pr.get("testo", "") for pr in (post.get("prospettive") or [])
                               if isinstance(pr, dict))
        minuti = minuti_di_lettura(testo, " ".join(f["testo"] for f in fatti),
                                   prosp_testi, post.get("implicazioni"))
        meta_html = (f'<div class="post-data">{esc(data_leggibile)} <span class="meta-sep">&middot;</span> '
                     f'Commento IA <span class="meta-sep">&middot;</span> {minuti} min di lettura</div>')
        if fatti:
            voci = []
            for f in fatti:
                url = str(f.get("url") or "")
                if url.startswith(("http://", "https://")):
                    voci.append(f'<li>{esc(f["testo"])} <a class="fonte-link" href="{esc(url)}" '
                                f'target="_blank" rel="noopener">{esc(f.get("fonte") or "fonte")} &#8599;</a></li>')
                else:
                    voci.append(f'<li>{esc(f["testo"])}</li>')
            fatti_html = f"""<section class="blocco fatti">
      <h2>I fatti</h2>
      <ul>{"".join(voci)}</ul>
      <p class="nota-blocco">Ogni fatto rimanda alla pagina in cui è stato trovato.</p>
    </section>"""
        lettura_html = f"""<section class="blocco lettura">
      <h2>La lettura</h2>
      <p class="nota-blocco">Commento di un'IA. La domanda è sempre la stessa: chi ci guadagna?</p>
      <div class="post-testo">{esc(testo)}</div>
    </section>"""
        if incerto:
            incerto_html = ('<section class="blocco incerto"><h2>Cosa non sappiamo</h2><ul>'
                            + "".join(f"<li>{esc(t)}</li>" for t in incerto) + "</ul></section>")
        costo = costo_edizione_eur(data_str)
        costo_txt = (f" Costo dell'intera edizione: &euro; {format(costo, '.2f').replace('.', ',')}."
                     if costo is not None else "")
        generato_html = f"""<section class="blocco generato">
      <h2>Come è stato generato</h2>
      <p>Scritto da un'intelligenza artificiale (Claude, Anthropic) il {int(giorno)} {MESI_IT[int(mese)]} {anno}, a partire da notizie di {esc(fonte or "varie fonti")}.{costo_txt}</p>
      <p class="link-riga"><a href="{ROOT_REL}prompt.html">Il prompt</a><a href="{ROOT_REL}costi.html">Costi</a></p>
    </section>"""
    if correlati:
        voci_c = "".join(
            f'<li><a href="{ROOT_REL}{esc(c["href"])}">{esc(c["titolo"])}</a>'
            f'<span class="corr-data">{esc(c["data"])}</span></li>' for c in correlati)
        correlati_html = f'<section class="blocco correlati"><h2>Altri articoli di {esc(cat)}</h2><ul>{voci_c}</ul></section>'

    json_ld = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": titolo,
        "datePublished": f"{data_iso}T09:00:00+02:00",
        "author": {"@type": "Organization", "name": "Il Corrispondente IA"},
        "publisher": {
            "@type": "Organization",
            "name": "Il Corrispondente IA",
            "logo": {"@type": "ImageObject", "url": OG_IMAGE},
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "description": descrizione,
        "articleSection": cat,
    }

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(titolo)} — Il Corrispondente IA</title>
  <meta name="description" content="{esc(descrizione)}">
  <link rel="canonical" href="{canonical}">
  <link rel="alternate" type="application/rss+xml" title="Il Corrispondente IA" href="{SITE_URL}/feed.xml">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{canonical}">
  <meta property="og:title" content="{esc(titolo)}">
  <meta property="og:description" content="{esc(descrizione)}">
  <meta property="og:image" content="{og_image_url}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="article:section" content="{esc(cat)}">
  <meta property="article:published_time" content="{data_iso}T09:00:00+02:00">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{esc(titolo)}">
  <meta name="twitter:description" content="{esc(descrizione)}">
  <meta name="twitter:image" content="{og_image_url}">
  <script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False)}</script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: 'Georgia', serif;
      background: #f5f0e8;
      color: #1a1a1a;
      min-height: 100vh;
    }}

    header {{
      background: #1a1a1a;
      color: #f5f0e8;
      text-align: center;
      padding: 1.6rem 1rem 1.1rem;
      border-bottom: 4px solid #c0392b;
    }}

    header .testata {{
      font-size: 1.9rem;
      font-weight: bold;
      letter-spacing: 0.05em;
      font-variant: small-caps;
      line-height: 1.1;
    }}

    header .testata a {{ color: inherit; text-decoration: none; }}

    .organo {{
      font-size: 0.78rem;
      color: #bbb;
      font-style: italic;
      margin-top: 0.35rem;
    }}

    nav {{ margin-top: 0.8rem; }}

    nav a {{
      color: #aaa;
      text-decoration: none;
      font-size: 0.76rem;
      margin: 0 0.7rem;
      font-family: Arial, sans-serif;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}

    nav a:hover {{ color: white; }}

    .breadcrumb {{
      max-width: 720px;
      margin: 1.4rem auto 0;
      padding: 0 1rem;
      font-size: 0.75rem;
      font-family: Arial, sans-serif;
      color: #888;
      letter-spacing: 0.02em;
    }}

    .breadcrumb a {{ color: #888; text-decoration: none; }}
    .breadcrumb a:hover {{ color: #c0392b; }}

    main {{
      max-width: 720px;
      margin: 0 auto;
      padding: 1rem 1rem 2.5rem;
    }}

    .categoria-label {{
      display: inline-block;
      font-size: 0.68rem;
      font-family: Arial, sans-serif;
      font-weight: bold;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: white;
      background: #c0392b;
      padding: 0.18rem 0.55rem;
      margin-bottom: 0.9rem;
    }}

    .categoria-label.internazionale {{ background: #2c3e50; }}
    .categoria-label.nazionale      {{ background: #c0392b; }}
    .categoria-label.economia       {{ background: #27ae60; }}
    .categoria-label.sport          {{ background: #2980b9; }}
    .categoria-label.cronaca        {{ background: #8e44ad; }}

    article {{
      background: white;
      border-left: 4px solid #c0392b;
      padding: 1.4rem 1.5rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }}

    article.internazionale {{ border-left-color: #2c3e50; }}
    article.economia       {{ border-left-color: #27ae60; }}
    article.sport          {{ border-left-color: #2980b9; }}
    article.cronaca        {{ border-left-color: #8e44ad; }}

    .post-titolo {{
      font-size: 1.5rem;
      font-weight: bold;
      margin-bottom: 0.5rem;
      line-height: 1.3;
    }}

    .post-data {{
      font-size: 0.8rem;
      color: #999;
      font-style: italic;
      margin-bottom: 1.1rem;
    }}

    .post-testo {{
      font-size: 1.02rem;
      line-height: 1.8;
      margin-bottom: 1.2rem;
      color: #222;
    }}

    .tag-bar {{
      margin-bottom: 1.1rem;
    }}

    .tag-chip {{
      display: inline-block;
      font-size: 0.7rem;
      font-family: Arial, sans-serif;
      color: #888;
      background: #f0ebe0;
      border: 1px solid #ddd;
      padding: 0.15rem 0.6rem;
      margin: 0 0.35rem 0.35rem 0;
      border-radius: 2px;
    }}

    .editoriale-block {{
      margin: 1.4rem 0;
      padding: 1.1rem 1.3rem;
      background: #f0f0ee;
      border-left: 4px solid #7a7a72;
    }}

    .editoriale-titolo {{
      font-family: Arial, sans-serif;
      font-size: 0.72rem;
      font-weight: bold;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #555;
      margin-bottom: 0.9rem;
    }}

    .prospettiva {{
      margin-bottom: 0.9rem;
    }}

    .prospettiva-etichetta {{
      font-family: Arial, sans-serif;
      font-size: 0.82rem;
      font-weight: bold;
      color: #333;
      margin-bottom: 0.2rem;
    }}

    .prospettiva-testo {{
      font-size: 0.96rem;
      line-height: 1.7;
      color: #333;
    }}

    .implicazioni-titolo {{
      font-family: Arial, sans-serif;
      font-size: 0.82rem;
      font-weight: bold;
      color: #333;
      margin: 1rem 0 0.2rem;
    }}

    .implicazioni-testo {{
      font-size: 0.96rem;
      line-height: 1.7;
      color: #333;
    }}

    .editoriale-disclaimer {{
      font-family: Arial, sans-serif;
      font-size: 0.72rem;
      font-style: italic;
      color: #888;
      margin-top: 1rem;
      padding-top: 0.7rem;
      border-top: 1px solid #ddd;
      line-height: 1.6;
    }}

    .post-footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
      border-top: 1px solid #eee;
      padding-top: 0.9rem;
    }}

    .post-fonte {{
      font-size: 0.75rem;
      color: #aaa;
      font-style: italic;
    }}

    .post-fonte a {{ color: #aaa; text-decoration: none; }}
    .post-fonte a:hover {{ color: #c0392b; }}

    .torna-edizioni {{
      display: block;
      text-align: center;
      margin-top: 1.6rem;
      font-size: 0.85rem;
      font-family: Arial, sans-serif;
      color: #555;
      text-decoration: none;
    }}

    .torna-edizioni:hover {{ color: #c0392b; }}

    :root {{ --accento: #c0392b; }}
    .meta-sep {{ color: #bbb; margin: 0 0.2rem; font-style: normal; }}
    .blocco {{ margin-top: 1.8rem; }}
    .blocco h2 {{ font-family: Arial, sans-serif; font-size: 0.78rem; letter-spacing: 0.1em; text-transform: uppercase; color: #444; margin-bottom: 0.6rem; }}
    .nota-blocco {{ font-family: Arial, sans-serif; font-size: 0.8rem; color: #666; line-height: 1.5; margin-bottom: 0.8rem; }}
    .blocco.fatti {{ background: #fbf8f2; border: 1px solid #d9d2c3; padding: 1.1rem 1.3rem; }}
    .blocco.fatti .nota-blocco {{ margin: 0.8rem 0 0; }}
    .blocco.fatti ul {{ padding-left: 1.1rem; }}
    .blocco.fatti li {{ margin-bottom: 0.6rem; line-height: 1.55; }}
    .fonte-link {{ font-family: Arial, sans-serif; font-size: 0.75rem; color: #666; text-decoration: none; border-bottom: 1px dotted #999; white-space: nowrap; }}
    .fonte-link:hover {{ color: var(--accento); }}
    .blocco.lettura h2 {{ color: var(--accento); margin-bottom: 0.2rem; }}
    .blocco.incerto {{ background: #eae3d5; padding: 1rem 1.3rem; }}
    .blocco.incerto ul {{ padding-left: 1.1rem; }}
    .blocco.incerto li {{ margin-bottom: 0.4rem; line-height: 1.5; }}
    .blocco.generato {{ border: 1px solid #1a1a1a; padding: 1rem 1.3rem; font-family: Arial, sans-serif; font-size: 0.88rem; line-height: 1.6; color: #333; }}
    .blocco.generato .link-riga {{ margin-top: 0.6rem; }}
    .blocco.generato .link-riga a {{ margin-right: 1.2rem; color: #1a1a1a; font-weight: bold; }}
    .blocco.correlati ul {{ list-style: none; padding: 0; }}
    .blocco.correlati li {{ padding: 0.55rem 0; border-bottom: 1px solid #e3dccd; display: flex; justify-content: space-between; gap: 1rem; line-height: 1.4; }}
    .blocco.correlati a {{ color: #1a1a1a; text-decoration: none; }}
    .blocco.correlati a:hover {{ color: var(--accento); }}
    .corr-data {{ font-family: Arial, sans-serif; font-size: 0.75rem; color: #888; white-space: nowrap; }}

    footer {{
      text-align: center;
      padding: 2rem;
      font-size: 0.75rem;
      color: #aaa;
      border-top: 1px solid #ddd;
      line-height: 1.9;
      margin-top: 2rem;
    }}

    footer a {{ color: #aaa; text-decoration: none; }}
    footer a:hover {{ color: #c0392b; }}
  </style>
<script data-goatcounter="https://il-corrispondente.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body>

<header>
  <p class="testata"><a href="{ROOT_REL}index.html">Il Corrispondente IA</a></p>
  <p class="organo">Organo Ufficiale del Commento Artificialmente Ragionato &mdash; Fondato per necessità e per noia</p>
  <nav>
    <a href="{ROOT_REL}index.html">Edizioni</a>
    <a href="{ROOT_REL}chi-siamo.html">Chi siamo</a>
    <a href="{ROOT_REL}prompt.html">Il prompt</a>
    <a href="{ROOT_REL}costi.html">Costi</a>
    <a href="{ROOT_REL}archivio.html">Archivio</a>
  </nav>
</header>

<div class="breadcrumb">
  <a href="{ROOT_REL}index.html">Home</a> &rsaquo; {esc(cat)} &rsaquo; {esc(titolo[:50])}{"…" if len(titolo) > 50 else ""}
</div>

<main>
  <article class="{cat_slug}">
    <div class="categoria-label {cat_slug}">{esc(cat)}</div>
    <h1 class="post-titolo">{esc(titolo)}</h1>
    {meta_html}
    {fatti_html}
    {lettura_html}
    {editoriale_html}
    {incerto_html}
    {generato_html}
    {correlati_html}
    {tag_html}
    <div class="post-footer">
      <span class="post-fonte">{fonte_html}</span>
    </div>
  </article>
  <a class="torna-edizioni" href="{ROOT_REL}index.html">&larr; Torna a tutte le edizioni</a>
</main>

<footer>
  Il Corrispondente IA &mdash; Tutti i diritti satiricamente riservati<br>
  Nessuna notizia è stata danneggiata durante la produzione di questo contenuto<br>
  Generato ogni mattina da Claude (Anthropic) &middot;
  <a href="{ROOT_REL}chi-siamo.html">Chi siamo &middot; Manifesto editoriale</a> &middot;
  <a href="{ROOT_REL}archivio.html">Archivio</a> &middot;
  <a href="{ROOT_REL}{anno}/{mese}/">{MESI_IT[int(mese)].capitalize()} {anno}</a> &middot;
  <a href="{ROOT_REL}feed.xml">RSS</a> &middot;
  <a href="https://filoclastos.it/licenze-copyright/">Licenze e copyright</a> &middot;
  <a href="https://filoclastos.it/dichiarazione-bias/">Dichiarazione sul bias</a>
</footer>

</body>
</html>
"""


def pulisci_orfani(archivio: dict) -> int:
    """Rimuove le pagine permalink 'orfane': cartelle rimaste sul disco per una
    data ancora dentro la finestra rolling di posts.json, il cui slug non
    corrisponde più a nessun post attuale per quella data (es. il modello è
    stato rilanciato più volte nello stesso giorno, in test o per errore).

    Le date USCITE dalla finestra rolling non vengono mai toccate: i loro
    permalink restano stabili per sempre, com'è giusto che sia."""
    n_rimosse = 0
    for edizione in archivio.get("edizioni", []):
        data_str = edizione.get("data", "")
        parti = data_str.split("-")
        if len(parti) != 3:
            continue
        anno, mese, giorno = parti

        cartella_giorno = os.path.join("docs", anno, mese, giorno)
        if not os.path.isdir(cartella_giorno):
            continue

        slug_validi = {p.get("slug") for p in edizione.get("post", []) if p.get("slug")}

        for nome in os.listdir(cartella_giorno):
            percorso = os.path.join(cartella_giorno, nome)
            if os.path.isdir(percorso) and nome not in slug_validi:
                shutil.rmtree(percorso)
                n_rimosse += 1
                print(f"  ✗ Rimossa pagina orfana: {percorso}")

                og_orfana = os.path.join(OG_IMG_DIR, f"{anno}-{mese}-{giorno}-{nome}.png")
                if os.path.exists(og_orfana):
                    os.remove(og_orfana)
                    print(f"  ✗ Rimossa immagine OG orfana: {og_orfana}")

    return n_rimosse


def elenco_permalink_su_disco() -> list:
    """Tutti i permalink presenti in docs/{anno}/{mese}/{giorno}/{slug}/index.html,
    come (anno, mese, giorno, slug), in ordine di data decrescente. Include gli
    articoli usciti dalla finestra rolling di posts.json: restano pubblicati e
    devono restare nella sitemap, altrimenti nessuna pagina li collega."""
    trovati = []
    for path in glob.glob(os.path.join("docs", "[0-9][0-9][0-9][0-9]", "*", "*", "*", "index.html")):
        parti = os.path.normpath(path).split(os.sep)
        # docs / anno / mese / giorno / slug / index.html
        if len(parti) == 6 and parti[1].isdigit() and parti[2].isdigit() and parti[3].isdigit():
            trovati.append((parti[1], parti[2], parti[3], parti[4]))
    return sorted(trovati, reverse=True)



CSS_ARCHIVIO = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Georgia', serif; background: #f5f0e8; color: #1a1a1a; min-height: 100vh; }
    header { background: #1a1a1a; color: #f5f0e8; text-align: center; padding: 1.6rem 1rem 1.1rem; border-bottom: 4px solid #c0392b; }
    header .testata { font-size: 1.9rem; font-weight: bold; letter-spacing: 0.05em; font-variant: small-caps; line-height: 1.1; }
    header .testata a { color: inherit; text-decoration: none; }
    .organo { font-size: 0.78rem; color: #bbb; font-style: italic; margin-top: 0.35rem; }
    nav { margin-top: 0.9rem; }
    nav a { color: #aaa; text-decoration: none; font-size: 0.8rem; margin: 0 0.7rem; font-family: Arial, sans-serif; letter-spacing: 0.05em; text-transform: uppercase; }
    nav a:hover { color: white; }
    nav a.attivo { color: white; border-bottom: 1px solid #c0392b; }
    main { max-width: 760px; margin: 0 auto; padding: 2.2rem 1rem 3rem; }
    h1 { font-size: 2rem; margin-bottom: 0.4rem; }
    .sotto { color: #666; font-family: Arial, sans-serif; font-size: 0.85rem; margin-bottom: 1.4rem; }
    h2 { font-size: 1.05rem; font-variant: small-caps; letter-spacing: 0.04em; margin: 1.8rem 0 0.6rem; padding-bottom: 0.3rem; border-bottom: 1px solid #1a1a1a; }
    ul { list-style: none; }
    li { padding: 0.45rem 0; border-bottom: 1px solid #e3dccd; line-height: 1.4; }
    li a { color: #1a1a1a; text-decoration: none; }
    li a:hover { color: #c0392b; }
    .cat { font-family: Arial, sans-serif; font-size: 0.68rem; font-weight: bold; text-transform: uppercase; letter-spacing: 0.06em; color: #666; margin-right: 0.5rem; }
    .mesi li { font-size: 1.05rem; display: flex; justify-content: space-between; gap: 1rem; }
    .mesi .n { font-family: Arial, sans-serif; font-size: 0.82rem; color: #666; white-space: nowrap; }
    .mese-nav { display: flex; justify-content: space-between; gap: 1rem; font-family: Arial, sans-serif; font-size: 0.85rem; margin-top: 2rem; }
    .mese-nav a { color: #c0392b; text-decoration: none; }
    footer { text-align: center; padding: 2rem 1rem; font-size: 0.75rem; color: #aaa; border-top: 1px solid #ddd; line-height: 1.8; }
    footer a { color: #aaa; text-decoration: none; }
    footer a:hover { color: #c0392b; }
"""


def pagina_archivio(titolo: str, descrizione: str, canonical: str, corpo: str, root_rel: str) -> str:
    """Pagina statica dell'archivio, con la stessa testata e lo stesso piede degli articoli."""
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(titolo)} — Il Corrispondente IA</title>
  <meta name="description" content="{esc(descrizione)}">
  <link rel="canonical" href="{canonical}">
  <link rel="alternate" type="application/rss+xml" title="Il Corrispondente IA" href="{SITE_URL}/feed.xml">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{canonical}">
  <meta property="og:title" content="{esc(titolo)} — Il Corrispondente IA">
  <meta property="og:description" content="{esc(descrizione)}">
  <meta property="og:image" content="{OG_IMAGE}">
  <style>{CSS_ARCHIVIO}</style>
<script data-goatcounter="https://il-corrispondente.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body>

<header>
  <p class="testata"><a href="{root_rel}index.html">Il Corrispondente IA</a></p>
  <p class="organo">Organo Ufficiale del Commento Artificialmente Ragionato &mdash; Fondato per necessità e per noia</p>
  <nav>
    <a href="{root_rel}index.html">Edizioni</a>
    <a href="{root_rel}chi-siamo.html">Chi siamo</a>
    <a href="{root_rel}prompt.html">Il prompt</a>
    <a href="{root_rel}costi.html">Costi</a>
    <a href="{root_rel}archivio.html" class="attivo">Archivio</a>
  </nav>
</header>

<main>
{corpo}
</main>

<footer>
  Il Corrispondente IA &mdash; Tutti i diritti satiricamente riservati<br>
  Nessuna notizia è stata danneggiata durante la produzione di questo contenuto<br>
  Generato ogni mattina da Claude (Anthropic) &middot;
  <a href="{root_rel}chi-siamo.html">Chi siamo &middot; Manifesto editoriale</a> &middot;
  <a href="{root_rel}feed.xml">RSS</a> &middot;
  <a href="https://filoclastos.it/licenze-copyright/">Licenze e copyright</a> &middot;
  <a href="https://filoclastos.it/dichiarazione-bias/">Dichiarazione sul bias</a>
</footer>

</body>
</html>
"""


def leggi_meta_articolo(percorso: str) -> dict:
    """Titolo e categoria di un articolo, letti dalla sua pagina già generata
    (posts.json conserva solo gli ultimi 30 giorni, le pagine restano per sempre)."""
    try:
        with open(percorso, encoding="utf-8") as f:
            h = f.read()
    except OSError:
        return {"titolo": "", "cat": ""}
    t = re.search(r'<h1 class="post-titolo">(.*?)</h1>', h, re.S)
    c = re.search(r'"articleSection":\s*"([^"]+)"', h)
    titolo = html_mod.unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip() if t else ""
    return {"titolo": titolo, "cat": c.group(1) if c else ""}


def costruisci_archivio() -> tuple:
    """Genera docs/archivio.html (elenco dei mesi) e docs/{anno}/{mese}/index.html
    (tutti gli articoli del mese, per giorno). Ogni articolo diventa raggiungibile
    da una pagina HTML statica. Ritorna (n_mesi, n_articoli)."""
    per_mese = {}
    for anno, mese, giorno, slug in elenco_permalink_su_disco():
        meta = leggi_meta_articolo(os.path.join("docs", anno, mese, giorno, slug, "index.html"))
        if not meta["titolo"]:
            continue
        per_mese.setdefault((anno, mese), []).append({"giorno": giorno, "slug": slug, **meta})

    chiavi = sorted(per_mese, reverse=True)          # mesi più recenti per primi
    n_articoli = 0
    for i, (anno, mese) in enumerate(chiavi):
        voci = per_mese[(anno, mese)]                # già in ordine di data decrescente
        n_articoli += len(voci)
        nome_mese = f"{MESI_IT[int(mese)].capitalize()} {anno}"

        corpo = [f"<h1>{nome_mese}</h1>",
                 f'<p class="sotto">{len(voci)} articoli · <a href="../../archivio.html" style="color:#c0392b">tutto l\'archivio</a></p>']
        giorno_corr = None
        for v in voci:
            if v["giorno"] != giorno_corr:
                if giorno_corr is not None:
                    corpo.append("</ul>")
                giorno_corr = v["giorno"]
                corpo.append(f"<h2>{esc(formatta_data(f'{anno}-{mese}-{giorno_corr}'))}</h2>\n<ul>")
            cat = f'<span class="cat">{esc(v["cat"])}</span>' if v["cat"] else ""
            corpo.append(f'<li>{cat}<a href="{v["giorno"]}/{v["slug"]}/">{esc(v["titolo"])}</a></li>')
        corpo.append("</ul>")

        nav = []
        if i + 1 < len(chiavi):                       # mese precedente
            pa, pm = chiavi[i + 1]
            nav.append(f'<a href="../../{pa}/{pm}/">← {MESI_IT[int(pm)].capitalize()} {pa}</a>')
        else:
            nav.append("<span></span>")
        if i > 0:                                     # mese successivo
            na, nm = chiavi[i - 1]
            nav.append(f'<a href="../../{na}/{nm}/">{MESI_IT[int(nm)].capitalize()} {na} →</a>')
        corpo.append(f'<div class="mese-nav">{"".join(nav)}</div>')

        html = pagina_archivio(
            titolo=f"Archivio {nome_mese}",
            descrizione=f"Tutti gli articoli pubblicati da Il Corrispondente IA a {MESI_IT[int(mese)]} {anno}, giorno per giorno.",
            canonical=f"{SITE_URL}/{anno}/{mese}/",
            corpo="\n".join(corpo),
            root_rel="../../",
        )
        with open(os.path.join("docs", anno, mese, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

    righe = ["<h1>Archivio</h1>",
             f'<p class="sotto">{n_articoli} articoli, da {MESI_IT[int(chiavi[-1][1])]} {chiavi[-1][0]} a oggi.</p>'] if chiavi else ["<h1>Archivio</h1>"]
    anno_corr = None
    for anno, mese in chiavi:
        if anno != anno_corr:
            if anno_corr is not None:
                righe.append("</ul>")
            anno_corr = anno
            righe.append(f"<h2>{anno}</h2>\n<ul class=\"mesi\">")
        righe.append(f'<li><a href="{anno}/{mese}/">{MESI_IT[int(mese)].capitalize()} {anno}</a>'
                     f'<span class="n">{len(per_mese[(anno, mese)])} articoli</span></li>')
    if chiavi:
        righe.append("</ul>")
    html = pagina_archivio(
        titolo="Archivio",
        descrizione="L'archivio completo di Il Corrispondente IA: tutti gli articoli, mese per mese.",
        canonical=f"{SITE_URL}/archivio.html",
        corpo="\n".join(righe),
        root_rel="",
    )
    with open(os.path.join("docs", "archivio.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return len(chiavi), n_articoli


def costruisci_sitemap(archivio: dict) -> str:
    """Genera sitemap.xml con le pagine statiche + tutti i permalink presenti
    su disco (non solo quelli della finestra rolling di posts.json)."""

    def xml_esc(s: str) -> str:
        return (str(s or "")
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    urls = [
        (f"{SITE_URL}/", "daily", "1.0", None),
        (f"{SITE_URL}/chi-siamo.html", "monthly", "0.5", None),
        (f"{SITE_URL}/prompt.html", "monthly", "0.5", None),
        (f"{SITE_URL}/costi.html", "daily", "0.4", None),
        (f"{SITE_URL}/archivio.html", "daily", "0.5", None),
    ]

    for p in sorted(glob.glob(os.path.join("docs", "[0-9][0-9][0-9][0-9]", "[0-9][0-9]", "index.html"))):
        _, anno, mese, _ = os.path.normpath(p).split(os.sep)
        urls.append((f"{SITE_URL}/{anno}/{mese}/", "daily", "0.5", None))

    for anno, mese, giorno, slug in elenco_permalink_su_disco():
        loc = f"{SITE_URL}/{anno}/{mese}/{giorno}/{slug}/"
        urls.append((loc, "monthly", "0.6", f"{anno}-{mese}-{giorno}"))

    voci = []
    for loc, changefreq, priority, lastmod in urls:
        lastmod_tag = f"\n    <lastmod>{xml_esc(lastmod)}</lastmod>" if lastmod else ""
        voci.append(f"""  <url>
    <loc>{xml_esc(loc)}</loc>{lastmod_tag}
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
  </url>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(voci)}
</urlset>
"""


def main():
    if not os.path.exists(POSTS_FILE):
        print(f"⚠ {POSTS_FILE} non trovato, niente da costruire.")
        return

    with open(POSTS_FILE, encoding="utf-8") as f:
        archivio = json.load(f)

    correlati_per_post = calcola_correlati(archivio)
    n_pagine = 0
    n_saltate = 0
    for edizione in archivio.get("edizioni", []):
        data_str = edizione.get("data", "")
        parti = data_str.split("-")
        if len(parti) != 3:
            n_saltate += len(edizione.get("post", []))
            continue
        anno, mese, giorno = parti

        for post in edizione.get("post", []):
            slug = post.get("slug")
            if not slug:
                n_saltate += 1
                continue

            cartella = os.path.join("docs", anno, mese, giorno, slug)
            os.makedirs(cartella, exist_ok=True)
            path = os.path.join(cartella, "index.html")

            og_path = os.path.join(OG_IMG_DIR, f"{anno}-{mese}-{giorno}-{slug}.png")
            og_url = OG_IMAGE
            try:
                genera_immagine_og(post, og_path)
                og_url = f"{SITE_URL}/{og_path.replace('docs/', '')}"
            except Exception as e:
                # Non blocchiamo mai la pipeline per un'immagine OG:
                # meglio l'anteprima generica che un'edizione mancata.
                print(f"  ⚠ Immagine OG non generata per '{slug}' ({e}) — uso il fallback generico")

            try:
                html = costruisci_pagina(post, data_str, anno, mese, giorno, og_image_url=og_url,
                                         correlati=correlati_per_post.get((data_str, slug)))
            except Exception as e:
                # Un difetto nel formato nuovo non deve costare l'edizione del giorno:
                # si ricostruisce la pagina senza i campi nuovi e si segnala nel log.
                print(f"  ⚠ Pagina '{slug}': formato nuovo non riuscito ({type(e).__name__}: {e}) "
                      f"— uso il formato semplice")
                semplice = {k: v for k, v in post.items() if k not in ("fatti", "incerto")}
                html = costruisci_pagina(semplice, data_str, anno, mese, giorno, og_image_url=og_url)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            n_pagine += 1

    print(f"✓ Costruite/aggiornate {n_pagine} pagine permalink"
          + (f" ({n_saltate} post senza slug saltati)" if n_saltate else ""))

    n_orfane = pulisci_orfani(archivio)
    if n_orfane:
        print(f"✓ Rimosse {n_orfane} pagine orfane")

    try:
        n_mesi, n_art_arch = costruisci_archivio()
        print(f"✓ Archivio costruito ({n_mesi} mesi, {n_art_arch} articoli)")
    except Exception as e:
        print(f"⚠ Archivio non costruito ({type(e).__name__}: {e}): le pagine restano quelle di ieri.")

    sitemap_xml = costruisci_sitemap(archivio)
    with open(SITEMAP_FILE, "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    print(f"✓ sitemap.xml aggiornata ({sitemap_xml.count('<loc>')} URL: articoli, archivio e pagine statiche)")


if __name__ == "__main__":
    main()
