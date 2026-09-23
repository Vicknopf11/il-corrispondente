"""
Stadio A — Sintesi longitudinale (autonoma, zero costo Anthropic).

Rilegge docs/posts.json (finestra già limitata a MAX_ARCHIVIO_GIORNI=30 in
genera.py) cercando ricorrenze della stessa categoria di meccanismo in
notizie diverse. Quando una categoria supera la SOGLIA_RICORRENZE nella
finestra, apre una GitHub Issue proposta — non un articolo, non un'analisi:
solo il segnale "qui potrebbe valere la pena approfondire con dati veri"
(Stadio B, mai automatico, sempre con controllo umano).

I meccanismi non sono un campo strutturato nello schema — vengono nominati
esplicitamente in minuscolo dentro il testo libero (post_sito/post_x/
prospettive/implicazioni) quando il modello li applica. Questo script li
rileva con semplice string matching, senza alcuna chiamata API.
"""
import json
import os
import re
import sys
import urllib.request

POSTS_FILE = "docs/posts.json"
SOGLIA_RICORRENZE = 4  # deciso 23/09/2026: via di mezzo tra 3 (troppo permissivo) e 5+ (troppo raro)

SITE_URL = "https://corrispondente.filoclastos.it"

REPO = "Vicknopf11/il-corrispondente"
LABEL_ISSUE = "pattern-ricorrente"

# Stessa formulazione esatta usata nel SYSTEM_PROMPT di genera.py, ma senza
# l'eventuale articolo iniziale ("il"/"la"/"l'") per un matching più robusto
# contro varianti come "un classico falso equilibrio".
MECCANISMI = [
    "villain di comodo",
    "beneficio taciuto",
    "distrazione utile",
    "coro compatto",
    "responsabilità diffusa",
    "doppio standard",
    "indignazione a costo zero",
    "mandante invisibile",
    "falso equilibrio",
    "eufemismo di potere",
    "causa strutturale rimossa",
    "conto dietro la medaglia",
]


def testo_completo(post: dict) -> str:
    """Concatena tutti i campi testuali di un post in cui un meccanismo
    potrebbe essere nominato esplicitamente."""
    pezzi = [
        post.get("post_sito", "") or "",
        post.get("post_x", "") or "",
        post.get("implicazioni", "") or "",
    ]
    for p in post.get("prospettive", []) or []:
        pezzi.append(p.get("testo", "") or "")
    return " ".join(pezzi).lower()


def trova_ricorrenze() -> dict:
    """Ritorna {meccanismo: [{"data":..., "slug":..., "categoria":...}, ...]}
    solo per i meccanismi che raggiungono/superano SOGLIA_RICORRENZE."""
    if not os.path.exists(POSTS_FILE):
        print("posts.json non trovato — niente da analizzare.")
        return {}

    with open(POSTS_FILE, encoding="utf-8") as f:
        archivio = json.load(f)

    occorrenze = {m: [] for m in MECCANISMI}

    for edizione in archivio.get("edizioni", []):
        for post in edizione.get("post", []):
            testo = testo_completo(post)
            for m in MECCANISMI:
                if re.search(re.escape(m), testo):
                    occorrenze[m].append({
                        "data": edizione.get("data"),
                        "slug": post.get("slug"),
                        "categoria": post.get("categoria"),
                    })

    return {m: occ for m, occ in occorrenze.items() if len(occ) >= SOGLIA_RICORRENZE}


def _github_request(path: str, method: str = "GET", body: dict = None) -> dict:
    token = os.environ["GITHUB_TOKEN"]
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def issue_gia_aperta(meccanismo: str) -> bool:
    """Evita duplicati: controlla se esiste già una issue aperta con la
    label LABEL_ISSUE il cui titolo cita questo meccanismo."""
    risultati = _github_request(
        f"/repos/{REPO}/issues?state=open&labels={LABEL_ISSUE}&per_page=100"
    )
    return any(meccanismo in issue.get("title", "").lower() for issue in risultati)


def apri_issue(meccanismo: str, occorrenze: list) -> None:
    righe = "\n".join(
        f"- {o['data']} — [{o['slug']}]({SITE_URL}/{o['data'].replace('-', '/')}/{o['slug']}/) "
        f"({o['categoria']})"
        for o in occorrenze
    )
    corpo = (
        f"**Stadio A — sintesi longitudinale automatica**\n\n"
        f"Il meccanismo **\"{meccanismo}\"** è comparso {len(occorrenze)} volte "
        f"negli ultimi 30 giorni, in contesti diversi:\n\n"
        f"{righe}\n\n"
        f"---\n"
        f"Questo è solo un **candidato tema**, non un'analisi. Se il pattern sembra "
        f"reale e sostanziale, il prossimo passo è Stadio B (data journalism da "
        f"dataset aperti), che richiede sempre approvazione umana via PR prima "
        f"di qualsiasi pubblicazione."
    )
    _github_request(f"/repos/{REPO}/issues", method="POST", body={
        "title": f"Pattern ricorrente: {meccanismo}",
        "body": corpo,
        "labels": [LABEL_ISSUE],
    })
    print(f"✓ Issue aperta per '{meccanismo}' ({len(occorrenze)} occorrenze)")


def main() -> None:
    pattern_trovati = trova_ricorrenze()

    if not pattern_trovati:
        print("Nessun meccanismo ha superato la soglia oggi — nessuna issue da aprire.")
        return

    for meccanismo, occorrenze in pattern_trovati.items():
        try:
            if issue_gia_aperta(meccanismo):
                print(f"— '{meccanismo}' già segnalato in una issue aperta, salto.")
                continue
            apri_issue(meccanismo, occorrenze)
        except Exception as e:
            print(f"⚠ Errore su '{meccanismo}' (non bloccante): {e}")


if __name__ == "__main__":
    main()
