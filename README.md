# Il Corrispondente IA 🗞️

Redazione satirica autonoma che ogni mattina cerca le notizie del giorno,
le commenta con la lente editoriale "chi ci guadagna" attraverso cinque
redattori interni specializzati per sezione, pubblica un'edizione sul
sito e distribuisce i post su X nel corso della giornata — **zero
intervento umano nel ciclo quotidiano**.

Sito live: **https://corrispondente.filoclastos.it**
Account X: **@filo_ferox**

## Filosofia editoriale

Ogni notizia viene letta attraverso un'unica lente fissa — "chi ci
guadagna da questo?" — applicata da 5 redattori interni (mai bylines
pubbliche), ciascuno con un proprio registro e un proprio sottoinsieme
di **categorie di meccanismo analitico** (es. "beneficio taciuto",
"mandante invisibile", "causa strutturale rimossa") che vengono nominate
esplicitamente nel testo quando il modello riconosce lo schema — mai
forzate.

Una sola notizia al giorno (al massimo, spesso nessuna) può ricevere un
trattamento **editoriale multi-prospettiva**: satira come apertura, poi
una sezione di prospettive multiple in registro neutro-giornalistico e
le relative implicazioni, visibile solo sulla pagina permalink con
disclaimer AI fisso.

## Architettura della pipeline

Nove script Python, orchestrati da cinque workflow GitHub Actions, tutti
triggerati esternamente da **cron-job.org** via `repository_dispatch`
(lo scheduler nativo di GitHub Actions è stato abbandonato per
inaffidabilità sugli orari).

1. **`genera.py`** — chiama l'API Anthropic (Claude + web search) per
   trovare e commentare la notizia più significativa del giorno per
   ognuna delle categorie editoriali. Per ogni post genera `slug`,
   `tag`, `categoria`, `evidenza` (un solo articolo "in evidenza" per
   edizione) ed eventualmente `editoriale`/`prospettive`/`implicazioni`.
   Aggiorna `docs/posts.json` (archivio rolling 30 giorni),
   `docs/feed.xml`, crea `coda_x.json` (coda tweet del giorno) e logga
   token/costo in `docs/costi_categoria.json`.

2. **`costruisci_sito.py`** — legge `docs/posts.json` e genera una
   pagina statica per ogni articolo sotto
   `docs/{anno}/{mese}/{giorno}/{slug}/`, con OG tag, canonical URL e
   JSON-LD per SEO. Rigenera `docs/sitemap.xml`, pulisce le pagine
   "orfane" di rigenerazioni multiple nello stesso giorno — ma **non
   tocca mai** i permalink usciti dalla finestra rolling: restano
   stabili per sempre.

3. **`og_immagine.py`** — genera l'immagine OG (Pillow) per ogni
   articolo, usata come `og:image` nei meta tag e come card di anteprima
   quando il link viene condiviso.

4. **`genera_prompt_html.py`** — inietta `SYSTEM_PROMPT` e
   `PROMPT_UTENTE_TEMPLATE`, letti direttamente da `genera.py`, in
   `docs/prompt.html`: la pagina di trasparenza non può disallinearsi
   dal prompt reale in produzione.

5. **`pubblica_tweet.py`** — pubblica un tweet alla volta dalla coda.
   Solo il post **evidenza** include il link al permalink (X tariffa
   $0,20/post con link contro $0,015 senza — differenza scoperta e
   corretta il 23/09/2026); gli altri post restano senza link ma
   mantengono l'immagine, caricata come media allegato. Logga il costo
   esatto di ogni pubblicazione in `docs/costi_x.json`.

6. **`genera_thread_settimanale.py`** / **`pubblica_thread_x.py`** —
   ogni sabato, un thread di 2-3 tweet che approfondisce l'articolo più
   rilevante della settimana (finestra rolling di 7 giorni), pubblicato
   atomicamente con `in_reply_to_tweet_id` per il threading.

7. **`raccogli_sport.py`** — rassegna sportiva satellite da fonti
   gratuite (RSS Gazzetta + ANSA), **zero chiamate Anthropic**: 3-5
   notizie/giorno con rotazione morbida verso sottocategorie meno
   coperte, tracciata in `docs/copertura_sport.json`.

8. **`sintesi_longitudinale.py`** (Stadio A) — rilegge `posts.json`
   cercando ricorrenze della stessa categoria di meccanismo **in
   relazione allo stesso tema** (non il meccanismo da solo — troppo
   spesso un tic stilistico del modello per essere un segnale
   utilizzabile). Quando una combinazione (meccanismo, tag) supera la
   soglia (4+ occorrenze/30gg), apre una GitHub Issue proposta — un
   candidato tema, non un'analisi. **Zero chiamate Anthropic.** È il
   primo stadio dell'architettura a due stadi per il data journalism:
   Stadio B (dataset aperti, mai automatico, sempre con approvazione
   umana via PR) non è ancora implementato.

## Workflow GitHub Actions

Tutti triggerati via `repository_dispatch` da job schedulati su
cron-job.org (non più dallo scheduler nativo GitHub):

- **`genera-post.yml`** — ogni giorno alle 09:17: `genera.py` →
  `costruisci_sito.py`, riepilogo costi nel Summary della run, commit
  automatico.
- **`pubblica-tweet.yml`** — 5 volte al giorno: pubblica il prossimo
  tweet dalla coda.
- **`genera-thread-settimanale.yml`** — sabato ~09:00: thread
  settimanale.
- **`aggiorna-sport.yml`** — 3 volte al giorno: rassegna sportiva, nessun
  secret Anthropic richiesto.
- **`sintesi-longitudinale.yml`** — settimanale: Stadio A, usa il token
  automatico `GITHUB_TOKEN` di Actions (permesso `issues: write`),
  nessun secret aggiuntivo.

Tutti committano da soli col bot `Il Corrispondente Bot` — zero
intervento umano nel ciclo quotidiano, salvo l'occasionale conflitto di
merge quando si lavora in locale a cavallo di un orario di cron (vedi
Note tecniche).

## Struttura del repository

```
il-corrispondente/
├── .github/workflows/
│   ├── genera-post.yml
│   ├── pubblica-tweet.yml
│   ├── genera-thread-settimanale.yml
│   ├── aggiorna-sport.yml
│   └── sintesi-longitudinale.yml
├── genera.py                     # redazione (Claude + web search), 5 redattori/categorie
├── costruisci_sito.py            # genera le pagine permalink + sitemap
├── og_immagine.py                # immagini OG per-articolo (Pillow)
├── genera_prompt_html.py         # sincronizza prompt.html dal SYSTEM_PROMPT reale
├── pubblica_tweet.py             # pubblica un tweet alla volta, logga costi X
├── genera_thread_settimanale.py  # sceglie il tema del thread settimanale
├── pubblica_thread_x.py          # pubblica il thread atomicamente
├── raccogli_sport.py             # rassegna sportiva da fonti gratuite
├── sintesi_longitudinale.py      # Stadio A: pattern ricorrenti → GitHub Issue
├── coda_x.json                   # coda tweet del giorno (rigenerata ogni mattina)
├── coda_thread_x.json            # stato del thread settimanale
└── docs/                         # servito da GitHub Pages sul dominio custom
    ├── index.html                # homepage (SPA client-side, legge posts.json)
    ├── chi-siamo.html            # manifesto editoriale
    ├── prompt.html               # trasparenza: SYSTEM_PROMPT reale (auto-sincronizzato)
    ├── posts.json                # archivio rolling ultimi 30 giorni
    ├── feed.xml / sitemap.xml
    ├── costi_categoria.json      # log costi Anthropic per-generazione (pubblico)
    ├── costi_x.json              # log costi X per-pubblicazione (pubblico, prezzi esatti)
    ├── rassegna_sport.json / copertura_sport.json
    ├── CNAME                     # corrispondente.filoclastos.it
    └── {anno}/{mese}/{giorno}/{slug}/index.html   # permalink di ogni articolo
```

## Trasparenza sui costi

Coerente con la filosofia di trasparenza radicale del progetto
(`prompt.html`), i log dei costi sono **pubblici**:

- **`docs/costi_categoria.json`** — token input/output, uso web search,
  `stop_reason`, costo stimato per generazione (prezzi verificati:
  `claude-sonnet-4-6` $3/$15 per MTok, web search $0,01/ricerca). Il
  breakdown per categoria è una **stima proporzionale**, non un dato
  esatto — un'unica chiamata API produce l'intera edizione.
- **`docs/costi_x.json`** — costo esatto per pubblicazione (prezzi
  fissi e noti: $0,20/post con link, $0,015/post senza link).

Storico: 180 giorni per entrambi.

## Secrets richiesti (GitHub Actions)

- `ANTHROPIC_API_KEY` — per `genera.py`
- `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` —
  OAuth 1.0a per `pubblica_tweet.py`/`pubblica_thread_x.py` (Consumer
  Key/Secret + Access Token/Secret del developer portal X, non le
  credenziali OAuth 2.0)
- `GITHUB_TOKEN` — automatico, fornito da Actions per
  `sintesi_longitudinale.py` (nessuna configurazione richiesta)

Il trigger esterno da cron-job.org richiede invece un **Personal Access
Token GitHub** (scope `repo`) configurato lato cron-job.org, non come
secret del repository.

## Note tecniche

- **Permalink permanenti**: una volta creata, una pagina
  `{anno}/{mese}/{giorno}/{slug}/` non viene più cancellata da
  `costruisci_sito.py`, anche quando la sua edizione esce dalla finestra
  rolling di 30 giorni di `posts.json`.
- **Pagine orfane**: se `genera.py` viene rilanciato più volte per lo
  stesso giorno, `costruisci_sito.py` rimuove le pagine permalink delle
  versioni precedenti per quella data — solo se ancora dentro la
  finestra rolling.
- **`prompt.html`** si rigenera da solo dal `SYSTEM_PROMPT` reale di
  `genera.py` — non va mai aggiornato a mano.
- **Meccanismi non sono un campo strutturato**: le categorie analitiche
  (beneficio taciuto, mandante invisibile, ecc.) vengono nominate in
  minuscolo dentro il testo libero quando applicate, non salvate come
  campo JSON dedicato — `sintesi_longitudinale.py` le rileva via string
  matching sul testo pubblicato.
- **Lavorare in locale**: se si modifica `genera.py` e si testa a
  ridosso dell'orario del trigger (09:17), il workflow schedulato può
  generare un'edizione diversa da quella di test, causando conflitti di
  merge. Sempre controllare il campo `"pubblicato"` in `coda_x.json`
  prima di risolvere conflitti — se `true`, il post va ripristinato in
  `posts.json`, mai scartato.
