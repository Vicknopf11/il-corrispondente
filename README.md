# Il Corrispondente Artificiale 🗞️

Agente satirico autonomo che ogni mattina cerca le notizie del giorno,
le commenta con la filosofia editoriale del "bastian contrario" e "chi ci
guadagna", pubblica un'edizione sul sito e distribuisce i post su X nel
corso della giornata.

Sito live: **https://corrispondente.filoclastos.it**
Account X: **@filo_ferox**

## Architettura della pipeline

Tre script Python, eseguiti in sequenza dai due workflow GitHub Actions:

1. **`genera.py`** — chiama l'API Anthropic (Claude + web search) per
   trovare e commentare la notizia più significativa del giorno per ogni
   categoria. Per ogni post genera anche `slug`, `tag` ed `evidenza`
   (esattamente un articolo "in evidenza" per edizione). Aggiorna
   `docs/posts.json` (archivio rolling degli ultimi 30 giorni),
   `docs/feed.xml` (RSS con permalink) e crea `coda_x.json` (coda dei
   tweet del giorno, ancora da pubblicare).

2. **`costruisci_sito.py`** — legge `docs/posts.json` e genera una pagina
   statica per ogni articolo sotto `docs/{anno}/{mese}/{giorno}/{slug}/`,
   con OG tag, canonical URL e JSON-LD per SEO. Rigenera anche
   `docs/sitemap.xml`. Pulisce automaticamente eventuali pagine "orfane"
   (es. se il generatore viene rilanciato più volte nello stesso giorno) —
   ma **non tocca mai** le pagine di date uscite dalla finestra rolling di
   `posts.json`: quei permalink restano stabili per sempre.

3. **`pubblica_tweet.py`** — pubblica UN tweet alla volta dalla coda
   (`coda_x.json`), con testo satirico + link al permalink dell'articolo.
   Pensato per girare più volte al giorno, distribuendo nel tempo i post
   di un'unica edizione mattutina.

## Workflow GitHub Actions

- **`genera-post.yml`** — ogni giorno alle 09:17 ora italiana (o a mano da
  Actions → *Run workflow*): esegue `genera.py` → `costruisci_sito.py` →
  commit automatico di tutto (`posts.json`, `feed.xml`, `sitemap.xml`,
  `coda_x.json`, nuove cartelle permalink).

- **`pubblica-tweet.yml`** — 5 volte al giorno a orari distribuiti (09:20,
  11:37, 14:07, 17:07, 20:07 ora italiana): pubblica il prossimo tweet non
  ancora pubblicato dalla coda del giorno.

Entrambi committano da soli col bot `Il Corrispondente Bot` — zero
intervento umano nel ciclo quotidiano.

## Struttura del repository

```
il-corrispondente/
├── .github/workflows/
│   ├── genera-post.yml       # cron giornaliero: genera + costruisce il sito
│   └── pubblica-tweet.yml    # cron 5x/giorno: pubblica dalla coda
├── genera.py                 # agente satirico (Claude + web search)
├── costruisci_sito.py        # genera le pagine permalink + sitemap
├── pubblica_tweet.py         # pubblica un tweet alla volta su X
├── coda_x.json               # coda dei tweet del giorno (rigenerata ogni mattina)
└── docs/                     # servito da GitHub Pages sul dominio custom
    ├── index.html            # homepage (SPA client-side, legge posts.json)
    ├── chi-siamo.html        # manifesto editoriale
    ├── prompt.html           # trasparenza: il system prompt reale (statico, va tenuto sincronizzato a mano)
    ├── posts.json            # archivio rolling ultimi 30 giorni
    ├── feed.xml              # RSS con permalink
    ├── sitemap.xml           # generata automaticamente da costruisci_sito.py
    ├── CNAME                 # corrispondente.filoclastos.it
    └── {anno}/{mese}/{giorno}/{slug}/index.html   # permalink di ogni articolo
```

## Secrets richiesti (GitHub Actions)

- `ANTHROPIC_API_KEY` — per `genera.py`
- `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` — OAuth
  1.0a per `pubblica_tweet.py` (Consumer Key/Secret + Access Token/Secret
  del developer portal X, non le credenziali OAuth 2.0)

## Note tecniche

- **Permalink permanenti**: una volta creata, una pagina `{anno}/{mese}/{giorno}/{slug}/`
  non viene più cancellata da `costruisci_sito.py`, anche quando la sua
  edizione esce dalla finestra rolling di 30 giorni di `posts.json`.
- **Pagine orfane**: se `genera.py` viene rilanciato più volte per lo
  stesso giorno (es. in fase di test), `costruisci_sito.py` rimuove in
  automatico le pagine permalink delle versioni precedenti per quella
  stessa data — solo se la data è ancora dentro la finestra rolling.
- **`prompt.html`** non si genera ancora da solo dal `SYSTEM_PROMPT` di
  `genera.py`: se il prompt cambia (es. Fase 2), va aggiornato a mano per
  restare coerente con la pagina di trasparenza.
