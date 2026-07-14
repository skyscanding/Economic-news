# Economic News Agent

Daily financial news aggregator — fetches RSS from major outlets, deduplicates,
ranks by relevance with Gemini or DeepSeek, serves a local interactive frontend.
Works without an API key (keyword fallback).

## Quick start

```bash
git clone https://github.com/skyscanding/Economic-news.git && cd Economic-news
python -m venv .venv
.venv\Scripts\activate         # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # then add your key (or skip — works with keywords)
```

**Run:**

```bash
start.bat                      # web interface → http://localhost:8765
run.bat                        # CLI: all feeds, writes output/news_YYYY-MM-DD.html
run.bat --sections Technology --no-open
```

## When to use which mode

```
Using daily? ──yes──→ Web interface (start.bat)
    │
    no
    │
Need automation/cron? ──yes──→ CLI (run.bat)
    │
    no
    │
Debugging a single run? ──yes──→ CLI with --no-open
```

## Tuning (edit `newsagent/config.py`)

| Knob | Default | What it controls |
|------|---------|-----------------|
| `INTEREST_PROFILE` | prose block | The reader's interests (fed to the LLM as system prompt) |
| `INTEREST_KEYWORDS` | company/theme list | Fallback scoring when no API key or API errors |
| `dedupe_threshold` | 85 | Title similarity cutoff (0–100); lower = more aggressive merging |
| `max_age_hours` | 36 | Drop stories older than this |
| `per_feed_limit` | 40 | Max items pulled per RSS feed |
| `rank_chunk_size` | 60 | Headlines per LLM call |
| `rank_workers` | 5 | Concurrent LLM scoring workers |

## Web interface (localhost:8765)

```
┌─ Header ──────────────────────────────────────────────┐
│ [Premium vendors] [Independent] [Sections]  ◐ theme   │
│ Portfolio: NVDA 25%, TSM 15%...  [Save] [Delete]      │
│ Key: [········]  Model: [gemini-3.5-flash ▼] [Refresh]│
│ Quick: nvidia  amd  tsmc  chip  fed  earnings  ...    │
│ Search: [________]  Min: [0──●──10]  Sort/Group by... │
└───────────────────────────────────────────────────────┘
│  ★ 7  Nvidia raises Blackwell guidance                    │
│       Bloomberg · 3h ago                                  │
│       reason: Directly impacts NVDA position               │
│       [NVDA·direct] [TSM·supplier]                         │
│       also at Reuters · WSJ                                │
```

### Score interpretation

| Score | Meaning |
|-------|---------|
| 8–10 | High materiality — directly on your thesis |
| 5–7  | Moderate — tangentially relevant |
| 0–4  | Noise — safe to filter out |

In **portfolio mode** (when you enter holdings), scores reflect *materiality to your book*,
including second-order effects: a TSMC supplier shortage matters to your NVDA position even
if "NVDA" never appears in the headline. Each story is attributed by channel:
`direct` · `supplier` · `customer` · `competitor` · `macro` · `regulatory`.

## Feeds

| Vendor | Sections | Source |
|--------|----------|--------|
| Financial Times | Business, Technology, World | Native RSS |
| Wall Street Journal | Business, Technology, World | Native RSS |
| The Economist | Business, Technology, World | Native RSS |
| Bloomberg | Business, Technology, World | Google News RSS |
| Reuters | Business, Technology, World | Google News RSS |
| Washington Post | Business, Technology, World | Google News RSS |
| SemiAnalysis | Technology | Native RSS |
| Ars Technica | Technology | Native RSS |
| Hacker News | Technology | hnrss.org |
| Calculated Risk | Business | Native RSS |
| The Big Picture | Business | Native RSS |

FT/WSJ/Bloomberg/Economist links may hit paywalls — you read what your subscription allows.

## Architecture

```
feeds ──→ fetch ──→ age filter ──→ dedupe ──→ resolve gnews links
                                                  │
                                     ┌────────────┘
                                     ▼
                           rank (LLM / keywords)
                                     │
                            ┌────────┴────────┐
                            ▼                  ▼
                     render (static)     server (SPA)
```

## API key setup

Get a free Gemini key at [aistudio.google.com](https://aistudio.google.com/apikey).
DeepSeek keys from [platform.deepseek.com](https://platform.deepseek.com).

```bash
# .env (git-ignored)
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash         # or deepseek-v4-flash
DEEPSEEK_API_KEY=your_key_here        # only if using deepseek-* models
```

No key? The agent still runs — it falls back to keyword matching from `INTEREST_KEYWORDS`.
The LLM path is more accurate (context-aware scoring), but keywords are a working baseline.

## Common issues

| Symptom | Fix |
|---------|-----|
| "0 stories fetched" | Feed URLs may have changed — check `feeds.py` and verify URLs in browser |
| All scores are keyword-based | API key missing or expired; check `.env` |
| Google News links don't resolve | Cache may be stale — delete `output/.gnews_cache.json` and re-run |
| Server won't start | Port 8765 in use; set `NEWSAGENT_PORT=9000` |
| "model not found" | Check model name in dropdown; free-tier keys may not access all models |

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## License

See [LICENSE](./LICENSE).
