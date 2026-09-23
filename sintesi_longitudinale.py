"""
Stadio A — Sintesi longitudinale (autonoma, zero costo Anthropic).

Rilegge docs/posts.json (finestra già limitata a MAX_ARCHIVIO_GIORNI=30 in
genera.py) cercando ricorrenze della stessa categoria di meccanismo IN
RELAZIONE ALLO STESSO TEMA (non solo il meccanismo da solo — vedi nota
sotto). Quando un tema ricorre abbastanza volte, apre una GitHub Issue
proposta — non un articolo, non un'analisi: solo il segnale "qui potrebbe
valere la pena approfondire con dati veri" (Stadio B, mai automatico,
sempre con controllo umano).

PERCHÉ IL RAGGRUPPAMENTO PER TEMA (non solo per meccanismo):
la prima versione di questo script contava solo quante volte un'etichetta
di meccanismo (es. "beneficio taciuto") compariva nell'archivio — ma si è
rivelato un conteggio quasi inutile: alcune etichette sono un vero e
proprio tic stilistico del modello (comparse 20-35 volte su 150 post),
quindi "ricorre spesso" non significa "è emerso un pattern reale del
mondo". Raggruppare per (meccanismo, tag) invece cattura la domanda
giusta: "questo meccanismo si ripete parlando dello STESSO tema?" — es.
"mandante invisibile" + "rai" (la vicenda Ranucci) è un segnale molto più
interessante di "mandante invisibile compare 32 volte in totale".

LIMITE ONESTO: un vero raggruppamento tematico richiederebbe similarità
semantica reale (temi diversi che parlano della stessa storia, es.
"petrolio"/"iran"/"energia" spesso sono lo stesso filone) — questo
richiederebbe l'IA, contro l'obiettivo di costo zero di questo stadio.
Il compromesso: una sola issue per meccanismo (non una per ogni tag),
con dentro elencati tutti i temi che hanno contribuito — così un lettore
umano vede comunque il quadro completo e decide se è un pattern reale.

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
from collections import defaultdict

POSTS_FILE = "docs/posts.json"
SOGLIA_RICORRENZE = 4  # deciso 23/09/2026: via di mezzo tra 3 (troppo permissivo) e 5+ (troppo raro)

REPO = "Vicknopf11/il-corrispondente"
LABEL_ISSUE = "pattern-ricorrente"
SITE_URL = "https://corrispondente.filoclastos.it"

# Tag troppo ampi/da-categoria per essere un tema specifico (si comportano
# più come "categoria" che come argomento — gonfiano il conteggio senza
# indicare un vero filone tematico). Lista curata a mano, non data-driven:
# la frequenza grezza di questi tag nell'archivio non li distingue bene
# dai tag genuinamente specifici (entrambi i gruppi cadono nel 4-10%).
TAG_TROPPO_GENERICI = {
    "italia", "usa", "mondiali", "europei", "cronaca",
    "nazionale", "internazionale", "economia", "sport",
}

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
    """Ritorna {meccanismo: {tag: [{"data":..., "slug":...}, ...]}} solo
    per le combinazioni (meccanismo, tag) che raggiungono/superano
    SOGLIA_RICORRENZE, raggruppate per meccanismo."""
    if not os.path.exists(POSTS_FILE):
        print("posts.json non trovato — niente da analizzare.")
        return {}

    with open(POSTS_FILE, encoding="utf-8") as f:
        archivio = json.load(f)

    combinazioni = defaultdict(list)  # (meccanismo, tag) -> [occorrenze]

    for edizione in archivio.get("edizioni", []):
        for post in edizione.get("post", []):
            testo = testo_completo(post)
            tags = [t for t in (post.get("tag", []) or []) if t not in TAG_TROPPO_GENERICI]
            for m in MECCANISMI:
                if re.search(re.escape(m), testo):
                    for tag in tags:
                        combinazioni[(m, tag)].append({
                            "data": edizione.get("data"),
                            "slug": post.get("slug"),
                        })

    per_meccanismo = defaultdict(dict)
    for (m, tag), occ in combinazioni.items():
        if len(occ) >= SOGLIA_RICORRENZE:
            per_meccanismo[m][tag] = occ

    return dict(per_meccanismo)


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


def apri_issue(meccanismo: str, temi: dict) -> None:
    """temi: {tag: [occorrenze]} — una sezione per ogni tema che ha
    raggiunto la soglia per questo meccanismo."""
    sezioni = []
    for tag, occ in sorted(temi.items(), key=lambda x: -len(x[1])):
        righe = "\n".join(
            f"  - {o['data']} — [{o['slug']}]({SITE_URL}/{o['data'].replace('-', '/')}/{o['slug']}/)"
            for o in occ
        )
        sezioni.append(f"**Tema: {tag}** ({len(occ)} post)\n{righe}")

    corpo = (
        f"**Stadio A — sintesi longitudinale automatica**\n\n"
        f"Il meccanismo **\"{meccanismo}\"** ricorre in relazione a uno o più temi "
        f"specifici negli ultimi 30 giorni:\n\n"
        + "\n\n".join(sezioni) +
        f"\n\n---\n"
        f"Questo è solo un **candidato tema**, non un'analisi. Se un pattern sembra "
        f"reale e sostanziale, il prossimo passo è Stadio B (data journalism da "
        f"dataset aperti), che richiede sempre approvazione umana via PR prima "
        f"di qualsiasi pubblicazione."
    )
    _github_request(f"/repos/{REPO}/issues", method="POST", body={
        "title": f"Pattern ricorrente: {meccanismo}",
        "body": corpo,
        "labels": [LABEL_ISSUE],
    })
    print(f"✓ Issue aperta per '{meccanismo}' ({len(temi)} temi sopra soglia)")


def main() -> None:
    per_meccanismo = trova_ricorrenze()

    if not per_meccanismo:
        print("Nessun meccanismo ha superato la soglia oggi — nessuna issue da aprire.")
        return

    for meccanismo, temi in per_meccanismo.items():
        try:
            if issue_gia_aperta(meccanismo):
                print(f"— '{meccanismo}' già segnalato in una issue aperta, salto.")
                continue
            apri_issue(meccanismo, temi)
        except Exception as e:
            print(f"⚠ Errore su '{meccanismo}' (non bloccante): {e}")


if __name__ == "__main__":
    main()
