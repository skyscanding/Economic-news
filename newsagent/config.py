"""
Configuration.

Edit INTEREST_PROFILE / INTEREST_KEYWORDS to tune what the ranker surfaces.
The profile is prose fed to Gemini; the keywords drive the cheap fallback
scorer and cross-check. Keep them roughly aligned.

Secrets come from the environment (GEMINI_API_KEY), never hardcoded.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Populate os.environ from a `.env` file (KEY=VALUE lines) if one exists.

    Looks in the current directory and the project root. Real environment
    variables always win (we only set defaults), so `set GEMINI_API_KEY=...`
    still overrides the file. Zero-dependency, so no python-dotenv needed.
    """
    seen = set()
    for candidate in (Path.cwd() / ".env",
                      Path(__file__).resolve().parent.parent / ".env"):
        if candidate in seen or not candidate.is_file():
            continue
        seen.add(candidate)
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(),
                                  val.strip().strip('"').strip("'"))


# --- Tune these two to your interests ----------------------------------------
INTEREST_PROFILE = """\
The reader is an active markets participant focused on semiconductors, AI
compute, and US mega-cap technology, plus broad-market and macro conditions.
Surface material news on these watchlist companies — earnings, guidance,
analyst rating/price-target changes, product and roadmap news, supply-chain
shifts, M&A, and regulation:

- Chip designers: Nvidia (NVDA), AMD (AMD), Intel (INTC), Qualcomm (QCOM).
- Memory: Micron (MU) — DRAM/HBM.
- Foundry, equipment & materials: TSMC (TSM), ASML (ASML, lithography),
  Tower Semiconductor (TSEM, analog foundry).
- Mega-cap platforms: Microsoft (MSFT), Alphabet/Google (GOOG),
  Amazon (AMZN), Apple (AAPL).
- AI software & data: Palantir (PLTR).
- Optical / AI-datacenter interconnect: Lumentum (LITE).
- EV & autonomy: Tesla (TSLA).
- Space & launch: SpaceX.

Macro & index context is high interest: the S&P 500 (SPY), Nasdaq-100 (QQQ)
and Dow (DIA); Federal Reserve policy and interest rates; inflation/CPI;
mega-cap earnings; and US-China tech policy, chip export controls, and Taiwan
risk given their impact on the names above.

Low interest: celebrity, sports, lifestyle, general opinion columns, and
consumer or human-interest stories unrelated to these companies or markets."""

# Fallback/cross-check scorer uses case-insensitive substring matching, so we
# favor distinctive company names + themes over ambiguous 2-3 letter tickers
# (e.g. "MU"/"DIA"/"SPY" would match "much"/"media"/"raspy"). The LLM profile
# above is the primary signal; this list only drives the no-API-key fallback.
INTEREST_KEYWORDS = [
    # Companies
    "nvidia", "nvda", "amd", "intel", "intc", "qualcomm", "qcom",
    "micron", "tsmc", "taiwan semiconductor", "asml", "tower semiconductor",
    "tsem", "microsoft", "msft", "alphabet", "google", "amazon", "apple",
    "aapl", "tesla", "tsla", "palantir", "pltr", "lumentum", "spacex",
    # Themes
    "semiconductor", "chip", "chips", "foundry", "lithography", "hbm",
    "memory chip", "gpu", "ai ", "artificial intelligence", "data center",
    "export control", "china", "taiwan", "ev ", "electric vehicle",
    # Macro / indices
    "s&p 500", "nasdaq", "dow jones", "federal reserve", "interest rate",
    "rate cut", "inflation", "cpi", "earnings", "guidance",
]


@dataclass
class Config:
    gemini_api_key: str | None = field(
        default_factory=lambda: os.environ.get("GEMINI_API_KEY"))
    deepseek_api_key: str | None = field(
        default_factory=lambda: os.environ.get("DEEPSEEK_API_KEY"))
    # Ranking model. Provider is inferred from the name: "deepseek-*" -> DeepSeek
    # (OpenAI-compatible endpoint), anything else -> Gemini.
    gemini_model: str = field(
        default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"))
    # Model used to build the portfolio exposure graph (reasoning-heavy, run
    # once + cached). Defaults to the rank model; DeepSeek V4-pro is a good pick.
    graph_model: str = field(
        default_factory=lambda: os.environ.get("GRAPH_MODEL", ""))
    gemini_max_retries: int = 3       # retry transient 429/5xx before falling back
    rank_chunk_size: int = 60         # headlines per LLM scoring call (smaller = less truncation)
    rank_workers: int = 5             # concurrent scoring calls (chunks in parallel)
    interest_profile: str = INTEREST_PROFILE
    interest_keywords: list[str] = field(
        default_factory=lambda: list(INTEREST_KEYWORDS))

    # Pipeline knobs
    per_feed_limit: int = 40          # max items pulled per feed
    dedupe_threshold: int = 85        # rapidfuzz token_set_ratio cutoff
    min_score_display: float = 0.0    # render everything; filter in the UI
    max_age_hours: float = 36.0       # default: drop anything older than this
    # Per-vendor age overrides for weekly/analysis outlets (hours).
    vendor_max_age_hours: dict = field(
        default_factory=lambda: {"The Economist": 336.0,     # ~14 days (weekly)
                                 "SemiAnalysis": 336.0,      # deep analysis, slow cadence
                                 "The Big Picture": 120.0})  # markets blog, ~5 days

    # Google News link resolution (Reuters/Bloomberg come via Google News)
    resolve_gnews: bool = True        # decode redirect links to source URLs
    gnews_workers: int = 8            # concurrency for the decode handshake

    @classmethod
    def load(cls) -> "Config":
        _load_dotenv()          # fill os.environ from .env before reading fields
        return cls()
