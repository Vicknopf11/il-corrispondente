#!/usr/bin/env python3
"""
Il Corrispondente IA — Recupero una tantum di cambio e dettaglio dei costi.

Le voci di docs/costi_categoria.json registrate prima dell'introduzione del
cambio BCE non hanno i campi "cambio_usd_per_eur", "cambio_data" e
"costo_dettaglio_usd". Questo script li aggiunge dove mancano, senza toccare
nient'altro. Va lanciato in locale, una volta, dalla radice del repo:

    python3 backfill_cambio.py

Poi si controlla il diff e si fa commit di docs/costi_categoria.json.
I tassi BCE disponibili coprono gli ultimi 90 giorni: le voci più vecchie
restano senza cambio.
"""
import json
import sys

from cambio_bce import scarica_tassi, tasso_per_data

COSTI_FILE = "docs/costi_categoria.json"

# Stessi prezzi di genera.py (claude-sonnet-4-6 e ricerca web).
PREZZO_INPUT_PER_MILIONE_USD = 3.0
PREZZO_OUTPUT_PER_MILIONE_USD = 15.0
PREZZO_WEB_SEARCH_PER_RICERCA_USD = 0.01


def main() -> int:
    with open(COSTI_FILE, encoding="utf-8") as f:
        log = json.load(f)

    tassi = scarica_tassi()
    print(f"Tassi BCE scaricati: {len(tassi)} giorni "
          f"({min(tassi)} → {max(tassi)})")

    aggiornate = senza_tasso = 0
    for voce in log["generazioni"]:
        modificata = False

        if voce.get("cambio_usd_per_eur") is None:
            tasso, data_tasso = tasso_per_data(tassi, voce["data"])
            if tasso is None:
                senza_tasso += 1
                print(f"  {voce['data']}: nessun tasso disponibile, lasciata com'è")
            else:
                voce["cambio_usd_per_eur"] = tasso
                voce["cambio_data"] = data_tasso
                modificata = True

        if "costo_dettaglio_usd" not in voce:
            voce["costo_dettaglio_usd"] = {
                "lettura": round(voce["input_tokens"] / 1_000_000 * PREZZO_INPUT_PER_MILIONE_USD, 4),
                "scrittura": round(voce["output_tokens"] / 1_000_000 * PREZZO_OUTPUT_PER_MILIONE_USD, 4),
                "ricerche": round(voce["web_search_richieste"] * PREZZO_WEB_SEARCH_PER_RICERCA_USD, 4),
            }
            modificata = True

        if modificata:
            aggiornate += 1
            print(f"  {voce['data']}: cambio {voce.get('cambio_usd_per_eur')} "
                  f"(tasso del {voce.get('cambio_data')})")

    with open(COSTI_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"\nVoci aggiornate: {aggiornate} — senza tasso: {senza_tasso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
