#!/usr/bin/env python3
"""
Il Corrispondente Artificiale — Rassegna sportiva da fonti gratuite
Raccoglie qualche notizia sportiva al giorno da feed RSS pubblici (Gazzetta
dello Sport, ANSA), SENZA passare da Claude/Anthropic: zero trattamento
satirico, solo titolo+link (più data/punteggio quando il feed li fornisce
già strutturati). Contenuto esclusivo del sito (mai pubblicato su X),
pensato per arricchire la sezione Sport oltre all'unico post satirico
quotidiano già generato da genera.py — quella pipeline resta completamente
invariata, stesso costo di oggi.

NOTA: l'integrazione con TheSportsDB è stata valutata e poi rimossa
(30/08/2026) — verificato che la chiave gratuita pubblica dà accesso solo a
Soccer e Motorsport (via all_sports.php), esattamente i due sport esclusi
dal focus di questo script sugli sport minori. Nessun valore aggiunto sul
tier gratuito per questo caso d'uso specifico.

NOTA IMPORTANTE: gli URL dei feed RSS in FONTI_RSS sono stati verificati
live il 30/08/2026 (risposta reale, non solo congettura). Un feed che in
futuro smettesse di rispondere o cambiasse URL viene comunque scartato in
silenzio dalla funzione di fetch, senza bloccare la pipeline.
"""

import json
import os
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

RASSEGNA_FILE = "docs/rassegna_sport.json"
COPERTURA_FILE = "docs/copertura_sport.json"
N_ITEM_FINALI = 5  # "pochi, 3-5 al giorno" — questo è il tetto massimo
TIMEOUT_SECONDI = 8
FRESCHEZZA_MAX_GIORNI = 4  # scarta voci RSS più vecchie di così — protegge
                           # da feed "morti"/archiviati che rispondono
                           # correttamente ma con contenuto non aggiornato

# ── Sottocategorie fisse (stessa tassonomia dell'espansione Sport già
# pianificata in roadmap) — assegnazione SEMPRE per keyword via codice, mai
# a testo libero dal modello: stesso principio già usato per "redattore". ──
SOTTOCATEGORIE_KEYWORD = {
    "Calcio femminile": ["calcio femminile", "serie a femminile", "nazionale femminile",
                          "women's football", "femminile"],
    "Calcio": ["calcio", "serie a", "serie b", "champions league", "coppa italia",
               "scudetto", "europa league"],
    "Atletica": ["atletica", "maratona", "100 metri", "salto in alto", "getto del peso",
                 "mezzofondo", "ciclismo", "giro d'italia", "tour de france", "vuelta",
                 "triathlon"],
    "Acqua": ["nuoto", "tuffi", "pallanuoto", "canottaggio", "canoa", "kayak", "vela",
              "nuoto di fondo", "quattro di coppia", "due senza", "due di coppia",
              "otto remi", "cavalieri delle acque", "surf", "wakeboard", "canottieri"],
    "Squadra": ["volley", "pallavolo", "basket", "pallacanestro", "rugby", "pallamano"],
    "Combattimento": ["pugilato", "boxe", "judo", "lotta", "karate", "taekwondo",
                       "kickboxing", "mma", "scherma", "guantoni", "pesi massimi",
                       "pesi medi", "pesi welter", "pesi gallo", "pesi leggeri",
                       "pesi piuma", "pesi mosca", "campione dei massimi",
                       "gettare la spugna", "ufc"],
    "Motori": ["formula 1", "f1", "motogp", "motociclismo", "rally", "motonautica",
               "superbike"],
    "Racchette e precisione": ["tennis", "atp", "wta", "slam", "padel", "badminton",
                                "squash", "tennistavolo", "golf", "tiro a segno",
                                "tiro con l'arco"],
    "Invernali": ["sci", "pattinaggio", "hockey ghiaccio", "curling", "biathlon",
                  "snowboard", "bob", "slittino"],
    "Mente e nicchia": ["scacchi", "dama", "bridge", "bocce", "biliardo"],
}

# ── Focus iniziale sugli sport minori (deciso 30/08/2026): Calcio (maschile)
# e Motori sono già ampiamente coperti dai media generalisti e dall'unico
# post satirico quotidiano — questa rassegna extra ha senso soprattutto per
# gli sport che altrimenti non troverebbero spazio. Calcio femminile resta
# IN SCOPE nonostante il nome: è esplicitamente trattato come sport
# sotto-rappresentato da valorizzare (vedi editorial rationale nella
# tassonomia), non come "grande sport" da escludere. Facile da rivedere in
# futuro: basta togliere una voce da questo insieme. ──
SOTTOCATEGORIE_ESCLUSE = {"Calcio", "Motori"}

# ── Feed RSS candidati — DA VERIFICARE al primo run reale (vedi nota in
# cima al file). Ogni voce: (nome_fonte, url). Un URL che non risponde
# viene semplicemente saltato, senza rompere nulla.
#
# Deliberatamente NON includo feed dedicati a Calcio/Motori (esclusi per il
# focus sugli sport minori, vedi SOTTOCATEGORIE_ESCLUSE): recuperarli solo
# per scartarne il contenuto sarebbe spreco di banda/rate limit. I feed
# generalisti (Home, Altri Sport) restano perché possono comunque contenere
# sport minori mescolati ad altro — il filtro fa comunque la sua parte. ──
# ── Feed RSS — confermati live il 30/08/2026 dalla directory ufficiale
# Gazzetta (gazzetta.it/rss), pattern dynamic-feed/rss/section/<Sezione>.xml.
# Selezione deliberatamente ristretta agli sport minori: niente Calcio,
# Serie A/B, Coppe, Calciomercato, Motori, F1, Moto — già ampiamente
# coperti altrove.
#
# Ogni voce: (nome_fonte, url, sottocategoria_fissa). Per i feed Gazzetta
# monotematici (es. "Nuoto.xml" contiene SOLO nuoto) assegniamo la
# sottocategoria direttamente dal feed — più affidabile di indovinarla per
# keyword dal titolo. Per i feed generalisti/misti (Sport Vari, ANSA Sport,
# e il transversale Paralimpici, che copre più discipline) la
# sottocategoria_fissa è None: si classifica per keyword come prima.
FONTI_RSS = [
    ("Gazzetta — Sport Vari", "https://www.gazzetta.it/dynamic-feed/rss/section/Sport-Vari.xml", None),
    ("Gazzetta — Nuoto e Pallanuoto", "https://www.gazzetta.it/dynamic-feed/rss/section/Nuoto.xml", "Acqua"),
    ("Gazzetta — Vela e Nautica", "https://www.gazzetta.it/dynamic-feed/rss/section/vela.xml", "Acqua"),
    ("Gazzetta — Rugby", "https://www.gazzetta.it/dynamic-feed/rss/section/Rugby.xml", "Squadra"),
    ("Gazzetta — Volley", "https://www.gazzetta.it/dynamic-feed/rss/section/Volley.xml", "Squadra"),
    ("Gazzetta — Basket", "https://www.gazzetta.it/dynamic-feed/rss/section/Basket.xml", "Squadra"),
    ("Gazzetta — Atletica", "https://www.gazzetta.it/dynamic-feed/rss/section/Atletica.xml", "Atletica"),
    ("Gazzetta — Ciclismo", "https://www.gazzetta.it/dynamic-feed/rss/section/Ciclismo.xml", "Atletica"),
    ("Gazzetta — Tennis", "https://www.gazzetta.it/dynamic-feed/rss/section/Tennis.xml", "Racchette e precisione"),
    ("Gazzetta — Padel", "https://www.gazzetta.it/dynamic-feed/rss/section/padel.xml", "Racchette e precisione"),
    ("Gazzetta — Golf", "https://www.gazzetta.it/dynamic-feed/rss/section/Golf.xml", "Racchette e precisione"),
    ("Gazzetta — Arco", "https://www.gazzetta.it/dynamic-feed/rss/section/arco.xml", "Racchette e precisione"),
    ("Gazzetta — Bocce", "https://www.gazzetta.it/dynamic-feed/rss/section/bocce.xml", "Mente e nicchia"),
    ("Gazzetta — Fighting", "https://www.gazzetta.it/dynamic-feed/rss/section/fighting.xml", "Combattimento"),
    ("Gazzetta — Sport Invernali", "https://www.gazzetta.it/dynamic-feed/rss/section/Sport-Invernali.xml", "Invernali"),
    ("Gazzetta — Paralimpici", "https://www.gazzetta.it/dynamic-feed/rss/section/Paralimpici.xml", None),
    ("ANSA Sport", "https://www.ansa.it/sito/notizie/sport/sport_rss.xml", None),
]

# Nomi fonte per cui, oltre alla sottocategoria, aggiungiamo il flag
# "paralimpico": true — priorità trasversale dichiarata su prompt.html,
# utile per un futuro contatore di copertura dedicato indipendente dalla
# rotazione per sottocategoria.
FONTI_PARALIMPICHE = {"Gazzetta — Paralimpici"}


def _fetch_url(url: str, timeout: int = TIMEOUT_SECONDI) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": "IlCorrispondenteArtificiale/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def classifica_sottocategoria(testo: str):
    """Assegna una sottocategoria fissa in base a keyword nel testo
    (titolo + descrizione). Nessun testo libero: se non trova nulla, o se
    la sottocategoria è tra quelle escluse per questo focus iniziale
    (sport già ben coperti altrove), None — l'elemento viene scartato."""
    t = testo.lower()
    for sottocat, keywords in SOTTOCATEGORIE_KEYWORD.items():
        if sottocat in SOTTOCATEGORIE_ESCLUSE:
            continue
        if any(k in t for k in keywords):
            return sottocat
    return None


def estrai_da_rss(nome_fonte: str, url: str, sottocategoria_fissa=None) -> list:
    """Estrae le voci da un feed RSS 2.0. Ritorna lista vuota se il feed
    non risponde o non è XML valido — non blocca mai la pipeline.

    Se sottocategoria_fissa è fornita (feed Gazzetta monotematici), la usa
    direttamente invece di indovinare dal titolo — più affidabile. Altrimenti
    classifica per keyword come per i feed generalisti/misti."""
    try:
        raw = _fetch_url(url)
        root = ET.fromstring(raw)
    except (urllib.error.URLError, ET.ParseError, TimeoutError, OSError, ValueError) as e:
        print(f"  ⚠ Feed non raggiungibile o non valido ({nome_fonte}): {e}")
        return []

    voci = []
    scartate_per_eta = 0
    scartate_per_classificazione = 0
    for item in root.findall(".//item"):
        titolo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        descrizione = (item.findtext("description") or "").strip()
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        categorie_tag = " ".join(
            (c.text or "").strip() for c in item.findall("category")
        )
        if not titolo or not link:
            continue

        # Controllo di freschezza: se il feed dichiara una data e questa è
        # troppo vecchia, scartiamo — protegge da feed "morti"/archiviati
        # che rispondono con XML valido ma contenuto non aggiornato (visto
        # in produzione: un feed ha restituito notizie di quasi 3 anni fa).
        data_evento = None
        if pub_date_raw:
            try:
                dt = parsedate_to_datetime(pub_date_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                eta_giorni = (datetime.now(timezone.utc) - dt).days
                if eta_giorni > FRESCHEZZA_MAX_GIORNI:
                    scartate_per_eta += 1
                    continue
                data_evento = dt.strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                pass  # data non parsabile: non blocchiamo, teniamo la voce

        if sottocategoria_fissa:
            sottocat = sottocategoria_fissa
        else:
            sottocat = classifica_sottocategoria(f"{titolo} {descrizione} {categorie_tag}")
            if not sottocat:
                scartate_per_classificazione += 1
                continue  # non riconducibile a nessuna sottocategoria nota

        voce = {
            "sottocategoria": sottocat,
            "tipo": "notizia",
            "titolo": titolo,
            "link": link,
            "fonte": nome_fonte,
        }
        if data_evento:
            voce["data_evento"] = data_evento
        if nome_fonte in FONTI_PARALIMPICHE:
            voce["paralimpico"] = True
        voci.append(voce)

    if scartate_per_eta:
        print(f"  ({nome_fonte}: scartate {scartate_per_eta} voci più vecchie "
              f"di {FRESCHEZZA_MAX_GIORNI} giorni — possibile feed non aggiornato)")
    if scartate_per_classificazione and nome_fonte in FONTI_PARALIMPICHE:
        print(f"  ({nome_fonte}: {scartate_per_classificazione} voci non classificate "
              f"in nessuna sottocategoria — priorità trasversale, vale la pena rivedere "
              f"le keyword se il numero è alto)")
    return voci


def carica_copertura() -> dict:
    if os.path.exists(COPERTURA_FILE):
        with open(COPERTURA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def salva_copertura(copertura: dict) -> None:
    with open(COPERTURA_FILE, "w", encoding="utf-8") as f:
        json.dump(copertura, f, ensure_ascii=False, indent=2)


def seleziona_finali(candidati: list, copertura: dict, n: int = N_ITEM_FINALI) -> list:
    """Sceglie fino a n candidati dando priorità alle sottocategorie meno
    coperte di recente (rotazione morbida, mai forzata: se oggi ci sono
    candidati solo per 2 sottocategorie, non se ne inventano altre)."""
    oggi = date.today()

    def giorni_da_ultima_copertura(sottocat: str) -> int:
        ultima = copertura.get(sottocat)
        if not ultima:
            return 9999  # mai coperta finora: priorità massima
        try:
            d = datetime.strptime(ultima, "%Y-%m-%d").date()
            return (oggi - d).days
        except ValueError:
            return 9999

    # Un solo candidato per sottocategoria. Preferenza, in ordine: un
    # "risultato" strutturato batte una semplice "notizia"; a parità di
    # tipo, un candidato paralimpico batte uno non paralimpico — coerente
    # con la priorità trasversale dichiarata su prompt.html.
    per_sottocat = {}
    for c in candidati:
        sc = c["sottocategoria"]
        attuale = per_sottocat.get(sc)
        migliore = (
            attuale is None
            or (c["tipo"] == "risultato" and attuale["tipo"] != "risultato")
            or (
                c["tipo"] == attuale["tipo"]
                and c.get("paralimpico") and not attuale.get("paralimpico")
            )
        )
        if migliore:
            per_sottocat[sc] = c

    ordinati = sorted(
        per_sottocat.items(),
        key=lambda kv: giorni_da_ultima_copertura(kv[0]),
        reverse=True,
    )

    scelti = [c for _, c in ordinati[:n]]
    for c in scelti:
        copertura[c["sottocategoria"]] = oggi.strftime("%Y-%m-%d")
    return scelti


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Raccolta rassegna sportiva...")

    candidati = []
    for nome_fonte, url, sottocategoria_fissa in FONTI_RSS:
        voci = estrai_da_rss(nome_fonte, url, sottocategoria_fissa)
        print(f"  {nome_fonte}: {len(voci)} voci classificate")
        candidati.extend(voci)

    if not candidati:
        print("⚠ Nessun candidato raccolto da nessuna fonte oggi — la rassegna "
              "esistente resta invariata (non sovrascrivo con un file vuoto).")
        return

    # Deduplica per titolo: la stessa notizia può emergere da più fonti RSS
    # (es. sia dal feed generalista "Sport Vari" sia da quello monotematico).
    visti = set()
    candidati_unici = []
    for c in candidati:
        chiave = c["titolo"].strip().lower()
        if chiave in visti:
            continue
        visti.add(chiave)
        candidati_unici.append(c)
    if len(candidati_unici) < len(candidati):
        print(f"  (rimossi {len(candidati) - len(candidati_unici)} duplicati per titolo)")

    copertura = carica_copertura()
    finali = seleziona_finali(candidati_unici, copertura)

    with open(RASSEGNA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generato": datetime.now(timezone.utc).isoformat(),
            "item": finali,
        }, f, ensure_ascii=False, indent=2)
    salva_copertura(copertura)

    print(f"✓ Rassegna sportiva aggiornata — {len(finali)} item selezionati "
          f"({len(candidati)} candidati totali raccolti da tutte le fonti)")


if __name__ == "__main__":
    main()
