#!/usr/bin/env python3
"""
Il Corrispondente IA — Report privato mensile (ultimi 30 giorni conclusi).

Manda un solo messaggio PRIVATO su Telegram (chat TELEGRAM_OWNER_CHAT_ID, la
stessa dell'avviso di errore della generazione) con quattro blocchi:
  1. Produzione  — da docs/posts.json (edizioni, articoli, controlli, apertura)
  2. Costi       — da docs/costi_categoria.json e docs/costi_x.json
  3. X           — visualizzazioni lette dall'API (funzioni di report_x_settimanale.py)
  4. Telegram    — iscritti al canale pubblico

Non scrive nulla nel repo e non pubblica niente in pubblico. Se un blocco
fallisce, il messaggio parte lo stesso con una riga di avviso al suo posto.
Lo stesso testo va anche nel Summary della run.

Periodo: i 30 giorni conclusi prima di oggi (ora italiana), cioè esattamente
quelli che posts.json conserva. Nei mesi di 31 giorni salta il giorno 1.

Costo: solo la lettura da X, circa 270 post → al massimo ~$1,35 a lancio.

Variabili d'ambiente:
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET   (blocco X)
  TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_CHAT_ID                 (invio)
  TELEGRAM_CHAT_ID                                           (iscritti al canale)
  INVIA = "no" per provare senza mandare il messaggio (solo Summary e log)
"""
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("Europe/Rome")
GIORNI = 30
POSTS_FILE = "docs/posts.json"
COSTI_FILE = "docs/costi_categoria.json"
COSTI_X_FILE = "docs/costi_x.json"
PREZZO_MAX_PER_POST_USD = 0.005
LIMITE_TELEGRAM = 4000  # il massimo è 4096 caratteri: un po' di margine


# ── Periodo ──────────────────────────────────────────────────────────────────

def periodo(oggi: date = None):
    """(primo, ultimo) giorno incluso: i 30 giorni conclusi prima di oggi."""
    oggi = oggi or datetime.now(FUSO).date()
    ultimo = oggi - timedelta(days=1)
    primo = oggi - timedelta(days=GIORNI)
    return primo, ultimo


def nel_periodo(data_iso: str, primo: date, ultimo: date) -> bool:
    try:
        d = date.fromisoformat((data_iso or "")[:10])
    except ValueError:
        return False
    return primo <= d <= ultimo


def fmt_data(d: date) -> str:
    return d.strftime("%d/%m")


def euro(usd: float, cambio: float) -> str:
    return f"€{usd / cambio:.2f}".replace(".", ",") if cambio else "€?"


def dollari(usd: float) -> str:
    return f"${usd:.2f}".replace(".", ",")


def carica(percorso: str) -> dict:
    with open(percorso, encoding="utf-8") as f:
        return json.load(f)


# ── 1. Produzione ────────────────────────────────────────────────────────────

def blocco_produzione(primo: date, ultimo: date) -> list:
    edizioni = [e for e in carica(POSTS_FILE).get("edizioni", [])
                if nel_periodo(e.get("data"), primo, ultimo)]
    date_presenti = {e["data"][:10] for e in edizioni}
    mancanti = [primo + timedelta(days=i) for i in range(GIORNI)
                if (primo + timedelta(days=i)).isoformat() not in date_presenti]

    articoli = sum(len(e.get("post", [])) for e in edizioni)
    out = ["PRODUZIONE",
           f"Edizioni: {len(edizioni)}/{GIORNI} · articoli: {articoli}"]
    if mancanti:
        out.append("Giorni senza edizione: " + ", ".join(fmt_data(d) for d in mancanti))

    con_controlli = [e["controlli"] for e in edizioni if isinstance(e.get("controlli"), dict)]
    if con_controlli:
        somma = lambda k: sum(c.get(k) or 0 for c in con_controlli)
        corretti = sum(len(c.get("giorni_corretti") or []) for c in con_controlli)
        out.append(f"Controlli (dati per {len(con_controlli)} {'giorno' if len(con_controlli) == 1 else 'giorni'} su {len(edizioni)}): "
                   f"fatti proposti {somma('fatti_proposti')}, scartati {somma('fatti_scartati')}; "
                   f"giorni della settimana corretti {corretti}; "
                   f"virgolette riparate {somma('virgolette_riparate')}")
    else:
        out.append("Controlli: nessun dato nel periodo")

    aperture = Counter(p.get("categoria", "?") for e in edizioni
                       for p in e.get("post", []) if p.get("evidenza"))
    if aperture:
        out.append("Apertura per sezione: " + ", ".join(
            f"{cat} {n}" for cat, n in aperture.most_common()))
    return out


# ── 2. Costi ─────────────────────────────────────────────────────────────────

def blocco_costi(primo: date, ultimo: date) -> list:
    gen = [g for g in carica(COSTI_FILE).get("generazioni", [])
           if nel_periodo(g.get("data"), primo, ultimo)]
    usd_gen = sum(g.get("costo_stimato_usd") or 0 for g in gen)
    cambi = [g["cambio_usd_per_eur"] for g in gen if g.get("cambio_usd_per_eur")]
    cambio = statistics.mean(cambi) if cambi else None
    non_finite = sum(1 for g in gen if g.get("stop_reason") not in (None, "end_turn"))
    out = ["COSTI",
           f"Generazione (Anthropic): {dollari(usd_gen)} ≈ {euro(usd_gen, cambio)} "
           f"in {len(gen)} lanci registrati"]
    if gen:
        token_medi = f"{statistics.mean(g.get('output_tokens') or 0 for g in gen):,.0f}".replace(",", ".")
        out.append(f"Media per lancio: {dollari(usd_gen / len(gen))} · token di output medi: {token_medi}")
    if non_finite:
        out.append(f"⚠ Lanci non conclusi normalmente (stop_reason diverso da end_turn): {non_finite}")

    tutte_x = carica(COSTI_X_FILE).get("pubblicazioni", [])
    pub = [p for p in tutte_x if nel_periodo(p.get("data"), primo, ultimo)]
    usd_x = sum(p.get("costo_usd") or 0 for p in pub)
    riga_x = (f"Pubblicazione su X: {dollari(usd_x)} ≈ {euro(usd_x, cambio)} "
              f"per {len(pub)} post")
    piu_vecchia = min((p.get("data", "")[:10] for p in tutte_x), default=None)
    if piu_vecchia and piu_vecchia > primo.isoformat():
        riga_x += (f" — PARZIALE: il registro parte dal "
                   f"{fmt_data(date.fromisoformat(piu_vecchia))}")
    out.append(riga_x)
    out.append(f"Totale: {dollari(usd_gen + usd_x)} ≈ {euro(usd_gen + usd_x, cambio)}")
    return out


# ── 3. X ─────────────────────────────────────────────────────────────────────

def data_locale(created_at: str):
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(FUSO).date()
    except (ValueError, AttributeError):
        return None


def blocco_x(primo: date, ultimo: date) -> list:
    import report_x_settimanale as rx

    # Un giorno in più per coprire il fuso; poi si filtra sulla data italiana.
    grezzi = rx.leggi_post(giorni=GIORNI + 2)
    mappa = rx.carica_articoli()
    righe = []
    for p in grezzi:
        d = data_locale(p.get("created_at", ""))
        if d is None or not (primo <= d <= ultimo):
            continue
        info = rx.abbina(p.get("text", ""), mappa)
        righe.append({
            "imp": (p.get("public_metrics") or {}).get("impression_count", 0),
            "cat": info["categoria"] if info else "non abbinato",
            "link": rx.ha_link_sito(p),
            "testo": rx.normalizza(p.get("text", "")),
            "data": d,
        })

    out = ["X"]
    if not righe:
        return out + ["Nessun post nel periodo."]
    tot = sum(r["imp"] for r in righe)
    out.append(f"Post: {len(righe)} · visualizzazioni: {tot} · "
               f"mediana per post: {statistics.median(r['imp'] for r in righe):.0f}")

    per_cat = defaultdict(list)
    per_link = defaultdict(list)
    for r in righe:
        per_cat[r["cat"]].append(r["imp"])
        per_link["con link" if r["link"] else "senza link"].append(r["imp"])
    out.append("Mediana per sezione: " + ", ".join(
        f"{c} {statistics.median(v):.0f}"
        for c, v in sorted(per_cat.items(), key=lambda kv: -statistics.median(kv[1]))))
    out.append("Mediana " + ", ".join(
        f"{k} {statistics.median(v):.0f} ({len(v)} post)" for k, v in sorted(per_link.items())))
    out.append("I 3 più visti:")
    for r in sorted(righe, key=lambda r: -r["imp"])[:3]:
        out.append(f"  {r['imp']} · {fmt_data(r['data'])} · {r['cat']} · {r['testo'][:70]}…")
    out.append(f"Costo di questa lettura: al massimo {dollari(len(grezzi) * PREZZO_MAX_PER_POST_USD)}")
    return out


# ── 4. Telegram ──────────────────────────────────────────────────────────────

def blocco_telegram() -> list:
    import requests

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    canale = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not canale:
        return ["TELEGRAM", "Non configurato: salto."]
    r = requests.get(f"https://api.telegram.org/bot{token}/getChatMemberCount",
                     params={"chat_id": canale}, timeout=10)
    corpo = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or not corpo.get("ok"):
        raise RuntimeError(f"getChatMemberCount: {r.status_code} — {r.text[:200]}")
    # Il conteggio include gli amministratori (te e il bot).
    return ["TELEGRAM", f"Iscritti al canale oggi: {corpo['result']} (amministratori inclusi)"]


# ── Messaggio ────────────────────────────────────────────────────────────────

def prova(nome: str, funzione, *argomenti) -> list:
    """Esegue un blocco; se fallisce, al suo posto una riga di avviso."""
    try:
        return funzione(*argomenti)
    except Exception as e:
        return [nome, f"⚠ Blocco non disponibile: {type(e).__name__}: {str(e)[:200]}"]


def componi(oggi: date = None) -> str:
    primo, ultimo = periodo(oggi)
    blocchi = [
        [f"📊 Il Corrispondente IA — report privato",
         f"Periodo: {fmt_data(primo)}–{fmt_data(ultimo)} ({GIORNI} giorni conclusi)"],
        prova("PRODUZIONE", blocco_produzione, primo, ultimo),
        prova("COSTI", blocco_costi, primo, ultimo),
        prova("X", blocco_x, primo, ultimo),
        prova("TELEGRAM", blocco_telegram),
        ["Le visualizzazioni degli ultimi giorni possono ancora crescere. "
         "Il confronto con il mese prima è nel messaggio precedente."],
    ]
    return "\n\n".join("\n".join(b) for b in blocchi)


def spezza(testo: str, limite: int = LIMITE_TELEGRAM) -> list:
    """Divide il testo tra i blocchi, se supera il limite di Telegram."""
    parti, corrente = [], ""
    for blocco in testo.split("\n\n"):
        candidato = f"{corrente}\n\n{blocco}" if corrente else blocco
        if len(candidato) <= limite:
            corrente = candidato
            continue
        if corrente:
            parti.append(corrente)
        while len(blocco) > limite:
            parti.append(blocco[:limite])
            blocco = blocco[limite:]
        corrente = blocco
    if corrente:
        parti.append(corrente)
    return parti


def invia(testo: str) -> bool:
    import requests

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_OWNER_CHAT_ID")
    if not token or not chat:
        print("✗ TELEGRAM_BOT_TOKEN o TELEGRAM_OWNER_CHAT_ID mancanti: messaggio non inviato.")
        return False
    for parte in spezza(testo):
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": parte,
                                "disable_web_page_preview": True},
                          timeout=10)
        if r.status_code != 200 or not r.json().get("ok"):
            print(f"✗ Invio su Telegram fallito: {r.status_code} — {r.text[:200]}")
            return False
    print("✓ Report inviato in privato su Telegram.")
    return True


def main() -> int:
    testo = componi()
    print(testo)
    percorso = os.environ.get("GITHUB_STEP_SUMMARY")
    if percorso:
        with open(percorso, "a", encoding="utf-8") as f:
            f.write("```\n" + testo + "\n```\n")
    if os.environ.get("INVIA", "si").strip().lower() == "no":
        print("INVIA=no: messaggio non inviato (prova).")
        return 0
    return 0 if invia(testo) else 1


if __name__ == "__main__":
    sys.exit(main())
