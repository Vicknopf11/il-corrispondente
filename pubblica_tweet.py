#!/usr/bin/env python3
"""
Il Corrispondente Artificiale — Pubblicazione distribuita su X
Pubblica UN SOLO tweet in attesa dalla coda del giorno, ad ogni esecuzione.
Pensato per essere lanciato più volte al giorno a orari diversi,
distribuendo nel tempo i post generati in un'unica edizione mattutina.
"""

import json
import os
import sys

CODA_FILE = "coda_x.json"

# Exit code dedicato per l'errore 402 (credito X esaurito), distinto dal
# generico 1 usato per qualsiasi altro tipo di fallimento di pubblicazione.
EXIT_CREDITO_ESAURITO = 2


class CreditoEsauritoError(Exception):
    """Sollevata quando X risponde 402 — credito API esaurito."""

# X accorcia sempre i link a 23 caratteri (wrapper t.co) indipendentemente
# dalla lunghezza reale, ai fini del conteggio dei 280 caratteri totali.
URL_PESO = 23
SEPARATORE = "\n\n"


def comporre_testo(testo: str, url: str = None) -> str:
    """Compone il testo finale del tweet, riservando spazio per il link
    (se presente) secondo il conteggio caratteri reale di X."""
    if not url:
        return testo if len(testo) <= 280 else testo[:277] + "..."

    budget_testo = 280 - URL_PESO - len(SEPARATORE)
    if len(testo) > budget_testo:
        testo = testo[:budget_testo - 3] + "..."
    return f"{testo}{SEPARATORE}{url}"


def pubblica_su_x(testo: str, url: str = None) -> bool:
    import requests
    from requests_oauthlib import OAuth1

    testo_finale = comporre_testo(testo, url)

    auth = OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_SECRET"],
    )
    r = requests.post(
        "https://api.x.com/2/tweets",
        auth=auth,
        json={"text": testo_finale},
        timeout=10,
    )
    if r.status_code == 201:
        print(f"✓ X: pubblicato — {testo_finale[:60]}...")
        return True
    elif r.status_code == 402:
        print(f"✗ X: errore 402 — credito esaurito — {r.text}")
        raise CreditoEsauritoError(r.text)
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

    try:
        ok = pubblica_su_x(prossimo["testo"], prossimo.get("url"))
    except CreditoEsauritoError:
        sys.exit(EXIT_CREDITO_ESAURITO)

    if ok:
        prossimo["pubblicato"] = True
        with open(CODA_FILE, "w", encoding="utf-8") as f:
            json.dump(coda, f, ensure_ascii=False, indent=2)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()