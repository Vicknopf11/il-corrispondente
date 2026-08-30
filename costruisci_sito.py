#!/usr/bin/env python3
"""
Il Corrispondente Artificiale — Costruttore di pagine permalink
Legge docs/posts.json e genera una pagina statica per ogni articolo
sotto docs/{anno}/{mese}/{giorno}/{slug}/index.html

Le pagine già generate per edizioni uscite dalla finestra rolling di
posts.json NON vengono toccate: restano sul disco come permalink stabili.
"""

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
    return ""


def esc(s) -> str:
    return (str(s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


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


def costruisci_pagina(post: dict, data_str: str, anno: str, mese: str, giorno: str,
                       og_image_url: str = OG_IMAGE) -> str:
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

    json_ld = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": titolo,
        "datePublished": f"{data_iso}T09:00:00+02:00",
        "author": {"@type": "Organization", "name": "Il Corrispondente Artificiale"},
        "publisher": {
            "@type": "Organization",
            "name": "Il Corrispondente Artificiale",
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
  <title>{esc(titolo)} — Il Corrispondente Artificiale</title>
  <meta name="description" content="{esc(descrizione)}">
  <link rel="canonical" href="{canonical}">
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

    header h1 {{
      font-size: 1.9rem;
      letter-spacing: 0.05em;
      font-variant: small-caps;
      line-height: 1.1;
    }}

    header h1 a {{ color: inherit; text-decoration: none; }}

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
  <h1><a href="{ROOT_REL}index.html">Il Corrispondente Artificiale</a></h1>
  <p class="organo">Organo Ufficiale della Satira Artificialmente Ragionata &mdash; Fondato per necessità e per noia</p>
  <nav>
    <a href="{ROOT_REL}index.html">Edizioni</a>
    <a href="{ROOT_REL}chi-siamo.html">Chi siamo</a>
    <a href="{ROOT_REL}prompt.html">Il prompt</a>
  </nav>
</header>

<div class="breadcrumb">
  <a href="{ROOT_REL}index.html">Home</a> &rsaquo; {esc(cat)} &rsaquo; {esc(titolo[:50])}{"…" if len(titolo) > 50 else ""}
</div>

<main>
  <article class="{cat_slug}">
    <div class="categoria-label {cat_slug}">{esc(cat)}</div>
    <h1 class="post-titolo">{esc(titolo)}</h1>
    <div class="post-data">{esc(data_leggibile)}</div>
    <div class="post-testo">{esc(testo)}</div>
    {editoriale_html}
    {tag_html}
    <div class="post-footer">
      <span class="post-fonte">{fonte_html}</span>
    </div>
  </article>
  <a class="torna-edizioni" href="{ROOT_REL}index.html">&larr; Torna a tutte le edizioni</a>
</main>

<footer>
  Il Corrispondente Artificiale &mdash; Tutti i diritti satiricamente riservati<br>
  Nessuna notizia è stata danneggiata durante la produzione di questo contenuto<br>
  Generato ogni mattina da Claude (Anthropic) &middot;
  <a href="{ROOT_REL}chi-siamo.html">Chi siamo &middot; Manifesto editoriale</a> &middot;
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


def costruisci_sitemap(archivio: dict) -> str:
    """Genera sitemap.xml con le pagine statiche + tutti i permalink presenti
    nella finestra rolling di posts.json."""

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
    ]

    for edizione in archivio.get("edizioni", []):
        data_str = edizione.get("data", "")
        parti = data_str.split("-")
        if len(parti) != 3:
            continue
        anno, mese, giorno = parti

        for post in edizione.get("post", []):
            slug = post.get("slug")
            if not slug:
                continue
            loc = f"{SITE_URL}/{anno}/{mese}/{giorno}/{slug}/"
            urls.append((loc, "weekly", "0.6", data_str))

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

            html = costruisci_pagina(post, data_str, anno, mese, giorno, og_image_url=og_url)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            n_pagine += 1

    print(f"✓ Costruite/aggiornate {n_pagine} pagine permalink"
          + (f" ({n_saltate} post senza slug saltati)" if n_saltate else ""))

    n_orfane = pulisci_orfani(archivio)
    if n_orfane:
        print(f"✓ Rimosse {n_orfane} pagine orfane")

    sitemap_xml = costruisci_sitemap(archivio)
    with open(SITEMAP_FILE, "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    print(f"✓ sitemap.xml aggiornata ({n_pagine} permalink + 3 pagine statiche)")


if __name__ == "__main__":
    main()
