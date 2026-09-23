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
OG_IMG_DIR = "docs/assets/og"
COSTI_X_FILE = "docs/costi_x.json"
MAX_COSTI_X_GIORNI = 180

# Prezzi X verificati da Ferruccio il 23/09/2026 via il dashboard X Developer
# (breakdown reale per voce, incollato in chat) — non stimati.
PREZZO_POST_CON_URL_USD = 0.20    # "Content: Create with URL" — post con link
PREZZO_POST_NORMALE_USD = 0.015   # "Post: Create" — post senza link (con o senza media)

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


def _oauth():
    from requests_oauthlib import OAuth1
    return OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_SECRET"],
    )


def percorso_immagine_og(data: str, slug: str) -> str | None:
    """Ricostruisce il percorso dell'immagine OG già generata da
    costruisci_sito.py per questo post (stessa convenzione di nome file:
    docs/assets/og/{data}-{slug}.png, con data in formato YYYY-MM-DD)."""
    if not data or not slug:
        return None
    percorso = os.path.join(OG_IMG_DIR, f"{data}-{slug}.png")
    return percorso if os.path.exists(percorso) else None


def carica_media(percorso_immagine: str) -> str | None:
    """Carica un'immagine come media allegato (endpoint v1.1, ancora
    necessario per ottenere un media_id da riferire in un tweet v2).
    Ritorna None se il caricamento fallisce, senza sollevare eccezioni —
    il chiamante decide come comportarsi (fallback a solo testo)."""
    import requests

    try:
        with open(percorso_immagine, "rb") as f:
            r = requests.post(
                "https://upload.twitter.com/1.1/media/upload.json",
                auth=_oauth(),
                files={"media": f},
                timeout=15,
            )
    except OSError as e:
        print(f"⚠ Impossibile leggere l'immagine {percorso_immagine}: {e}")
        return None

    if r.status_code == 200:
        media_id = r.json().get("media_id_string")
        print(f"✓ X: immagine caricata — media_id {media_id}")
        return media_id
    else:
        print(f"⚠ X: upload immagine fallito ({r.status_code}) — {r.text}")
        return None


def pubblica_su_x(testo: str, url: str = None, media_id: str = None) -> bool:
    import requests

    testo_finale = comporre_testo(testo, url)

    payload = {"text": testo_finale}
    if media_id:
        payload["media"] = {"media_ids": [media_id]}

    r = requests.post(
        "https://api.x.com/2/tweets",
        auth=_oauth(),
        json=payload,
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


def logga_costo_x(coda: dict, prossimo: dict, con_url: bool) -> None:
    """Logga il costo di questa pubblicazione in docs/costi_x.json
    (append-only, storico limitato a MAX_COSTI_X_GIORNI). Prezzi fissi e
    noti (non stimati) — vedi PREZZO_POST_CON_URL_USD/PREZZO_POST_NORMALE_USD.
    Non deve mai bloccare la pipeline: eventuali errori sono solo loggati."""
    try:
        costo = PREZZO_POST_CON_URL_USD if con_url else PREZZO_POST_NORMALE_USD

        voce = {
            "data": coda.get("data"),
            "slug": prossimo.get("slug"),
            "categoria": prossimo.get("categoria"),
            "evidenza": prossimo.get("evidenza", False),
            "tipo_richiesta": "ContentCreateWithUrl" if con_url else "PostCreate",
            "costo_usd": costo,
        }

        if os.path.exists(COSTI_X_FILE):
            with open(COSTI_X_FILE, encoding="utf-8") as f:
                log = json.load(f)
        else:
            log = {"pubblicazioni": []}

        log["pubblicazioni"].insert(0, voce)
        log["pubblicazioni"] = log["pubblicazioni"][:MAX_COSTI_X_GIORNI]

        with open(COSTI_X_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

        print(f"✓ Costo X loggato — {voce['tipo_richiesta']} — ${costo}")
    except Exception as e:
        print(f"⚠ Logging costi X fallito (non bloccante): {e}")


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

    e_evidenza = prossimo.get("evidenza", False)

    if e_evidenza:
        # Notizia di apertura del giorno: link pieno, com'è sempre stato.
        # X mostra automaticamente l'immagine come card di anteprima del link.
        url_da_usare, media_id = prossimo.get("url"), None
    else:
        # Notizie non-evidenza: niente link (costo X molto più alto per i
        # post con URL), ma manteniamo l'immagine caricandola come allegato.
        url_da_usare = None
        percorso_img = percorso_immagine_og(coda.get("data"), prossimo.get("slug"))
        media_id = carica_media(percorso_img) if percorso_img else None
        if not media_id:
            print("⚠ Nessuna immagine disponibile per questo post — pubblico solo testo.")

    try:
        ok = pubblica_su_x(prossimo["testo"], url_da_usare, media_id)
    except CreditoEsauritoError:
        sys.exit(EXIT_CREDITO_ESAURITO)

    if ok:
        prossimo["pubblicato"] = True
        with open(CODA_FILE, "w", encoding="utf-8") as f:
            json.dump(coda, f, ensure_ascii=False, indent=2)
        logga_costo_x(coda, prossimo, con_url=bool(url_da_usare))
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()