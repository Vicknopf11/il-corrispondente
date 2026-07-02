#!/usr/bin/env python3
"""
Il Corrispondente Artificiale — Pubblicazione distribuita su X
Pubblica UN SOLO tweet in attesa dalla coda del giorno, ad ogni esecuzione.
Pensato per essere lanciato più volte al giorno a orari diversi,
distribuendo nel tempo i post generati in un'unica edizione mattutina.
"""

import json
import os

CODA_FILE = "coda_x.json"


def pubblica_su_x(testo: str) -> bool:
    import requests
    from requests_oauthlib import OAuth1

    auth = OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_SECRET"],
    )
    r = requests.post(
        "https://api.twitter.com/2/tweets",
        auth=auth,
        json={"text": testo},
        timeout=10,
    )
    if r.status_code == 201:
        print(f"✓ X: pubblicato — {testo[:60]}...")
        return True
    else:
        print(f"✗ X: errore {r.status_code} — {r.text}")
        return False


def main() -> None:
    if not os.path.exists(CODA_FILE):
        print("Nessuna coda trovata — probabilmente genera.py non è ancora girato oggi.")
        return

    with open(CODA_FILE, encoding="utf-8") as f:
        coda = json.load(f)

    prossimo = next((t for t in coda.get("tweet", []) if not t.get("pubblicato")), None)

    if prossimo is None:
        print("Coda vuota per oggi — tutti i tweet sono già stati pubblicati.")
        return

    ok = pubblica_su_x(prossimo["testo"])
    if ok:
        prossimo["pubblicato"] = True
        with open(CODA_FILE, "w", encoding="utf-8") as f:
            json.dump(coda, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()