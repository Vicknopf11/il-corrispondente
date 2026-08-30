#!/usr/bin/env python3
"""
Il Corrispondente Artificiale — Rassegna sportiva da fonti gratuite
Raccoglie qualche notizia/risultato sportivo al giorno da feed RSS pubblici
e dall'API gratuita TheSportsDB, SENZA passare da Claude/Anthropic: zero
trattamento satirico, solo dati strutturati (quando disponibili da
TheSportsDB) o titolo+link (quando arrivano da RSS). Contenuto esclusivo
del sito (mai pubblicato su X), pensato per arricchire la sezione Sport
oltre all'unico post satirico quotidiano già generato da genera.py — quella
pipeline resta completamente invariata, stesso costo di oggi.

NOTA IMPORTANTE: gli URL dei feed RSS in FONTI_RSS e gli endpoint
TheSportsDB sono candidati plausibili da conoscenza generale, NON
verificati con una richiesta di rete reale (l'ambiente in cui è stato
scritto questo script non ha accesso alla rete pubblica generica). Vanno
controllati al primo run reale su GitHub Actions: la funzione di fetch
scarta silenziosamente una fonte che non risponde o non è valida, quindi
un URL sbagliato non blocca mai la pipeline — semplicemente quella fonte
non porta contenuto quel giorno. Controlla i log del primo run per capire
quali fonti funzionano davvero.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

RASSEGNA_FILE = "docs/rassegna_sport.json"
COPERTURA_FILE = "docs/copertura_sport.json"
N_ITEM_FINALI = 5  # "pochi, 3-5 al giorno" — questo è il tetto massimo
TIMEOUT_SECONDI = 8

# TheSportsDB: "3" è la chiave pubblica di test messa a disposizione da
# TheSportsDB stessa per esperimenti gratuiti (rate limit più stretto e
# copertura ridotta). Per uso più stabile, registrati gratuitamente su
# thesportsdb.com/api.php e imposta la chiave come secret
# THESPORTSDB_API_KEY nel repo — se il secret non è configurato o è vuoto,
# si ricade automaticamente sulla chiave di test.
THESPORTSDB_KEY = os.environ.get("THESPORTSDB_API_KEY") or "3"
THESPORTSDB_BASE = f"https://www.thesportsdb.com/api/v1/json/{THESPORTSDB_KEY}"

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
              "nuoto di fondo"],
    "Squadra": ["volley", "pallavolo", "basket", "pallacanestro", "rugby", "pallamano"],
    "Combattimento": ["pugilato", "boxe", "judo", "lotta", "karate", "taekwondo",
                       "kickboxing", "mma", "scherma"],
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
FONTI_RSS = [
    ("Gazzetta dello Sport — Home", "https://www.gazzetta.it/rss/home.xml"),
    ("Gazzetta dello Sport — Tennis", "https://www.gazzetta.it/rss/Tennis.xml"),
    ("Gazzetta dello Sport — Altri Sport", "https://www.gazzetta.it/rss/Altrisport.xml"),
    ("ANSA Sport", "https://www.ansa.it/sito/notizie/sport/sport_rss.xml"),
    # CONI: portale aggregatore notizie federazioni — URL da verificare,
    # la struttura esatta del feed CONI non è confermata.
    ("CONI — Notizie", "https://www.coni.it/it/rss.html"),
    # CIP (Comitato Italiano Paralimpico): priorità trasversale dichiarata
    # pubblicamente su prompt.html — URL da verificare, non ancora testato.
    ("CIP — Paralimpico", "https://www.comitatoparalimpico.it/rss"),
]

# TheSportsDB: query testuali (ricerca per nome di competizione) invece di
# ID numerici di lega memorizzati, per non dipendere da ID non verificati.
# Niente "Serie A" o "Formula 1" qui: sono le categorie escluse per il
# focus sugli sport minori. La copertura gratuita di TheSportsDB su sport
# di nicchia italiani è probabilmente scarsa — da verificare quali di
# queste query restituiscono davvero qualcosa di utile.
THESPORTSDB_QUERY = [
    "Serie A Femminile",
    "Volleyball Italy",
    "Rugby Italy",
]


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


def estrai_da_rss(nome_fonte: str, url: str) -> list:
    """Estrae le voci da un feed RSS 2.0. Ritorna lista vuota se il feed
    non risponde o non è XML valido — non blocca mai la pipeline."""
    try:
        raw = _fetch_url(url)
        root = ET.fromstring(raw)
    except (urllib.error.URLError, ET.ParseError, TimeoutError, OSError, ValueError) as e:
        print(f"  ⚠ Feed non raggiungibile o non valido ({nome_fonte}): {e}")
        return []

    voci = []
    for item in root.findall(".//item"):
        titolo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        descrizione = (item.findtext("description") or "").strip()
        if not titolo or not link:
            continue
        sottocat = classifica_sottocategoria(f"{titolo} {descrizione}")
        if not sottocat:
            continue  # non riconducibile a nessuna sottocategoria nota
        voci.append({
            "sottocategoria": sottocat,
            "tipo": "notizia",
            "titolo": titolo,
            "link": link,
            "fonte": nome_fonte,
        })
    return voci


def estrai_da_thesportsdb(query: str) -> list:
    """Cerca eventi recenti su TheSportsDB per nome di competizione.
    Ritorna lista vuota su qualsiasi errore di rete o risposta inattesa —
    l'API gratuita ha limiti di rate ed endpoint che possono cambiare."""
    url = f"{THESPORTSDB_BASE}/searchevents.php?e={urllib.parse.quote(query)}"
    try:
        raw = _fetch_url(url)
        dati = json.loads(raw)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError, ValueError) as e:
        print(f"  ⚠ TheSportsDB non raggiungibile per '{query}': {e}")
        return []

    eventi = dati.get("event") or []
    voci = []
    for ev in eventi[:5]:
        titolo = ev.get("strEvent") or ""
        # Preferiamo classificare dal solo titolo: usare anche la query di
        # ricerca come contesto rischia di "contaminare" la sottocategoria
        # se lo stesso evento emerge da più query diverse (es. un evento
        # ambiguo trovato sia cercando "Serie A" che "Formula 1").
        sottocat = classifica_sottocategoria(titolo) or classifica_sottocategoria(f"{titolo} {query}")
        if not sottocat:
            continue
        casa = ev.get("strHomeTeam")
        ospite = ev.get("strAwayTeam")
        p_casa = ev.get("intHomeScore")
        p_ospite = ev.get("intAwayScore")
        strutturato = bool(casa and ospite and p_casa is not None and p_ospite is not None)
        voce = {
            "sottocategoria": sottocat,
            "tipo": "risultato" if strutturato else "notizia",
            "titolo": titolo,
            "link": ev.get("strVideo") or "https://www.thesportsdb.com",
            "fonte": "TheSportsDB",
            "data_evento": ev.get("dateEvent"),
        }
        if strutturato:
            voce.update({
                "squadra_casa": casa,
                "squadra_ospite": ospite,
                "punteggio_casa": p_casa,
                "punteggio_ospite": p_ospite,
                "competizione": ev.get("strLeague"),
            })
        voci.append(voce)
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

    # Un solo candidato per sottocategoria (preferendo il "risultato"
    # strutturato a una semplice "notizia", se entrambi disponibili).
    per_sottocat = {}
    for c in candidati:
        sc = c["sottocategoria"]
        attuale = per_sottocat.get(sc)
        if attuale is None or (c["tipo"] == "risultato" and attuale["tipo"] != "risultato"):
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
    for nome_fonte, url in FONTI_RSS:
        voci = estrai_da_rss(nome_fonte, url)
        print(f"  {nome_fonte}: {len(voci)} voci classificate")
        candidati.extend(voci)

    for query in THESPORTSDB_QUERY:
        voci = estrai_da_thesportsdb(query)
        print(f"  TheSportsDB '{query}': {len(voci)} voci classificate")
        candidati.extend(voci)

    if not candidati:
        print("⚠ Nessun candidato raccolto da nessuna fonte oggi — la rassegna "
              "esistente resta invariata (non sovrascrivo con un file vuoto).")
        return

    # Deduplica per titolo: la stessa notizia/evento può emergere da più
    # fonti RSS o da più query TheSportsDB diverse.
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
