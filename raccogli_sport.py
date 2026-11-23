#!/usr/bin/env python3
"""
Il Corrispondente IA — Rassegna sportiva da fonti gratuite
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

import html
import json
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

RASSEGNA_FILE = "docs/rassegna_sport.json"
COPERTURA_FILE = "docs/copertura_sport.json"
N_ITEM_FINALI = 8  # tetto massimo al giorno (era 5 fino al 23/11/2026)
MAX_PER_TESTATA = 3  # al massimo 3 voci dalla stessa testata (Gazzetta, OA Sport, ...):
                     # con 3 testate principali, a 2 non si arriverebbe mai a 8
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
    # Aggiunta il 23/11/2026 insieme al feed "Altri sport" del Corriere dello Sport.
    "Equitazione e ippica": ["equitazione", "ippica", "salto ostacoli", "dressage",
                             "galoppo", "trotto", "concorso ippico", "global champions"],
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
# Valore speciale per la terza colonna di FONTI_RSS: la sottocategoria non è
# fissa ma si ricava dall'indirizzo della notizia (Corriere dello Sport).
DA_URL_CDS = "__da_url_cds__"

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
    # ── Aggiunte il 23/11/2026, feed verificati a mano da Ferruccio lo stesso giorno.
    # Corriere dello Sport, "Altri sport": la disciplina è nell'indirizzo della
    # notizia (/altri-sport/<disciplina>/...), quindi la sottocategoria si prende
    # da lì (vedi sottocategoria_da_url_cds). Escluse /running/ e le notizie senza
    # disciplina: sono soprattutto comunicati promozionali.
    ("Corriere dello Sport — Altri sport", "https://www.corrieredellosport.it/rss/altri-sport", DA_URL_CDS),
    # OA Sport, un feed per disciplina (il feed generale copre solo le ultime 3-4 ore).
    ("OA Sport — Scherma", "https://www.oasport.it/category/scherma/feed/", "Combattimento"),
    ("OA Sport — Judo", "https://www.oasport.it/category/judo/feed/", "Combattimento"),
    ("OA Sport — Pallanuoto", "https://www.oasport.it/category/pallanuoto/feed/", "Acqua"),
    ("OA Sport — Canottaggio", "https://www.oasport.it/category/canottaggio/feed/", "Acqua"),
    ("OA Sport — Tuffi", "https://www.oasport.it/category/tuffi/feed/", "Acqua"),
    ("OA Sport — Pallamano", "https://www.oasport.it/category/pallamano/feed/", "Squadra"),
    ("OA Sport — Atletica", "https://www.oasport.it/category/atletica/feed/", "Atletica"),
    ("OA Sport — Scacchi", "https://www.oasport.it/category/scacchi/feed/", "Mente e nicchia"),
    ("OA Sport — Tiro a volo", "https://www.oasport.it/category/tiro-a-volo/feed/", "Racchette e precisione"),
    ("OA Sport — Sport invernali", "https://www.oasport.it/category/sport-invernali/feed/", "Invernali"),
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


TAG_HTML = re.compile(r"<[^>]+>")


def pulisci_testo(testo: str) -> str:
    """Toglie i pezzi di HTML (<h1>, <p>, <br />...) e decodifica i caratteri
    (&egrave; → è, &#39; → '), poi compatta gli spazi. Alcuni feed (Corriere
    dello Sport) mettono HTML dentro i titoli."""
    t = html.unescape(TAG_HTML.sub(" ", testo or ""))
    t = html.unescape(t)  # seconda passata: entità codificate due volte
    return " ".join(t.split())


# Disciplina nell'indirizzo del Corriere dello Sport → sottocategoria.
# None = da escludere (comunicati). Una disciplina non in elenco si classifica
# per parole chiave sul titolo, come per i feed generalisti.
CDS_DISCIPLINE = {
    "equitazione": "Equitazione e ippica", "ippica": "Equitazione e ippica",
    "rugby": "Squadra", "volley": "Squadra", "basket": "Squadra", "pallamano": "Squadra",
    "pallanuoto": "Acqua", "nuoto": "Acqua", "vela": "Acqua", "canottaggio": "Acqua",
    "atletica": "Atletica", "ciclismo": "Atletica",
    "sci": "Invernali", "sport-invernali": "Invernali",
    "pugilato": "Combattimento", "boxe": "Combattimento", "judo": "Combattimento",
    "scherma": "Combattimento", "taekwondo": "Combattimento",
    "tennis": "Racchette e precisione", "padel": "Racchette e precisione",
    "golf": "Racchette e precisione",
    "running": None,
}


def sottocategoria_da_url_cds(link: str, testo: str):
    """/news/altri-sport/<disciplina>/2026/... → sottocategoria.
    Senza disciplina (/news/altri-sport/2026/...) o in /running/ → None."""
    m = re.search(r"/altri-sport/([a-z-]+)/", link or "")
    if not m:
        return None  # nessuna disciplina nell'indirizzo: quasi sempre un comunicato
    disciplina = m.group(1)
    if disciplina in CDS_DISCIPLINE:
        return CDS_DISCIPLINE[disciplina]
    return classifica_sottocategoria(f"{disciplina.replace('-', ' ')} {testo}")


def testata(nome_fonte: str) -> str:
    """"OA Sport — Scherma" → "OA Sport". Serve al tetto per testata."""
    return nome_fonte.split(" — ")[0].strip()


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
        titolo = pulisci_testo(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        descrizione = pulisci_testo(item.findtext("description"))
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

        if sottocategoria_fissa == DA_URL_CDS:
            sottocat = sottocategoria_da_url_cds(link, f"{titolo} {descrizione}")
            if not sottocat or sottocat in SOTTOCATEGORIE_ESCLUSE:
                scartate_per_classificazione += 1
                continue
        elif sottocategoria_fissa:
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

    # Un solo candidato per sottocategoria (la rotazione resta com'era), ma ora
    # con al massimo MAX_PER_TESTATA voci dalla stessa testata. Per ogni
    # sottocategoria si tengono tutti i candidati in ordine di preferenza:
    # un "risultato" strutturato batte una "notizia"; a parità, un candidato
    # paralimpico batte uno non paralimpico (priorità dichiarata su
    # prompt.html); a parità ancora, il più recente. Se il preferito è di una
    # testata già al tetto, si passa al successivo della stessa sottocategoria.
    def preferenza(c):
        return (c["tipo"] == "risultato", bool(c.get("paralimpico")), c.get("data_evento", ""))

    per_sottocat = {}
    for c in candidati:
        per_sottocat.setdefault(c["sottocategoria"], []).append(c)
    for lista in per_sottocat.values():
        lista.sort(key=preferenza, reverse=True)

    ordinate = sorted(per_sottocat, key=giorni_da_ultima_copertura, reverse=True)

    scelti, per_testata = [], {}
    for sc in ordinate:
        if len(scelti) >= n:
            break
        for c in per_sottocat[sc]:
            t = testata(c["fonte"])
            if per_testata.get(t, 0) < MAX_PER_TESTATA:
                scelti.append(c)
                per_testata[t] = per_testata.get(t, 0) + 1
                break
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

    # Deduplica per titolo e per indirizzo: la stessa notizia può emergere da più fonti RSS
    # (es. sia dal feed generalista "Sport Vari" sia da quello monotematico).
    visti = set()
    candidati_unici = []
    for c in candidati:
        chiavi = (c["titolo"].strip().lower(), c["link"].strip())
        if chiavi[0] in visti or chiavi[1] in visti:
            continue
        visti.update(chiavi)
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
