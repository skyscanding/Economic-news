# Economic News Agent

Daily financial news aggregator with LLM-based relevance ranking. Fetches RSS
feeds from major financial outlets, deduplicates across sources, and ranks
stories by relevance using Gemini or DeepSeek — with automatic keyword-based
fallback if no API key is available.

## Features

- **Multi-source RSS aggregation** — Financial Times, Wall Street Journal,
  Bloomberg, Reuters, Washington Post, The Economist, SemiAnalysis, and more
- **Cross-outlet deduplication** — Same story across vendors is merged, with
  alternate links shown
- **LLM relevance ranking (0–10)** — Scores articles against your interest
  profile or portfolio holdings using Gemini or DeepSeek
- **Fail-open keyword fallback** — Works even without any API key; just less
  precise
- **Portfolio mode** — Input your holdings (e.g. `NVDA 25%, TSM 15%`) and get
  materiality scores with second-order effect attribution (suppliers, customers,
  competitors, macro, regulatory)
- **Two interfaces**: CLI (writes a static HTML file) and Web (interactive
  single-page app served locally)

## Quick start

### 1. Clone & set up

```bash
git clone https://github.com/skyscanding/Economic-news.git
cd Economic-news
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure (optional)

Copy the example env file and add your API key(s):

```bash
cp .env.example .env
```

Then edit `.env` — at minimum set `GEMINI_API_KEY`. Get a free key at
[aistudio.google.com](https://aistudio.google.com/apikey). If you skip this,
the agent still works using keyword matching.

For DeepSeek (optional, good at financial reasoning):
set `GEMINI_MODEL=deepseek-v4-flash` and add `DEEPSEEK_API_KEY` from
[platform.deepseek.com](https://platform.deepseek.com).

### 3. Run

**Web interface** (recommended for daily use):

```bash
start.bat                  # Windows
python -m newsagent.server # any platform
```

Opens a browser at `http://localhost:8765` where you can select sources,
set the model, enter a portfolio, and re-rank interactively. The server
auto-shuts down ~12 seconds after you close the tab.

**CLI mode** (good for scheduled/cron runs):

```bash
run.bat                                            # all vendors, all sections
run.bat --sections Technology World                # specific sections
run.bat --vendors Reuters Bloomberg                # specific vendors
run.bat --no-open                                  # write file, don't open browser
python -m newsagent.main --sections Business World  # raw Python equivalent
```

Output lands in `./output/news_YYYY-MM-DD.html`.

## Tuning

Edit `newsagent/config.py` to customize:

| Setting | What it does |
|---------|-------------|
| `INTEREST_PROFILE` | Prose describing what you care about (fed to the LLM) |
| `INTEREST_KEYWORDS` | Fallback keyword list for scoring without an API key |
| `dedupe_threshold` | Title similarity cutoff for merging stories (0–100) |
| `max_age_hours` | Drop stories older than this (default 36h) |
| `vendor_max_age_hours` | Per-vendor overrides (e.g. weekly magazines get longer) |
| `per_feed_limit` | Max items fetched per RSS feed |
| `rank_chunk_size` | Headlines per LLM call (smaller = less risk of truncation) |
| `rank_workers` | Concurrent LLM scoring workers |

## Web interface guide

![screenshot placeholder]

### Controls

| Section | What it does |
|---------|-------------|
| **Premium / Independent / Sections** | Checkboxes to select which feeds to fetch |
| **Portfolio** | Enter holdings like `NVDA 25%, TSM 15%, ASML 10%` — switches to portfolio materiality scoring |
| **API key / Model** | Override the key or model for this session (blank = use `.env`) |
| **Quick filters** | One-click chips to filter by topic (nvidia, fed, earnings, etc.) |
| **Search** | Free-text filter across title, vendor, reason, and keyword hits |
| **Min score** | Slider to hide low-relevance stories |
| **Sort** | By relevance, newest-first, or vendor |
| **Group** | By section or by portfolio holding |
| **★ / ✕** | Star (persists in localStorage) or hide individual stories |
| **◐ Theme** | Toggle light/dark |

### Understanding scores

- **8–10** — High relevance or materiality; directly on-topic for your interests/portfolio
- **5–7** — Moderate; tangentially related or lower conviction
- **0–4** — Low; likely noise unless it's a slow news day

In portfolio mode, stories are attributed to specific holdings with a channel
(`direct`, `supplier`, `customer`, `competitor`, `macro`, `regulatory`) so you
can see *why* a story matters to your book.

## Architecture

```
RSS feeds ──→ fetch ──→ age filter ──→ deduplicate ──→ resolve links
                                                           │
                                              ┌────────────┘
                                              ▼
                                rank (LLM or keywords)
                                              │
                                     ┌────────┴────────┐
                                     ▼                  ▼
                              render (static)     web server (SPA)
```

### Key modules

| Module | Role |
|--------|------|
| `config.py` | All settings: interest profile, keywords, pipeline knobs |
| `feeds.py` | RSS feed registry (native feeds + Google News fallbacks) |
| `fetch.py` | Fetch and normalize RSS entries |
| `dedupe.py` | Cross-outlet deduplication via fuzzy title matching |
| `gnews.py` | Decode Google News redirect links to real source URLs |
| `providers.py` | LLM abstraction layer (Gemini SDK / DeepSeek OpenAI-compatible) |
| `rank.py` | Batch scoring: LLM chunks with concurrent workers, keyword fallback |
| `portfolio.py` | Portfolio parsing → exposure graph (suppliers/customers/competitors/macro) |
| `render.py` | Self-contained static HTML output |
| `webapp.py` | Interactive SPA frontend (inline HTML/CSS/JS) |
| `server.py` | Zero-dependency HTTP server with heartbeat-based auto-shutdown |

## Vendors & feeds

| Vendor | Mechanism | Paywall |
|--------|-----------|---------|
| Financial Times | Native RSS (`?format=rss`) | Yes |
| Wall Street Journal | Native RSS (Dow Jones feeds) | Yes |
| The Economist | Native RSS | Yes |
| Bloomberg | Google News RSS | Yes |
| Reuters | Google News RSS | No |
| Washington Post | Google News RSS | Soft |
| SemiAnalysis | Native RSS | Yes |
| Ars Technica | Native RSS | No |
| Hacker News | Native RSS (hnrss.org) | No |
| Calculated Risk | Native RSS | No |
| The Big Picture | Native RSS | No |

FT/WSJ/Bloomberg/Economist links may hit paywalls — you read what your
subscriptions allow. The agent only links to source sites; it does not
reproduce article content.

## Notes

- If no API key is set, ranking falls back to keyword scoring — the run
  still produces a usable page (fail-open design)
- Google News links for Reuters/Bloomberg/WaPo are resolved to real source
  URLs via a two-step handshake; results are cached in `output/.gnews_cache.json`
- The HTML page has a "min relevance" slider (vanilla JS) to adjust the cutoff
  without re-running
- Verify feed URLs occasionally; outlets change them
- Portfolio exposure graphs for known tickers are hand-curated (in `SEED`
  within `portfolio.py`); unknown tickers are enriched once via LLM and cached

## Running tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## License

See [LICENSE](./LICENSE).
