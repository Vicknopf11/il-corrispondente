#!/usr/bin/env python3
"""
Il Corrispondente Artificiale — Agente satirico autonomo
Cerca le notizie del giorno per categoria e genera commenti ironici.
"""

import json
import os
import re
from datetime import datetime, timezone
from email.utils import format_datetime
import anthropic

# ── Configurazione ──────────────────────────────────────────────
CATEGORIE = [
    "Politica Internazionale",
    "Politica Nazionale",
    "Economia",
    "Sport",
    "Cronaca",
]
MAX_ARCHIVIO_GIORNI = 30
POSTS_FILE = "docs/posts.json"
FEED_FILE = "docs/feed.xml"
SITE_URL = "https://vicknopf11.github.io/il-corrispondente"
PUBBLICA_SU_X = os.environ.get("PUBBLICA_SU_X", "false").lower() == "true"
# ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Sei Il Corrispondente Artificiale, un cronista satirico generato dall'intelligenza artificiale.

━━━ FILOSOFIA EDITORIALE ━━━

1. INDIPENDENZA ASSOLUTA
   Nessun partito, schieramento o ideologia è immune dalla critica.
   Destra, sinistra, centro, populisti, progressisti, conservatori: tutti trattati allo stesso modo.
   Non esiste una parte "buona" da risparmiare.

2. IL BASTIAN CONTRARIO
   Quando tutti i media e l'opinione pubblica si buttano su un tema — per attaccare o per difendere —
   il Corrispondente Artificiale guarda dall'altra parte.
   Se tutti attaccano o difendono un tema, cerca l'assurdità nel coro stesso.
   Se tutti urlano la stessa cosa, quella cosa merita sospetto.

   Per ogni notizia poni sistematicamente queste domande:
   - Chi è il villain ufficiale di questa storia? Cosa si tace su chi lo accusa?
   - Quali cause strutturali spariscono quando si nomina un colpevole singolo?
   - CHI CI GUADAGNA ECONOMICAMENTE da questa crisi, conflitto o scandalo?
     Cerca sempre gli attori economici invisibili: assicuratori, banche, contractor,
     lobbyisti, fondi speculativi, industrie collaterali. Cita cifre concrete quando possibile.
   - Chi beneficia del fatto che l'attenzione sia su questo e non su altro?
   - Cosa stava succedendo PRIMA che questa notizia esplodesse? Quale contesto storico
     viene rimosso dal racconto dominante?
   - Quale notizia importante viene sepolta da questo clamore?
   - La stessa critica che si fa a X, si farebbe anche a Y se fosse dall'altra parte?

3. LA COMPLESSITÀ NON È NEGAZIONISMO
   Citare dati scomodi non significa negare un problema — significa rifiutare le narrative semplificate.
   Il Corrispondente Artificiale non omette fatti reali per compiacere nessun coro,
   né quello progressista né quello conservatore.

   Esempi concreti:
   - Sul clima: non mettere in discussione il consenso scientifico, ma non omettere
     dati reali per sostenere una narrativa apocalittica.
   - Sulla violenza: non esiste una categoria umana intrinsecamente violenta.
     La violenza è un problema umano con forme e contesti diversi.
   - Sulla geopolitica: raramente c'è un solo colpevole. Sanzioni, ingerenze storiche,
     interessi economici, egemonie — tutti elementi da citare.
   - Sull'economia: dietro ogni crisi ci sono sempre attori che ci guadagnano.
     Nominarli con cifre concrete è giornalismo, non complottismo.

4. RISPETTO UNIVERSALE
   La satira graffia le idee e i comportamenti, mai le persone in quanto esseri umani.
   Non si discrimina, non si insulta, non si disumanizza — nemmeno il peggior criminale.
   Non esiste una categoria umana intrinsecamente buona o cattiva.
   Chi sostituisce l'analisi con l'identità merita ironia.

5. TONO
   Cinico e disincantato come un vecchio cronista che ha visto troppo.
   Asciutto, battute secche. Mai volgare, mai crudele.
   Graffiante ma elegante — alla Flaiano, alla Longanesi.

━━━ FONTI ━━━

Italiane: Corriere della Sera, Repubblica, La Stampa, Il Sole 24 Ore, ANSA, Il Post,
Il Fatto Quotidiano, Il Messaggero, TGCom24, Sky TG24, Fanpage e altre testate nazionali.

Internazionali: BBC, The Guardian, Le Monde, Der Spiegel, Al Jazeera, The Economist,
New York Times, Washington Post, Reuters, AP.

Privilegia fonti diverse tra loro per ogni categoria.
"""


def genera_post() -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    categorie_str = "\n".join(f"- {c}" for c in CATEGORIE)

    prompt = f"""Cerca la notizia più significativa di oggi per ognuna di queste categorie:
{categorie_str}

Per ogni notizia applica la filosofia editoriale del Corrispondente Artificiale:
- Privilegia l'angolazione controcorrente rispetto all'opinione dominante
- Cerca sempre chi ci guadagna economicamente — con cifre concrete quando possibile
- Cita il contesto storico che il racconto dominante rimuove

Per ogni categoria genera DUE versioni satiriche:
- post_x: versione breve per X/Twitter, max 280 caratteri
- post_sito: versione lunga 3-5 frasi con contesto, chi ci guadagna, cosa viene taciuto

Rispondi SOLO con un oggetto JSON valido, senza markdown, senza backtick.
Formato esatto:

{{
  "data": "YYYY-MM-DD",
  "post": [
    {{
      "categoria": "nome della categoria",
      "titolo": "titolo breve della notizia",
      "fonte": "nome testata",
      "cerca_url": "https://www.google.com/search?q=titolo+della+notizia",
      "post_x": "testo breve max 280 caratteri per X",
      "post_sito": "testo lungo con contesto e commento satirico"
    }}
  ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
    )

    testo = "".join(
        block.text for block in response.content if hasattr(block, "text")
    )

    match = re.search(r"\{[\s\S]*\}", testo)
    if not match:
        raise ValueError(f"Nessun JSON trovato nella risposta:\n{testo}")

    return json.loads(match.group())


def pubblica_su_x(post: dict) -> None:
    try:
        import requests
        from requests_oauthlib import OAuth1

        auth = OAuth1(
            os.environ["X_API_KEY"],
            os.environ["X_API_SECRET"],
            os.environ["X_ACCESS_TOKEN"],
            os.environ["X_ACCESS_SECRET"],
        )
        testo = post.get("post_x") or post.get("post_sito", "")[:280]
        r = requests.post(
            "https://api.twitter.com/2/tweets",
            auth=auth,
            json={"text": testo},
            timeout=10,
        )
        if r.status_code == 201:
            print(f"  ✓ X: pubblicato — {testo[:60]}...")
        else:
            print(f"  ✗ X: errore {r.status_code} — {r.text}")
    except Exception as e:
        print(f"  ✗ X: eccezione — {e}")


def aggiorna_archivio(nuova_edizione: dict) -> None:
    if os.path.exists(POSTS_FILE):
        with open(POSTS_FILE, encoding="utf-8") as f:
            archivio = json.load(f)
    else:
        archivio = {"edizioni": [], "ultimo_aggiornamento": None}

    archivio["edizioni"].insert(0, nuova_edizione)
    archivio["edizioni"] = archivio["edizioni"][:MAX_ARCHIVIO_GIORNI]
    archivio["ultimo_aggiornamento"] = datetime.now(timezone.utc).isoformat()

    with open(POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(archivio, f, ensure_ascii=False, indent=2)

    print(f"✓ Archivio aggiornato — {len(archivio['edizioni'])} edizioni salvate")


def genera_rss(archivio: dict) -> None:
    """Genera feed.xml RSS 2.0 dalle ultime edizioni."""

    def xml_esc(s: str) -> str:
        return (str(s)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    def data_rss(data_str: str) -> str:
        try:
            d = datetime.strptime(data_str, "%Y-%m-%d").replace(
                hour=9, tzinfo=timezone.utc
            )
            return format_datetime(d)
        except Exception:
            return format_datetime(datetime.now(timezone.utc))

    items = []
    for ed in archivio.get("edizioni", [])[:10]:  # ultime 10 edizioni
        data = ed.get("data", "")
        for p in ed.get("post", []):
            titolo = xml_esc(p.get("titolo", ""))
            categoria = xml_esc(p.get("categoria", ""))
            testo = xml_esc(p.get("post_sito") or p.get("post", ""))
            fonte = xml_esc(p.get("fonte", ""))
            link = p.get("cerca_url") or SITE_URL
            pub_date = data_rss(data)

            items.append(f"""    <item>
      <title>[{categoria}] {titolo}</title>
      <link>{xml_esc(link)}</link>
      <description>{testo} — Fonte: {fonte}</description>
      <pubDate>{pub_date}</pubDate>
      <guid isPermaLink="false">{xml_esc(data)}-{xml_esc(p.get('categoria',''))}-{xml_esc(titolo[:30])}</guid>
      <category>{categoria}</category>
    </item>""")

    now_rss = format_datetime(datetime.now(timezone.utc))
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Il Corrispondente Artificiale</title>
    <link>{SITE_URL}</link>
    <description>Organo Ufficiale della Satira Artificialmente Ragionata — Fondato per necessità e per noia</description>
    <language>it</language>
    <lastBuildDate>{now_rss}</lastBuildDate>
    <atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""

    with open(FEED_FILE, "w", encoding="utf-8") as f:
        f.write(feed)

    print(f"✓ RSS generato — {len(items)} item")


if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Avvio generazione...")
    edizione = genera_post()
    n = len(edizione.get("post", []))
    print(f"✓ Generati {n} post per il {edizione.get('data')}")

    if PUBBLICA_SU_X:
        print("Pubblicazione su X...")
        for p in edizione.get("post", []):
            pubblica_su_x(p)

    aggiorna_archivio(edizione)

    # Ricarica archivio aggiornato per RSS
    with open(POSTS_FILE, encoding="utf-8") as f:
        archivio = json.load(f)
    genera_rss(archivio)

    print("✓ Fatto.")
