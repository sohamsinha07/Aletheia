# Aletheia â€” Multi-Perspective News Digest

Aletheia is a local news pipeline that fetches articles from across the political spectrum every day, clusters stories about the same event, and uses an LLM to produce a single digest card per story â€” showing shared facts and where left/right coverage diverges.

---

## How it works

```
RSS Feeds â†’ ingest.py â†’ embed_cluster.py â†’ synthesize.py â†’ database.py â†’ API â†’ Frontend
```

1. **Ingest** â€” fetches RSS feeds from 8 sources (NPR, BBC, Guardian, The Hill, Fox News, Washington Times, Axios, and more)
2. **Embed & Cluster** â€” converts each article to a vector using a free local model, then groups articles about the same story together
3. **Synthesize** â€” sends each story cluster to an LLM (OpenAI or Anthropic) and gets back a neutral summary + perspective breakdown
4. **Serve** â€” FastAPI stores the edition in SQLite and serves it to the frontend
5. **Display** â€” a single HTML page renders the story cards with genre filters and source links

---

## Requirements

- Python 3.10+
- An OpenAI API key (or Anthropic key)
- ~500MB disk space for the local embedding model (downloads once automatically)

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/sohamsinha07/Aletheia.git
cd Aletheia
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 3. Configure your API key

Create a file called `.env` inside the `backend/` folder:

```bash
touch backend/.env
```

Open it and add the following (fill in your actual key):

```
OPENAI_API_KEY=sk-...your-key-here...
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_PROVIDER=local
MAX_CLUSTERS=10
MIN_CLUSTER_SIZE=2
FRONTEND_URL=http://localhost:3000
```

> **Using Anthropic instead?** Set `LLM_PROVIDER=anthropic` and add `ANTHROPIC_API_KEY=sk-ant-...` instead of `OPENAI_API_KEY`.

> **Get an OpenAI key** at [platform.openai.com](https://platform.openai.com) â€” you'll need a few dollars of credit. Each pipeline run costs roughly $0.03.

---

## Running the project

You need **three terminal tabs** open at the same time.

### Tab 1 â€” Run the pipeline (generates today's digest)

```bash
cd /path/to/Aletheia
source .venv/bin/activate
python3 backend/pipeline.py
```

This takes 2â€“4 minutes on first run (it downloads the embedding model). You'll see it fetch articles, cluster them, and call the LLM. When it finishes you'll see something like:

```
Pipeline complete! Edition 1: 5 stories
```

> You only need to run this once to see content. After that, the Refresh button in the UI triggers it again whenever you want fresh news.

### Tab 2 â€” Start the API server

```bash
cd /path/to/Aletheia
source .venv/bin/activate
python3 backend/api.py
```

Leave this running. You should see:

```
Uvicorn running on http://0.0.0.0:8000
```

### Tab 3 â€” Start the frontend server

```bash
cd /path/to/Aletheia
source .venv/bin/activate
python3 -m http.server 3000 --directory frontend
```

Leave this running too. You should see:

```
Serving HTTP on port 3000
```

### Open the app

Go to **[http://localhost:3000](http://localhost:3000)** in your browser.

> âš ï¸ Do NOT open `frontend/index.html` directly as a file â€” it will be blocked by browser security. Always use `http://localhost:3000`.

---

## Daily usage

Once set up, your daily workflow is:

1. Open a terminal and start the API: `python3 backend/api.py`
2. Open another terminal and start the frontend: `python3 -m http.server 3000 --directory frontend`
3. Go to `http://localhost:3000`
4. Click **Refresh** to fetch today's news â€” takes ~2â€“4 minutes

---

## Project structure

```
Aletheia/
â”œâ”€â”€ backend/
â”‚   â”œâ”€â”€ ingest.py          # Step 1: fetch RSS feeds
â”‚   â”œâ”€â”€ embed_cluster.py   # Step 2: embed articles + cluster by story
â”‚   â”œâ”€â”€ synthesize.py      # Step 3: LLM synthesis per cluster
â”‚   â”œâ”€â”€ database.py        # SQLite storage
â”‚   â”œâ”€â”€ pipeline.py        # Orchestrator â€” runs steps 1-3 in sequence
â”‚   â”œâ”€â”€ api.py             # FastAPI server (port 8000)
â”‚   â”œâ”€â”€ sources.json       # News source list with lean labels
â”‚   â”œâ”€â”€ requirements.txt   # Python dependencies
â”‚   â””â”€â”€ .env               # Your API keys (never commit this)
â”œâ”€â”€ frontend/
â”‚   â””â”€â”€ index.html         # Single-page UI
â”œâ”€â”€ data/
â”‚   â””â”€â”€ aletheia.db        # SQLite database (auto-created on first run)
â””â”€â”€ .github/
    â””â”€â”€ workflows/
        â””â”€â”€ daily_pipeline.yml  # Optional: GitHub Actions for automated daily runs
```

---

## News sources

| Source | Lean |
|---|---|
| NPR | Lean Left |
| The Guardian | Left |
| BBC News | Center |
| The Hill | Center |
| Axios | Center |
| Fox News | Lean Right |
| Washington Times | Right |
| Associated Press | Center |

---

## Troubleshooting

**Pipeline returns 0 articles**
RSS feeds may be blocking requests. Make sure `ingest.py` is passing a User-Agent header in the feedparser call.

**UI stuck on "Loading latest edition"**
Make sure both `api.py` (port 8000) and the frontend server (port 3000) are running, and that you're opening `http://localhost:3000` not `file://...`.

**SyntaxError in any .py file mentioning markdown-style links**
Some files may have been corrupted during copy-paste (markdown links like `[x.app](...)end` instead of `x.append`). Run the pipeline from this repo directly â€” all files here are clean.

**LLM returns no stories**
Check that your `.env` file is inside the `backend/` folder and that your API key is valid and has credit.

---

## Cost estimate

| Component | Cost |
|---|---|
| Embedding model | Free (runs locally) |
| LLM synthesis (gpt-4o-mini, ~10 stories/day) | ~$0.03/day |
| RSS feeds | Free |
| Hosting (local) | Free |

---

## Roadmap

- [ ] Fix remaining `appendChild` corruption in `frontend/index.html`
- [ ] Add more news sources across the spectrum
- [ ] Genre filtering fully working end-to-end
- [ ] Email digest delivery
- [ ] Hosted deployment (Railway + Vercel)
- [ ] User-configurable source lists