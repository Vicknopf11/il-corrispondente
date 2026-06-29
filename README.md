# Il Corrispondente 🗞️

Agente satirico autonomo che ogni mattina cerca le notizie più assurde del giorno
e genera post ironici pronti per X (Twitter).

## Setup in 5 passi

### 1. Crea il repository su GitHub
- Vai su [github.com/new](https://github.com/new)
- Nome: `il-corrispondente`
- Visibilità: **Public** (richiesto per GitHub Pages gratuito)
- Clicca *Create repository*

### 2. Carica i file
```bash
git init
git add .
git commit -m "primo commit"
git branch -M main
git remote add origin https://github.com/TUO_USERNAME/il-corrispondente.git
git push -u origin main
```

### 3. Aggiungi la chiave API
- Settings → Secrets and variables → Actions → *New repository secret*
- Nome: `ANTHROPIC_API_KEY`
- Valore: la tua chiave `sk-ant-...`

### 4. Attiva GitHub Pages
- Settings → Pages
- Source: **Deploy from a branch**
- Branch: `main` — cartella: `/docs`
- Clicca *Save*

### 5. Prima esecuzione manuale
- Actions → "Genera Post Satirici" → *Run workflow*
- Aspetta ~30 secondi
- Il sito si aggiorna automaticamente

Il sito sarà live su: `https://TUO_USERNAME.github.io/il-corrispondente/`

Da quel momento l'agente gira **ogni giorno alle 09:00** (ora italiana) senza intervento.

## Personalizzazione

Modifica le prime righe di `genera.py`:

```python
NUM_NOTIZIE = 5        # quante notizie per edizione
REGISTRO = "cronista"  # cronista | osservatore | burocrate | futuro
```

## Struttura
```
il-corrispondente/
├── .github/
│   └── workflows/
│       └── genera-post.yml   # cron job giornaliero
├── docs/
│   ├── index.html            # sito pubblico (GitHub Pages)
│   └── posts.json            # archivio ultimi 30 giorni
├── genera.py                 # agente satirico
└── README.md
```

## Costi
- GitHub Actions: gratuito (2000 min/mese inclusi, ne usa ~1 al giorno)
- GitHub Pages: gratuito
- Anthropic API: ~€0.01–0.05 per esecuzione
