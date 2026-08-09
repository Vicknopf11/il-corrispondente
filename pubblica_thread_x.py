#!/usr/bin/env python3
"""
Il Corrispondente Artificiale — Pubblicazione del thread settimanale su X
A differenza di pubblica_tweet.py (un tweet a esecuzione, distribuito nella
giornata), questo script pubblica TUTTO il thread in un'unica esecuzione:
un thread ha bisogno dell'ID del tweet precedente per incatenarsi, quindi
non può essere spezzato su esecuzioni separate come la coda giornaliera.
"""

import json
import os

from pubblica_tweet import URL_PESO, SEPARATORE

CODA_THREAD_FILE = "coda_thread_x.json"


def comporre_ultimo_tweet(testo: str, url: str) -> str:
    """Come comporla_testo di pubblica_tweet.py, ma qui la usiamo solo
    sull'ultimo tweet del thread, dove va agganciato il permalink."""
    budget_testo = 280 - URL_PESO - len(SEPARATORE)
    if len(testo) > budget_testo:
        testo = testo[: budget_testo - 3] + "..."
    return f"{testo}{SEPARATORE}{url}"


def pubblica_tweet_singolo(testo: str, in_reply_to: str = None) -> str | None:
    import requests
    from requests_oauthlib import OAuth1

    auth = OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_SECRET"],
    )

    payload = {"text": testo}
    if in_reply_to:
        payload["reply"] = {"in_reply_to_tweet_id": in_reply_to}

    r = requests.post(
        "https://api.x.com/2/tweets",
        auth=auth,
        json=payload,
        timeout=10,
    )
    if r.status_code == 201:
        tweet_id = r.json()["data"]["id"]
        print(f"✓ X: pubblicato — {testo[:60]}...")
        return tweet_id
    else:
        print(f"✗ X: errore {r.status_code} — {r.text}")
        return None


def pubblica_thread(coda: dict) -> bool:
    tweet_list = coda["tweet"]
    url = coda.get("articolo_riferimento")

    id_precedente = None
    for i, t in enumerate(tweet_list):
        testo = t["testo"]
        if i == len(tweet_list) - 1 and url:
            testo = comporre_ultimo_tweet(testo, url)

        tweet_id = pubblica_tweet_singolo(testo, in_reply_to=id_precedente)
        if tweet_id is None:
            # Si interrompe: meglio un thread parziale visibile e un errore
            # nel log, che un ciclo infinito di retry automatici.
            print(f"✗ Thread interrotto al tweet {i + 1}/{len(tweet_list)}")
            return False

        t["pubblicato"] = True
        t["tweet_id"] = tweet_id
        id_precedente = tweet_id

    return True


def main() -> None:
    if not os.path.exists(CODA_THREAD_FILE):
        print("Nessun thread in coda — genera_thread_settimanale.py è già girato oggi?")
        return

    with open(CODA_THREAD_FILE, encoding="utf-8") as f:
        coda = json.load(f)

    if coda.get("pubblicato"):
        print("Il thread di oggi è già stato pubblicato.")
        return

    ok = pubblica_thread(coda)
    coda["pubblicato"] = ok
    with open(CODA_THREAD_FILE, "w", encoding="utf-8") as f:
        json.dump(coda, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
