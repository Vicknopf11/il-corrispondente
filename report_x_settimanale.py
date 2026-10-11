#!/usr/bin/env python3
"""
Il Corrispondente IA — Report settimanale delle visualizzazioni su X.

Legge gli ultimi 7 giorni di post dell'account tramite l'API di X (con le
stesse credenziali di pubblica_tweet.py), li abbina agli articoli del sito
(categoria, evidenza) e stampa un riepilogo: visualizzazioni per categoria,
post con e senza link, post migliori. Il riepilogo va anche nel Summary della
run di GitHub Actions. Non scrive nulla nel repo e non pubblica niente.

Costo: l'API fa pagare la lettura per post restituito (da listino: $0,005 per
"Posts: Read", $0,001 per "Owned: Read"; non so quale delle due si applichi).
Con ~63 post a settimana, al massimo circa 32 centesimi per lancio.

ATTENZIONE: i nomi dei campi (public_metrics.impression_count) e il
comportamento dell'endpoint NON sono stati verificati contro l'API reale:
il primo lancio serve anche a questo, e gli errori vengono stampati per intero.
"""
import html
import json
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

POSTS_FILE = "docs/posts.json"
GIORNI = 7
PREZZO_MAX_PER_POST_USD = 0.005
DOMINIO_SITO = "corrispondente.filoclastos.it"


def _oauth():
    from requests_oauthlib import OAuth1
    return OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_SECRET"],
    )


def normalizza(testo: str) -> str:
    """Toglie link e differenze di spazi/entità HTML, per confrontare il testo
    di un post su X con il testo registrato in posts.json."""
    t = html.unescape(testo or "")
    t = re.sub(r"https?://\S+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def carica_articoli() -> dict:
    """{testo_normalizzato: {categoria, slug, evidenza}} dai post del sito."""
    if not os.path.exists(POSTS_FILE):
        return {}
    with open(POSTS_FILE, encoding="utf-8") as f:
        archivio = json.load(f)
    mappa = {}
    for ed in archivio.get("edizioni", []):
        for p in ed.get("post", []):
            chiave = normalizza(p.get("post_x") or "")
            if chiave:
                mappa[chiave] = {
                    "categoria": p.get("categoria", "?"),
                    "slug": p.get("slug"),
                    "evidenza": bool(p.get("evidenza")),
                }
    return mappa


def abbina(testo: str, mappa: dict):
    n = normalizza(testo)
    if n in mappa:
        return mappa[n]
    if len(n) >= 40:  # ripiego: stesso inizio
        for chiave, info in mappa.items():
            if chiave.startswith(n[:40]):
                return info
    return None


def leggi_post(giorni: int = GIORNI) -> list:
    import requests

    r = requests.get("https://api.x.com/2/users/me", auth=_oauth(), timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"users/me: {r.status_code} — {r.text[:300]}")
    user_id = r.json()["data"]["id"]

    inizio = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%Y-%m-%dT%H:%M:%SZ")
    post, token = [], None
    for _ in range(10):  # tetto di sicurezza alle pagine
        params = {
            "max_results": 100,
            "start_time": inizio,
            "exclude": "replies,retweets",
            "tweet.fields": "created_at,public_metrics,entities",
        }
        if token:
            params["pagination_token"] = token
        r = requests.get(f"https://api.x.com/2/users/{user_id}/tweets",
                         auth=_oauth(), params=params, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"users/{user_id}/tweets: {r.status_code} — {r.text[:300]}")
        corpo = r.json()
        post.extend(corpo.get("data", []))
        token = corpo.get("meta", {}).get("next_token")
        if not token:
            break
    return post


def ha_link_sito(p: dict) -> bool:
    urls = (p.get("entities") or {}).get("urls") or []
    return any(DOMINIO_SITO in (u.get("expanded_url") or "") for u in urls)


def riepilogo(post: list, mappa: dict) -> str:
    righe = []
    senza_dato = 0
    for p in post:
        m = (p.get("public_metrics") or {})
        if "impression_count" not in m:
            senza_dato += 1
        info = abbina(p.get("text", ""), mappa)
        righe.append({
            "testo": normalizza(p.get("text", "")),
            "data": (p.get("created_at") or "")[:10],
            "imp": m.get("impression_count", 0),
            "like": m.get("like_count", 0),
            "rt": m.get("retweet_count", 0),
            "risp": m.get("reply_count", 0),
            "categoria": info["categoria"] if info else "non abbinato (fissato/manuale)",
            "link": ha_link_sito(p),
        })

    tot = sum(r["imp"] for r in righe)
    out = [f"## Report X — ultimi {GIORNI} giorni", ""]
    out.append(f"- Post letti: **{len(righe)}** · visualizzazioni totali: **{tot}** · "
               f"media per post: **{tot / len(righe):.0f}**" if righe else "- Nessun post trovato.")
    if senza_dato:
        out.append(f"- ⚠ {senza_dato} post senza il campo impression_count: il dato potrebbe non essere disponibile sul piano.")
    out.append(f"- Costo massimo di questa lettura: circa ${len(righe) * PREZZO_MAX_PER_POST_USD:.2f}")
    out.append("")

    def tabella(titolo, gruppi):
        out.append(f"### {titolo}")
        out.append("")
        out.append("| Gruppo | Post | Totale | Media | Mediana |")
        out.append("|---|---:|---:|---:|---:|")
        for nome, voci in sorted(gruppi.items(), key=lambda kv: -sum(kv[1])):
            out.append(f"| {nome} | {len(voci)} | {sum(voci)} | {sum(voci)/len(voci):.0f} | {statistics.median(voci):.0f} |")
        out.append("")

    per_cat, per_link = defaultdict(list), defaultdict(list)
    for r in righe:
        per_cat[r["categoria"]].append(r["imp"])
        per_link["con link al sito" if r["link"] else "senza link"].append(r["imp"])
    if righe:
        tabella("Per categoria", per_cat)
        tabella("Con e senza link", per_link)
        out.append("### I 5 post più visti")
        out.append("")
        for r in sorted(righe, key=lambda r: -r["imp"])[:5]:
            out.append(f"- **{r['imp']}** · {r['data']} · {r['categoria']} · {r['testo'][:90]}…")
        out.append("")
        out.append("_Il campione è piccolo: la media pesa molto sui pochi post che esplodono, "
                   "la mediana dice com'è andato il post tipico. I post degli ultimi giorni "
                   "possono ancora crescere._")
    return "\n".join(out)


def main() -> int:
    try:
        post = leggi_post()
    except Exception as e:
        print(f"✗ Lettura da X fallita: {e}")
        return 1
    testo = riepilogo(post, carica_articoli())
    print(testo)
    percorso = os.environ.get("GITHUB_STEP_SUMMARY")
    if percorso:
        with open(percorso, "a", encoding="utf-8") as f:
            f.write(testo + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
