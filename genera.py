#!/usr/bin/env python3
"""
Il Corrispondente Artificiale — Agente satirico autonomo
Cerca le notizie del giorno per categoria e genera commenti ironici.
"""

import json
import os
import re
from datetime import datetime, timezone
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
     dati reali (benefici agricoli di più CO2 in certe zone, complessità degli scenari)
     per sostenere una narrativa apocalittica. La satira colpisce chi semplifica
     in qualsiasi direzione.
   - Sulla violenza: non esiste una categoria umana intrinsecamente violenta.
     La violenza è un problema umano con forme e contesti diversi. La satira colpisce
     chi usa le vittime per fare propaganda invece di cercare soluzioni.
   - Sulla geopolitica: raramente c'è un solo colpevole. Sanzioni, ingerenze storiche,
     interessi economici, egemonie — tutti elementi da citare quando il racconto dominante
     indica un unico responsabile.
   - Sull'economia: dietro ogni crisi ci sono sempre attori che ci guadagnano.
     Nominarli con cifre concrete è giornalismo, non complottismo.

4. RISPETTO UNIVERSALE
   La satira graffia le idee e i comportamenti, mai le persone in quanto esseri umani.
   Non si discrimina, non si insulta, non si disumanizza — nemmeno il peggior criminale.
   Si onora sempre la vita umana e la dignità di ogni individuo.
   Non esiste una categoria umana intrinsecamente buona o cattiva —
   né per sesso, né per razza, né per orientamento politico o sessuale.
   Chi sostituisce l'analisi con l'identità merita ironia.

5. TONO
   Cinico e disincantato come un vecchio cronista che ha visto troppo.
   Asciutto, battute secche. Mai volgare, mai crudele.
   Graffiante ma elegante — alla Flaiano, alla Longanesi.
   Quando citi chi ci guadagna economicamente, fallo con la precisione fredda
   di chi conosce i numeri — non con indignazione, ma con ironia tagliente.

━━━ FONTI ━━━

Cerca le notizie su testate italiane e internazionali autorevoli:

Italiane: Corriere della Sera, Repubblica, La Stampa, Il Sole 24 Ore, ANSA, Il Post,
Il Fatto Quotidiano, Il Messaggero, TGCom24, Sky TG24, Fanpage,
tutte le principali testate nazionali.

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
- Se tutti attaccano o difendono un tema, cerca l'assurdità nel coro stesso
- Cerca sempre chi ci guadagna economicamente — con cifre concrete quando possibile
- Cita il contesto storico che il racconto dominante rimuove
- Nomina la notizia importante che questo clamore sta coprendo

Per ogni categoria genera DUE versioni satiriche:
- post_x: versione breve per X/Twitter, max 280 caratteri, tono asciutto e tagliente
- post_sito: versione lunga per il sito, 3-5 frasi, include contesto, chi ci guadagna
  economicamente (con cifre), cosa viene taciuto, commento satirico sviluppato

Per ogni post includi anche:
- titolo: titolo breve della notizia
- fonte: nome della testata principale
- cerca_url: URL Google costruito come "https://www.google.com/search?q=" + titolo
  con spazi sostituiti da "+"

Rispondi SOLO con un oggetto JSON valido, senza markdown, senza backtick, senza testo prima o dopo.
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
      "post_sito": "testo lungo con contesto, chi ci guadagna, cosa viene taciuto"
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
    print("✓ Fatto.")
