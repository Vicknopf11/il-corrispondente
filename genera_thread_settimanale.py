#!/usr/bin/env python3
"""
Il Corrispondente Artificiale — Thread settimanale di approfondimento su X
Ogni sabato, il modello rilegge le edizioni degli ultimi 7 giorni, scelte
autonomamente in base a rilevanza/impatto (non necessariamente l'ultima
uscita), e sceglie UN SOLO articolo su cui costruire un thread breve
(2-3 tweet) di approfondimento. Il thread punta sempre allo stesso
permalink — non è un giro tra notizie diverse, è un "torniamo su questa".
"""

import json
import os
import re
from datetime import date, datetime, timedelta

import anthropic

# Riusa la filosofia editoriale e le costanti già definite in genera.py,
# invece di duplicarle: un solo punto di verità per il registro satirico.
from genera import SYSTEM_PROMPT, SITE_URL, SLUG_VALIDO

POSTS_FILE = "docs/posts.json"
CODA_THREAD_FILE = "coda_thread_x.json"
GIORNI_FINESTRA = 7
MIN_TWEET = 2
MAX_TWEET = 3


def carica_edizioni_settimana() -> list[dict]:
    """Filtra le edizioni degli ultimi 7 giorni (rolling, oggi incluso)."""
    if not os.path.exists(POSTS_FILE):
        raise FileNotFoundError(f"{POSTS_FILE} non trovato — genera.py è già girato?")

    with open(POSTS_FILE, encoding="utf-8") as f:
        archivio = json.load(f)

    oggi = date.today()
    soglia = oggi - timedelta(days=GIORNI_FINESTRA - 1)

    edizioni_settimana = []
    for ed in archivio.get("edizioni", []):
        try:
            data_ed = datetime.strptime(ed["data"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if soglia <= data_ed <= oggi:
            edizioni_settimana.append(ed)

    return edizioni_settimana


def costruisci_digest(edizioni: list[dict]) -> str:
    """Digest compatto delle notizie della settimana, con riferimento
    univoco (data + slug) per ogni articolo, così il modello può
    citarlo esattamente nella risposta."""
    righe = []
    for ed in edizioni:
        for p in ed.get("post", []):
            slug = p.get("slug")
            if not slug:
                continue
            righe.append(
                f"- data={ed['data']} slug={slug} categoria={p.get('categoria', '')} "
                f"evidenza={p.get('evidenza', False)}\n"
                f"  titolo: {p.get('titolo', '')}\n"
                f"  sintesi: {p.get('post_x', '')[:200]}"
            )
    return "\n".join(righe)


PROMPT_UTENTE_TEMPLATE = """Sotto trovi il digest delle notizie pubblicate da Il Corrispondente
Artificiale negli ultimi 7 giorni. Ogni notizia è identificata univocamente
da data+slug.

{digest}

Scegli UNA sola notizia — quella che, con lo sguardo di fine settimana,
risulta la più rilevante o quella che merita un ritorno con più respiro
(non necessariamente la più recente, né necessariamente quella che era
segnata evidenza:true nel giorno in cui è uscita).

Scrivi un thread di approfondimento su X, breve, {min_tweet}-{max_tweet} tweet,
che riprenda quella notizia con più respiro rispetto al post_x originale —
stessa filosofia editoriale (bastian contrario, chi ci guadagna, contesto
storico rimosso dal racconto dominante), ma con lo spazio di più tweet per
sviluppare l'argomento con un ordine logico: apertura che aggancia,
sviluppo che approfondisce, chiusura che lascia una domanda o un'affilata
finale. NON includere link nei testi dei tweet: il link al permalink verrà
aggiunto automaticamente in coda all'ultimo tweet dallo script.

Ogni tweet singolarmente deve restare sotto 280 caratteri (l'ultimo deve
restare sotto 250, per lasciare spazio al link che verrà aggiunto dopo).

Rispondi SOLO con un oggetto JSON valido, senza markdown, senza backtick.
Formato esatto:

{{
  "data_riferimento": "YYYY-MM-DD",
  "slug_riferimento": "slug-esatto-dal-digest",
  "tweet": [
    "testo del primo tweet",
    "testo del secondo tweet"
  ]
}}"""


def genera_thread() -> dict:
    edizioni = carica_edizioni_settimana()
    if not edizioni:
        raise ValueError("Nessuna edizione trovata negli ultimi 7 giorni.")

    digest = costruisci_digest(edizioni)
    if not digest:
        raise ValueError("Digest vuoto — nessun post con slug valido nella finestra.")

    prompt = PROMPT_UTENTE_TEMPLATE.format(
        digest=digest, min_tweet=MIN_TWEET, max_tweet=MAX_TWEET
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    testo = "".join(block.text for block in response.content if hasattr(block, "text"))

    match = re.search(r"\{[\s\S]*\}", testo)
    if not match:
        raise ValueError(f"Nessun JSON trovato nella risposta:\n{testo}")

    thread = json.loads(match.group())
    return valida_thread(thread, edizioni)


def valida_thread(thread: dict, edizioni: list[dict]) -> dict:
    """Rete di sicurezza: verifica che data_riferimento+slug_riferimento
    corrispondano davvero a un articolo del digest. In caso di scelta
    invalida o assente, ricade sull'ultima notizia evidenza:true trovata
    nella finestra — non inventiamo mai un permalink a caso."""
    slug = thread.get("slug_riferimento")
    data_rif = thread.get("data_riferimento")

    esiste = False
    if isinstance(slug, str) and SLUG_VALIDO.match(slug):
        for ed in edizioni:
            if ed.get("data") == data_rif:
                if any(p.get("slug") == slug for p in ed.get("post", [])):
                    esiste = True
                    break

    if not esiste:
        fallback = None
        for ed in edizioni:
            for p in ed.get("post", []):
                if p.get("evidenza") is True:
                    fallback = (ed["data"], p["slug"])
        if fallback is None and edizioni and edizioni[0].get("post"):
            primo = edizioni[0]["post"][0]
            fallback = (edizioni[0]["data"], primo.get("slug"))
        if fallback:
            thread["data_riferimento"], thread["slug_riferimento"] = fallback

    tweet = thread.get("tweet")
    if not isinstance(tweet, list) or not all(isinstance(t, str) for t in tweet):
        raise ValueError(f"Campo 'tweet' malformato: {tweet!r}")
    thread["tweet"] = tweet[:MAX_TWEET] if len(tweet) > MAX_TWEET else tweet
    if len(thread["tweet"]) < MIN_TWEET:
        raise ValueError(f"Thread troppo corto ({len(thread['tweet'])} tweet)")

    return thread


def permalink(data_riferimento: str, slug: str) -> str | None:
    if not data_riferimento or not slug:
        return None
    parti = data_riferimento.split("-")
    if len(parti) != 3:
        return None
    anno, mese, giorno = parti
    return f"{SITE_URL}/{anno}/{mese}/{giorno}/{slug}/"


def crea_coda_thread(thread: dict) -> None:
    url = permalink(thread["data_riferimento"], thread["slug_riferimento"])
    coda = {
        "data": date.today().isoformat(),
        "articolo_riferimento": url,
        "pubblicato": False,
        "tweet": [{"testo": t} for t in thread["tweet"]],
    }
    with open(CODA_THREAD_FILE, "w", encoding="utf-8") as f:
        json.dump(coda, f, ensure_ascii=False, indent=2)
    print(f"✓ Thread settimanale creato — {len(coda['tweet'])} tweet, riferimento: {url}")


def main() -> None:
    thread = genera_thread()
    crea_coda_thread(thread)


if __name__ == "__main__":
    main()
