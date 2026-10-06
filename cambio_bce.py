#!/usr/bin/env python3
"""
Il Corrispondente IA — Cambio EUR/USD dai tassi di riferimento della BCE.

Serve alla pagina /costi, che mostra gli importi in euro: ogni giorno viene
registrato nel log il cambio da usare, così la conversione resta riproducibile.

Regola: per una data D si usa l'ultimo tasso BCE pubblicato PRIMA di D (la BCE
pubblica nel pomeriggio dei giorni lavorativi, quindi alle 09:17 il tasso di
oggi non esiste ancora; nel weekend vale quello dell'ultimo giorno lavorativo).
La stessa regola vale per il recupero dei giorni passati (backfill_cambio.py),
così live e storico sono coerenti.

Non deve mai bloccare la pipeline: se il download o la lettura falliscono,
si restituisce (None, None) e la voce di log resta senza cambio.
"""
import re
import urllib.request

# File ufficiale BCE con i tassi degli ultimi 90 giorni (tutte le valute).
URL_BCE_90G = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"


def analizza_xml(xml: str) -> dict:
    """Ritorna {'YYYY-MM-DD': dollari_per_un_euro} dal formato XML della BCE."""
    tassi = {}
    for blocco in re.finditer(r'<Cube\s+time="(\d{4}-\d{2}-\d{2})"\s*>(.*?)</Cube>', xml, re.DOTALL):
        m = re.search(r'currency="USD"\s+rate="([\d.]+)"', blocco.group(2))
        if m:
            tassi[blocco.group(1)] = float(m.group(1))
    return tassi


def scarica_tassi(timeout: int = 20) -> dict:
    req = urllib.request.Request(URL_BCE_90G, headers={"User-Agent": "il-corrispondente"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return analizza_xml(r.read().decode("utf-8"))


def tasso_per_data(tassi: dict, data_iso: str):
    """Ultimo tasso con data STRETTAMENTE precedente a data_iso.
    Ritorna (tasso, data_del_tasso) oppure (None, None)."""
    precedenti = [d for d in tassi if d < data_iso]
    if not precedenti:
        return None, None
    d = max(precedenti)
    return tassi[d], d


def cambio_per_data(data_iso: str):
    """Scarica i tassi e ritorna (tasso, data_del_tasso) per la data richiesta,
    oppure (None, None) in caso di qualsiasi errore (mai solleva eccezioni)."""
    try:
        return tasso_per_data(scarica_tassi(), data_iso)
    except Exception as e:
        print(f"⚠ Cambio BCE non disponibile (non bloccante): {e}")
        return None, None
