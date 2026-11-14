#!/usr/bin/env python3
"""
Il Corrispondente IA — Prima pagina statica e pagine delle edizioni.

Legge docs/posts.json (ultime 30 edizioni), docs/costi_categoria.json e
docs/rassegna_sport.json e scrive:
  - docs/index.html                     la prima pagina (edizione più recente)
  - docs/edizioni/AAAA-MM-GG.html       una pagina per ciascuna delle 30 edizioni

La pagina arriva già completa (la legge anche Google). Il JavaScript fa solo
una cosa: i filtri per sezione, nascondendo o mostrando quello che c'è già.
Senza JavaScript le voci del menu portano alle sezioni nella stessa pagina.

Protezioni: tutte le pagine vengono preparate in memoria e scritte solo alla
fine. Se qualcosa va storto lo script stampa l'errore ed esce con 0: restano
le pagine del giorno prima e il resto della run (commit, pubblicazione)
prosegue. Le edizioni uscite dalla finestra di 30 giorni non vengono
cancellate: le loro pagine restano dove sono.
"""
import html
import json
import os
import re
import sys
import traceback
from collections import Counter
from datetime import date

DOCS = "docs"
POSTS_FILE = os.path.join(DOCS, "posts.json")
COSTI_FILE = os.path.join(DOCS, "costi_categoria.json")
RASSEGNA_FILE = os.path.join(DOCS, "rassegna_sport.json")
CARTELLA_EDIZIONI = "edizioni"
SITO = "https://corrispondente.filoclastos.it"

# Le pagine delle edizioni ripetono titoli e attacchi delle pagine articolo.
# Per ora non vanno indicizzate: si decide dopo il confronto Search Console del 16/11.
INDICIZZA_EDIZIONI = False

RASSEGNA_IN_BREVE = 3   # titoli visibili, il resto dietro "Mostra tutta la rassegna"
TEMI_MAX = 8
FATTI_IN_APERTURA = 3
ATTACCO_MAX = 260

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]

# Gruppi e ordine delle sezioni: gli stessi del menu attuale del sito.
GRUPPI = [
    ("attualita", "Attualità", ["internazionale", "nazionale", "cronaca"]),
    ("economia-tech", "Economia & Tech", ["economia", "ai"]),
    ("vita-cultura", "Vita & Cultura", ["scienza", "wellness", "cultura"]),
    ("sport", "Sport", ["sport"]),
]
COLORI = {
    "internazionale": "#2C3E50", "nazionale": "#A93226", "cronaca": "#7A3A99",
    "economia": "#1E7E46", "ai": "#34495E", "scienza": "#0F7664",
    "wellness": "#A84300", "cultura": "#5D6A6B", "sport": "#1F6391",
}

TESTATA_SOTTOTITOLO = ("Organo Ufficiale del Commento Artificialmente Ragionato "
                       "— Fondato per necessità e per noia")
TESTATA_MOTTO = "«La realtà è già satira. Noi aggiungiamo solo la punteggiatura.»"
TESTATA_ULTIMA = "Nessuna notizia è stata danneggiata durante la redazione"
DESCRIZIONE = ("Notizie reali con commento IA dichiarato apertamente. Analisi quotidiana "
               "dell'attualità italiana ed europea, con il prompt che la genera sempre visibile.")


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def slug_categoria(cat: str) -> str:
    """Stessa logica di slug_categoria() in costruisci_sito.py."""
    c = (cat or "").lower()
    if "intern" in c: return "internazionale"
    if "naz" in c: return "nazionale"
    if "econ" in c: return "economia"
    if "sport" in c: return "sport"
    if "cron" in c: return "cronaca"
    if "scien" in c: return "scienza"
    if c == "ai" or "intelligenza artificiale" in c: return "ai"
    if "wellness" in c: return "wellness"
    if "cultura" in c: return "cultura"
    return ""


def data_lunga(d: date) -> str:
    return f"{GIORNI[d.weekday()].capitalize()} {d.day} {MESI[d.month - 1]} {d.year}"


def data_breve(d: date) -> str:
    return f"{d.day} {MESI[d.month - 1]}"


def del_giorno(d: date) -> str:
    """«del 9 novembre», ma «dell’8 novembre», «dell’11», «dell’1»."""
    return ("dell’" if d.day in (1, 8, 11) else "del ") + data_breve(d)


def permalink(data_iso: str, slug: str) -> str:
    """Percorso relativo a docs/ (come buildPermalink nel sito)."""
    a, m, g = data_iso.split("-")
    return f"{a}/{m}/{g}/{slug}/"


def frasi(testo: str) -> list:
    return [f for f in re.split(r"(?<=[.!?»])\s+", (testo or "").strip()) if f]


def attacco(post: dict) -> str:
    prima = (frasi(post.get("post_sito")) or [""])[0]
    if len(prima) > ATTACCO_MAX:
        prima = prima[:ATTACCO_MAX].rsplit(" ", 1)[0] + "…"
    return prima


def lettura(post: dict) -> str:
    """La frase del commento con la domanda fissa, se c'è. Scelta dal codice."""
    for f in frasi(post.get("post_sito")):
        if "guadagn" in f.lower():
            return f
    return ""


def fonti(post: dict) -> list:
    nomi = []
    for f in post.get("fatti") or []:
        n = (f.get("fonte") or "").strip() if isinstance(f, dict) else ""
        if n and n not in nomi:
            nomi.append(n)
    if not nomi and post.get("fonte"):
        nomi = [post["fonte"]]
    return nomi


def minuti_lettura(post: dict) -> int:
    parole = len(" ".join([post.get("post_sito") or ""] +
                          [p.get("testo", "") for p in post.get("prospettive") or [] if isinstance(p, dict)]).split())
    return max(1, round(parole / 200))


# ── Dati ─────────────────────────────────────────────────────────────────────

def carica(percorso: str, vuoto):
    if not os.path.exists(percorso):
        return vuoto
    with open(percorso, encoding="utf-8") as f:
        return json.load(f)


def costo_euro(costi: dict, data_iso: str):
    for g in costi.get("generazioni", []):
        if g.get("data") == data_iso and g.get("costo_stimato_usd") and g.get("cambio_usd_per_eur"):
            return g["costo_stimato_usd"] / g["cambio_usd_per_eur"]
    return None


def temi_del_mese(edizioni: list) -> list:
    """Tag più frequenti nelle edizioni in archivio, esclusi i nomi delle sezioni."""
    sezioni = set(COLORI)
    conta = Counter(t for e in edizioni for p in e.get("post", [])
                    for t in (p.get("tag") or []) if t and t not in sezioni)
    return conta.most_common(TEMI_MAX)


# ── Pezzi di pagina ──────────────────────────────────────────────────────────

def etichetta(post: dict, extra: str = "") -> str:
    s = slug_categoria(post.get("categoria"))
    return (f'<p class="sezione"><span style="color:{COLORI.get(s, "#4A4A4A")}">'
            f'{esc(post.get("categoria"))}</span>{extra}</p>')


def blocco_apertura(post: dict, data_iso: str, root: str) -> str:
    url = root + permalink(data_iso, post.get("slug", ""))
    fatti = [f.get("testo") for f in (post.get("fatti") or [])
             if isinstance(f, dict) and f.get("testo")][:FATTI_IN_APERTURA]
    let = lettura(post)
    prosp = [p.get("etichetta") for p in post.get("prospettive") or []
             if isinstance(p, dict) and p.get("etichetta")]
    colonne = []
    if fatti:
        colonne.append('<div class="colonna"><p class="titoletto">I fatti</p><ul>'
                       + "".join(f"<li>{esc(t)}</li>" for t in fatti) + "</ul></div>")
    if let:
        colonne.append('<div class="colonna"><p class="titoletto accento">La lettura</p>'
                       f'<p class="citazione-lettura">{esc(let)}</p></div>')
    if prosp:
        colonne.append('<div class="colonna"><p class="titoletto">Le prospettive</p>'
                       f'<p>{esc(" · ".join(prosp))}</p></div>')
    griglia = f'<div class="tre-colonne">{"".join(colonne)}</div>' if colonne else ""
    nomi = fonti(post)
    piede = (f'<p class="piede-apertura"><span>{"Fonti: " + esc(", ".join(nomi)) + " · " if nomi else ""}'
             f'{minuti_lettura(post)} min di lettura</span>'
             f'<a href="{esc(url)}">Leggi l’articolo completo</a></p>')
    return (f'<section class="apertura" data-cat="{slug_categoria(post.get("categoria"))}">'
            f'{etichetta(post, " <span class=grigio>· Apertura</span>")}'
            f'<h2><a href="{esc(url)}">{esc(post.get("titolo"))}</a></h2>'
            f'<p class="attacco">{esc(attacco(post))}</p>{griglia}{piede}</section>')


def blocco_articolo(post: dict, data_iso: str, root: str) -> str:
    url = root + permalink(data_iso, post.get("slug", ""))
    nomi = fonti(post)
    return (f'<article class="articolo" data-cat="{slug_categoria(post.get("categoria"))}">'
            f'{etichetta(post)}<h3><a href="{esc(url)}">{esc(post.get("titolo"))}</a></h3>'
            f'<p class="attacco-breve">{esc(attacco(post))}</p>'
            + (f'<p class="fonti">{esc(", ".join(nomi))}</p>' if nomi else "")
            + "</article>")


def voce_rassegna(it: dict) -> str:
    return (f'<li><a href="{esc(it.get("link"))}" rel="noopener">{esc(it.get("titolo"))}</a>'
            f'<span class="fonti">{esc(it.get("fonte"))}</span></li>')


def blocco_rassegna(rassegna: list) -> str:
    if not rassegna:
        return ""
    visibili, altri = rassegna[:RASSEGNA_IN_BREVE], rassegna[RASSEGNA_IN_BREVE:]
    out = ('<p class="titoletto">In breve</p><ul class="rassegna">'
           + "".join(voce_rassegna(i) for i in visibili) + "</ul>")
    if altri:
        out += (f'<details class="rassegna-tutta"><summary>Mostra tutta la rassegna ({len(rassegna)})</summary>'
                '<ul class="rassegna">' + "".join(voce_rassegna(i) for i in altri) + "</ul></details>")
    return out


def barra_laterale(edizione: dict, temi: list, euro, root: str) -> str:
    parti = []
    if temi:
        massimo = temi[0][1]
        righe = "".join(
            f'<li><span class="tema">{esc(t.replace("-", " "))}</span>'
            f'<span class="barra" aria-hidden="true"><span style="width:{round(100 * n / massimo)}%"></span></span>'
            f'<span class="numero">{n}</span></li>' for t, n in temi)
        parti.append('<section><h3 class="titolo-riquadro">Temi del mese</h3>'
                     '<p class="nota">Articoli che trattano il tema, ultimi 30 giorni di edizioni.</p>'
                     f'<ul class="temi">{righe}</ul></section>')
    n = len(edizione.get("post", []))
    con_prosp = sum(1 for p in edizione.get("post", []) if p.get("prospettive"))
    costo = f"<br>Costo di produzione: € {euro:.2f}".replace(".", ",") if euro else ""
    parti.append('<section class="riquadro"><h3>L’edizione del giorno</h3>'
                 f'<p>{n} articoli · {con_prosp} con prospettive{costo}</p>'
                 f'<p><a href="{root}costi.html">Come lavoriamo e quanto costa</a></p></section>')
    return '<aside class="laterale">' + "".join(parti) + "</aside>"


def barra_edizioni(edizioni: list, i: int, root: str) -> str:
    d = date.fromisoformat(edizioni[i]["data"][:10])
    pezzi = []
    if i + 1 < len(edizioni):
        prec = edizioni[i + 1]["data"][:10]
        pezzi.append(f'<a class="bottone" href="{root}{CARTELLA_EDIZIONI}/{prec}.html">'
                     f'← Edizione {del_giorno(date.fromisoformat(prec))}</a>')
    if i > 0:
        succ = edizioni[i - 1]["data"][:10]
        dest = f"{root}index.html" if i == 1 else f"{root}{CARTELLA_EDIZIONI}/{succ}.html"
        pezzi.append(f'<a class="bottone" href="{dest}">'
                     f'Edizione {del_giorno(date.fromisoformat(succ))} →</a>')
    pezzi.append(f'<a href="{root}{d.year}/{d.month:02d}/index.html">Tutte le edizioni del mese</a>')
    pezzi.append(f'<a class="a-destra" href="{root}feed.xml">RSS</a>')
    return f'<nav class="edizioni" aria-label="Edizioni">{"".join(pezzi)}</nav>'


# ── Pagina ───────────────────────────────────────────────────────────────────

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#F5F0E8;color:#1A1A1A;font-family:'PT Serif',Georgia,serif}
a{color:#1A1A1A}a:hover{color:#c0392b}
a:focus-visible,button:focus-visible,summary:focus-visible{outline:3px solid #c0392b;outline-offset:2px}
.contenitore{max-width:1200px;margin:0 auto;padding:0 40px}
.riga-alta{border-bottom:1px solid #CFC7B8;font-family:'PT Sans',Arial,sans-serif;font-size:13px;color:#4A4A4A}
.riga-alta .contenitore{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 24px;padding-top:10px;padding-bottom:10px}
.riga-alta a{color:#4A4A4A}
header.testata{text-align:center;padding:28px 40px 22px}
header.testata h1{margin:0;font-size:68px;line-height:1;font-weight:700;font-variant:small-caps;letter-spacing:.03em}
header.testata h1 a{text-decoration:none}
header.testata p{margin:10px 0 0;font-style:italic;color:#4A4A4A;font-size:17px}
header.testata p.ultima{font-family:'PT Sans',Arial,sans-serif;font-style:normal;font-size:13px}
.doppia-riga{max-width:1200px;margin:20px auto 0;border-top:3px solid #1A1A1A;border-bottom:1px solid #1A1A1A;height:4px}
nav.sezioni{background:#1A1A1A;overflow-x:auto;white-space:nowrap;scrollbar-width:none}
nav.sezioni::-webkit-scrollbar{display:none}
nav.sezioni .contenitore{display:flex;gap:0 28px;font-family:'PT Sans',Arial,sans-serif;font-size:14px;text-transform:uppercase;letter-spacing:.08em}
nav.sezioni a{color:#F5F0E8;text-decoration:none;padding:15px 0 12px;border-bottom:3px solid transparent;display:inline-block}
nav.sezioni a.attivo{border-bottom-color:#c0392b}
nav.sezioni a.separato{padding-left:28px;border-left:1px solid #5A5A5A}
.sottosezioni{background:#E3DCCD}
.sottosezioni .contenitore{display:flex;flex-wrap:wrap;gap:8px;padding-top:10px;padding-bottom:10px;font-family:'PT Sans',Arial,sans-serif;font-size:13px}
.sottosezioni button{min-height:44px;padding:0 14px;border-radius:22px;border:1px solid #A39B8C;background:#FFF;color:#1A1A1A;font:inherit;cursor:pointer}
.sottosezioni button[aria-pressed=true]{background:#c0392b;border-color:#c0392b;color:#FFF}
nav.edizioni{max-width:1200px;margin:0 auto;padding:12px 40px;display:flex;flex-wrap:wrap;align-items:center;gap:10px 18px;font-family:'PT Sans',Arial,sans-serif;font-size:14px;border-bottom:1px solid #CFC7B8}
nav.edizioni a{color:#4A4A4A}
nav.edizioni a.bottone{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;border:1px solid #A39B8C;background:#FFF;color:#1A1A1A;text-decoration:none}
nav.edizioni .a-destra{margin-left:auto}
main{max-width:1200px;margin:0 auto;padding:36px 40px 56px}
.in-alto{display:flex;flex-wrap:wrap;gap:40px}
.apertura{flex:999 1 620px;min-width:0}
.sezione{margin:0 0 10px;font-family:'PT Sans',Arial,sans-serif;font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase}
.grigio{color:#4A4A4A}
.apertura h2{margin:0;font-size:46px;line-height:1.1}
.apertura h2 a,.articolo h3 a{text-decoration:none}
.attacco{margin:18px 0 0;font-size:21px;line-height:1.45;color:#2E2E2E;max-width:46em}
.tre-colonne{margin-top:28px;display:flex;flex-wrap:wrap;border-top:1px solid #1A1A1A;border-bottom:1px solid #CFC7B8}
.colonna{flex:1 1 220px;padding:18px 20px;font-size:15px;line-height:1.5}
.colonna:first-child{padding-left:0}
.colonna+.colonna{border-left:1px solid #CFC7B8}
.colonna ul{margin:0;padding-left:18px}.colonna p{margin:0}
.titoletto{margin:0 0 8px;font-family:'PT Sans',Arial,sans-serif;font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#4A4A4A}
.titoletto.accento{color:#c0392b}
.citazione-lettura{font-style:italic}
.piede-apertura{margin:16px 0 0;display:flex;flex-wrap:wrap;gap:8px 20px;justify-content:space-between;font-family:'PT Sans',Arial,sans-serif;font-size:13px;color:#4A4A4A}
.piede-apertura a{font-weight:700}
.laterale{flex:1 1 300px;min-width:0;display:flex;flex-direction:column;gap:32px}
.titolo-riquadro{margin:0 0 4px;font-size:20px;padding-bottom:8px;border-bottom:2px solid #1A1A1A}
.nota{margin:8px 0 14px;font-family:'PT Sans',Arial,sans-serif;font-size:13px;color:#4A4A4A}
.temi{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:9px;font-family:'PT Sans',Arial,sans-serif;font-size:14px}
.temi li{display:flex;align-items:center;gap:10px}
.temi .tema{flex:0 0 132px}.temi .barra{flex:1 1 auto;height:10px;background:#E3DCCD}
.temi .barra span{display:block;height:10px;background:#1A1A1A}
.temi .numero{flex:0 0 28px;text-align:right;font-weight:700}
.riquadro{background:#EAE3D5;padding:18px 20px}
.riquadro h3{margin:0 0 10px;font-size:18px}
.riquadro p{margin:0;font-family:'PT Sans',Arial,sans-serif;font-size:14px;line-height:1.6}
.riquadro p+p{margin-top:12px;font-size:13px}.riquadro a{font-weight:700}
.gruppi{margin-top:44px;padding-top:28px;border-top:3px solid #1A1A1A;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0 40px}
.gruppo h2{margin:0 0 16px;font-size:20px;padding-bottom:8px;border-bottom:2px solid #1A1A1A;scroll-margin-top:16px}
.articolo{padding-bottom:22px}
.articolo h3{margin:0;font-size:20px;line-height:1.25}
.attacco-breve{margin:8px 0 0;font-size:15px;line-height:1.55;color:#2E2E2E}
.fonti{display:block;margin:6px 0 0;font-family:'PT Sans',Arial,sans-serif;font-size:13px;color:#4A4A4A}
.rassegna{list-style:none;margin:0;padding:0}
.rassegna li{padding:10px 0;border-bottom:1px solid #CFC7B8;font-size:16px;line-height:1.4}
.rassegna li a{text-decoration:none}
.rassegna-tutta summary{margin-top:10px;display:inline-flex;align-items:center;min-height:44px;padding:0 14px;border:1px solid #A39B8C;font-family:'PT Sans',Arial,sans-serif;font-size:14px;font-weight:700;color:#c0392b;cursor:pointer;list-style:none}
.rassegna-tutta summary::-webkit-details-marker{display:none}
.rassegna-tutta[open] summary{margin-bottom:4px}
[hidden]{display:none!important}
footer{background:#1A1A1A;color:#D8D2C6;text-align:center}
footer .contenitore{padding-top:32px;padding-bottom:36px;font-family:'PT Sans',Arial,sans-serif;font-size:13px;line-height:1.9}
footer a{color:#F5F0E8}
@media (max-width:640px){
 .contenitore,main,nav.edizioni{padding-left:18px;padding-right:18px}
 header.testata{padding:22px 18px 18px}
 header.testata h1{font-size:40px}
 header.testata p{font-size:15px}
 nav.sezioni .contenitore{gap:0 18px}
 .apertura h2{font-size:32px}
 .attacco{font-size:18px}
 .colonna{flex-basis:100%;padding-left:0;padding-right:0}
 .colonna+.colonna{border-left:0;border-top:1px solid #CFC7B8}
 nav.edizioni .a-destra{margin-left:0}
}
"""

# Filtri per sezione: nasconde o mostra ciò che è già nella pagina.
JS = """
(function () {
  var nav = document.querySelectorAll('nav.sezioni a[data-gruppo]');
  var barra = document.querySelector('.sottosezioni');
  var gruppi = document.querySelectorAll('.gruppo');
  var apertura = document.querySelector('.apertura');
  var inAlto = document.querySelector('.in-alto');
  var stato = { gruppo: 'tutte', cat: null };
  function applica() {
    nav.forEach(function (a) { a.classList.toggle('attivo', a.dataset.gruppo === stato.gruppo); });
    var tutte = stato.gruppo === 'tutte';
    gruppi.forEach(function (g) {
      g.hidden = !tutte && g.dataset.gruppo !== stato.gruppo;
      var visibili = 0;
      g.querySelectorAll('.articolo').forEach(function (art) {
        art.hidden = !!stato.cat && art.dataset.cat !== stato.cat;
        if (!art.hidden) visibili++;
      });
      if (stato.cat && !visibili && !g.querySelector('.rassegna')) g.hidden = true;
    });
    if (apertura) {
      var cat = apertura.dataset.cat, membri = '';
      nav.forEach(function (a) { if (a.dataset.gruppo === stato.gruppo) membri = a.dataset.membri || ''; });
      inAlto.hidden = !(tutte || (membri.split(' ').indexOf(cat) >= 0 && (!stato.cat || stato.cat === cat)));
    }
    barra.querySelectorAll('button').forEach(function (b) {
      b.hidden = b.dataset.gruppo !== stato.gruppo;
      b.setAttribute('aria-pressed', b.dataset.cat === stato.cat ? 'true' : 'false');
    });
    var visibili = barra.querySelectorAll('button:not([hidden])').length;
    barra.hidden = visibili < 2;
  }
  nav.forEach(function (a) {
    a.addEventListener('click', function (ev) {
      ev.preventDefault();
      stato = { gruppo: a.dataset.gruppo, cat: null };
      applica();
    });
  });
  barra.querySelectorAll('button').forEach(function (b) {
    b.addEventListener('click', function () {
      stato.cat = stato.cat === b.dataset.cat ? null : b.dataset.cat;
      applica();
    });
  });
  applica();
})();
"""


def pagina(edizioni: list, i: int, temi: list, costi: dict, rassegna: list, prima: bool) -> str:
    ed = edizioni[i]
    data_iso = ed["data"][:10]
    d = date.fromisoformat(data_iso)
    root = "" if prima else "../"
    posts = ed.get("post", [])
    evidenza = next((p for p in posts if p.get("evidenza")), posts[0] if posts else None)
    altri = [p for p in posts if p is not evidenza]

    per_cat = {}
    for p in altri:
        per_cat.setdefault(slug_categoria(p.get("categoria")), []).append(p)

    sezioni_html, bottoni = [], []
    for gid, nome, membri in GRUPPI:
        articoli = [p for m in membri for p in per_cat.get(m, [])]
        presenti = [m for m in membri if per_cat.get(m)]
        if evidenza and slug_categoria(evidenza.get("categoria")) in membri:
            presenti = [slug_categoria(evidenza.get("categoria"))] + [m for m in presenti if m != slug_categoria(evidenza.get("categoria"))]
        corpo = "".join(blocco_articolo(p, data_iso, root) for p in articoli)
        if gid == "sport" and prima:
            corpo += blocco_rassegna(rassegna)
        if not corpo:
            continue
        sezioni_html.append(f'<section class="gruppo" id="{gid}" data-gruppo="{gid}">'
                            f'<h2>{esc(nome)}</h2>{corpo}</section>')
        for m in presenti:
            cat = next(p.get("categoria") for p in posts if slug_categoria(p.get("categoria")) == m)
            bottoni.append(f'<button type="button" data-gruppo="{gid}" data-cat="{m}" '
                           f'aria-pressed="false" hidden>{esc(cat)}</button>')

    voci = ['<a href="#apertura" data-gruppo="tutte" class="attivo">Tutte</a>']
    voci += [f'<a href="#{gid}" data-gruppo="{gid}" data-membri="{" ".join(m)}">{esc(n)}</a>'
             for gid, n, m in GRUPPI]
    voci.append(f'<a class="separato" href="{root}archivio.html">Archivio</a>')

    url_pagina = f"{SITO}/" if prima else f"{SITO}/{CARTELLA_EDIZIONI}/{data_iso}.html"
    titolo = ("Il Corrispondente IA" if prima
              else f"Edizione {del_giorno(d)} {d.year} — Il Corrispondente IA")
    robots = "" if prima or INDICIZZA_EDIZIONI else '\n<meta name="robots" content="noindex, follow">'

    in_alto = ""
    if evidenza:
        in_alto = (f'<div class="in-alto" id="apertura">{blocco_apertura(evidenza, data_iso, root)}'
                   f'{barra_laterale(ed, temi, costo_euro(costi, data_iso), root) if prima else ""}</div>')

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(titolo)}</title>
<meta name="description" content="{esc(DESCRIZIONE)}">{robots}
<link rel="canonical" href="{url_pagina}">
<link rel="alternate" type="application/rss+xml" title="Il Corrispondente IA" href="{SITO}/feed.xml">
<meta property="og:type" content="website">
<meta property="og:url" content="{url_pagina}">
<meta property="og:title" content="{esc(titolo)}">
<meta property="og:description" content="{esc(DESCRIZIONE)}">
<meta property="og:image" content="{SITO}/assets/img/og-cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(titolo)}">
<meta name="twitter:description" content="{esc(DESCRIZIONE)}">
<meta name="twitter:image" content="{SITO}/assets/img/og-cover.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=PT+Serif:ital,wght@0,400;0,700;1,400&amp;family=PT+Sans:wght@400;700&amp;display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="riga-alta"><div class="contenitore">
<span>{data_lunga(d)} · Edizione del giorno</span>
<span><a href="{root}chi-siamo.html">Chi siamo</a> · <a href="{root}prompt.html">Il prompt</a> · <a href="{root}costi.html">Costi</a> · <a href="{root}feed.xml">RSS</a> · <a href="https://t.me/il_corrispondente_ia">Telegram</a></span>
</div></div>
<header class="testata">
<h1><a href="{root}index.html">Il Corrispondente IA</a></h1>
<p>{esc(TESTATA_SOTTOTITOLO)}</p>
<p>{esc(TESTATA_MOTTO)}</p>
<p class="ultima">{esc(TESTATA_ULTIMA)}</p>
<div class="doppia-riga"></div>
</header>
<nav class="sezioni" aria-label="Sezioni"><div class="contenitore">{"".join(voci)}</div></nav>
<div class="sottosezioni" hidden><div class="contenitore">{"".join(bottoni)}</div></div>
{barra_edizioni(edizioni, i, root)}
<main>
{in_alto}
<div class="gruppi">{"".join(sezioni_html)}</div>
</main>
<footer><div class="contenitore">
Il Corrispondente IA — Tutti i diritti satiricamente riservati<br>
Nessuna notizia è stata danneggiata durante la produzione di questo contenuto<br>
Generato ogni mattina da Claude (Anthropic) · <a href="{root}chi-siamo.html">Chi siamo</a> · <a href="{root}prompt.html">Il prompt</a> · <a href="{root}costi.html">Costi</a> · <a href="{root}feed.xml">RSS</a> · <a href="https://t.me/il_corrispondente_ia">Telegram</a> · <a href="https://filoclastos.it/licenze-copyright/">Licenze e copyright</a> · <a href="https://filoclastos.it/dichiarazione-bias/">Dichiarazione sul bias</a>
</div></footer>
<script>{JS}</script>
<script data-goatcounter="https://il-corrispondente.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</body>
</html>
"""


def prepara() -> dict:
    """{percorso: contenuto} per tutte le pagine. Non scrive niente."""
    edizioni = [e for e in carica(POSTS_FILE, {}).get("edizioni", []) if e.get("data") and e.get("post")]
    edizioni.sort(key=lambda e: e["data"], reverse=True)
    if not edizioni:
        raise RuntimeError("posts.json non contiene edizioni")
    costi = carica(COSTI_FILE, {})
    rassegna = carica(RASSEGNA_FILE, {}).get("item", [])
    temi = temi_del_mese(edizioni)
    pagine = {os.path.join(DOCS, "index.html"): pagina(edizioni, 0, temi, costi, rassegna, prima=True)}
    for i, e in enumerate(edizioni):
        percorso = os.path.join(DOCS, CARTELLA_EDIZIONI, f'{e["data"][:10]}.html')
        pagine[percorso] = pagina(edizioni, i, temi, costi, rassegna, prima=False)
    return pagine


def main() -> int:
    try:
        pagine = prepara()
    except Exception:
        print("⚠ Prima pagina NON ricostruita: restano le pagine precedenti.")
        traceback.print_exc()
        return 0
    os.makedirs(os.path.join(DOCS, CARTELLA_EDIZIONI), exist_ok=True)
    for percorso, contenuto in pagine.items():
        with open(percorso, "w", encoding="utf-8") as f:
            f.write(contenuto)
    print(f"✓ Prima pagina e {len(pagine) - 1} pagine delle edizioni scritte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
