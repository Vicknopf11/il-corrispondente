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
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

RASSEGNA_FILE = "docs/rassegna_sport.json"
COPERTURA_FILE = "docs/copertura_sport.json"
N_ITEM_FINALI = 5  # "pochi, 3-5 al giorno" — questo è il tetto massimo
TIMEOUT_SECONDI = 8
FRESCHEZZA_MAX_GIORNI = 4  # scarta voci RSS più vecchie di così — protegge
                           # da feed "morti"/archiviati che rispondono
                           # correttamente ma con contenuto non aggiornato

# TheSportsDB: "123" è la chiave pubblica gratuita attuale (documentata su
# thesportsdb.com/api.php), con limiti di rate (30 richieste/minuto) e
# alcuni endpoint di ricerca testuale ristretti sul tier free. Per uso più
# stabile, registrati gratuitamente e imposta la chiave come secret
# THESPORTSDB_API_KEY — se il secret non è configurato o è vuoto, si ricade
# automaticamente sulla chiave pubblica.
THESPORTSDB_KEY = os.environ.get("THESPORTSDB_API_KEY") or "123"
THESPORTSDB_BASE = f"https://www.thesportsdb.com/api/v1/json/{THESPORTSDB_KEY}"

# Mappa (sport TheSportsDB, paese, nostra sottocategoria) — usiamo il nome
# sport come lo intende TheSportsDB per cercare le leghe italiane di quel
# sport, poi ne prendiamo gli eventi recenti. Nomi sport DA VERIFICARE: non
# ho modo di controllare dal sandbox quali stringhe esatte l'API riconosce.
THESPORTSDB_SPORT_PAESE = [
    ("Volleyball", "Italy", "Squadra"),
    ("Rugby", "Italy", "Squadra"),
    ("Basketball", "Italy", "Squadra"),
    ("Swimming", "Italy", "Acqua"),
    ("Ice Hockey", "Italy", "Invernali"),
]

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


def _cerca_leghe(nome_sport: str, paese: str) -> list:
    """search_all_leagues.php: elenca le leghe di un paese per uno sport.
    Endpoint di tipo "List", non "Search" — dovrebbe essere meno limitato
    sul tier gratuito rispetto agli endpoint di ricerca testuale (che la
    documentazione TheSportsDB segnala esplicitamente come ristretti, es.
    "Search Teams" limitata al solo esempio 'Arsenal' sulla chiave free)."""
    url = (f"{THESPORTSDB_BASE}/search_all_leagues.php?"
           f"c={urllib.parse.quote(paese)}&s={urllib.parse.quote(nome_sport)}")
    try:
        raw = _fetch_url(url)
        dati = json.loads(raw)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError, ValueError) as e:
        print(f"  ⚠ TheSportsDB (ricerca leghe {nome_sport}/{paese}) non raggiungibile: {e}")
        return []
    # La chiave della risposta per questo endpoint è storicamente "countrys"
    # (refuso noto nell'API stessa) — teniamo un fallback su "leagues" nel
    # caso sia cambiata.
    return dati.get("countrys") or dati.get("leagues") or []


def _eventi_passati_lega(id_lega: str) -> list:
    """eventspastleague.php: eventi recenti di una lega per ID. Endpoint di
    tipo "Schedule", stesso ragionamento sui limiti del tier gratuito."""
    url = f"{THESPORTSDB_BASE}/eventspastleague.php?id={urllib.parse.quote(str(id_lega))}"
    try:
        raw = _fetch_url(url)
        dati = json.loads(raw)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError, ValueError) as e:
        print(f"  ⚠ TheSportsDB (eventi lega {id_lega}) non raggiungibile: {e}")
        return []
    return dati.get("results") or dati.get("events") or []


def estrai_da_thesportsdb(nome_sport: str, paese: str, sottocategoria_fissa: str) -> list:
    """Cerca le leghe di uno sport in un paese, poi gli eventi recenti di
    ciascuna: due chiamate API invece di una ricerca testuale libera, più
    aderenti al modo in cui l'API è pensata per essere usata (vedi
    documentazione ufficiale). Ritorna lista vuota su qualsiasi errore o
    risposta inattesa — non blocca mai la pipeline."""
    leghe = _cerca_leghe(nome_sport, paese)
    if not leghe:
        return []

    voci = []
    for lega in leghe[:3]:  # non esageriamo con le chiamate per singolo sport
        id_lega = lega.get("idLeague")
        nome_lega = lega.get("strLeague") or nome_sport
        if not id_lega:
            continue

        eventi = _eventi_passati_lega(id_lega)
        for ev in eventi[:3]:
            titolo = ev.get("strEvent") or ""
            data_evento = ev.get("dateEvent")

            # Freschezza: stesso principio del filtro RSS — scartiamo
            # eventi troppo vecchi (una lega può non giocare da settimane).
            if data_evento:
                try:
                    d = datetime.strptime(data_evento, "%Y-%m-%d").date()
                    if (date.today() - d).days > FRESCHEZZA_MAX_GIORNI:
                        continue
                except ValueError:
                    pass

            casa = ev.get("strHomeTeam")
            ospite = ev.get("strAwayTeam")
            p_casa = ev.get("intHomeScore")
            p_ospite = ev.get("intAwayScore")
            strutturato = bool(casa and ospite and p_casa is not None and p_ospite is not None)
            if not strutturato and not titolo:
                continue

            voce = {
                "sottocategoria": sottocategoria_fissa,
                "tipo": "risultato" if strutturato else "notizia",
                "titolo": titolo or f"{casa} - {ospite}",
                "link": ev.get("strVideo") or "https://www.thesportsdb.com",
                "fonte": f"TheSportsDB — {nome_lega}",
            }
            if data_evento:
                voce["data_evento"] = data_evento
            if strutturato:
                voce.update({
                    "squadra_casa": casa,
                    "squadra_ospite": ospite,
                    "punteggio_casa": p_casa,
                    "punteggio_ospite": p_ospite,
                    "competizione": nome_lega,
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

    for nome_sport, paese, sottocategoria_fissa in THESPORTSDB_SPORT_PAESE:
        voci = estrai_da_thesportsdb(nome_sport, paese, sottocategoria_fissa)
        print(f"  TheSportsDB '{nome_sport}/{paese}': {len(voci)} voci trovate")
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
