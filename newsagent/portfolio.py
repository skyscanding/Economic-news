"""
Portfolio -> exposure graph -> materiality scoring.

The differentiator: instead of matching ticker symbols, we expand each holding
into an *exposure graph* (suppliers, customers, competitors, sector, macro and
regulatory sensitivities), then score each article for how much it moves the
whole book — including second-order effects (a TSMC story matters to an NVDA
holder even if "NVDA" never appears).

Design (as evaluated with the user):
  * HYBRID graph. A curated seed map covers the well-known mega-cap/semis names
    reliably; unknown tickers are enriched by an LLM once and cached. This avoids
    hallucinated supply-chain links for the names that matter most.
  * WEIGHTS matter. Materiality scales with position size, so a supplier story
    hitting a 20% position outranks a direct story on a 2% one.
  * INDEX holdings (SPY/QQQ/DIA) are treated as a macro/breadth backdrop, not
    per-name relevance, so they don't flood the feed.

Nothing here is investment advice — it is information filtering by relevance to
stated positions.
"""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path

log = logging.getLogger("newsagent.portfolio")

_CACHE = Path.cwd() / "output" / ".exposure_cache.json"

# Broad-market ETFs -> macro backdrop, not single-name exposure.
INDEX_TICKERS = {"SPY", "QQQ", "DIA", "IWM", "VOO", "VTI", "SOXX", "SMH"}
_INDEX_ENTRY = {
    "kind": "index",
    "direct": [],
    "macro": ["Federal Reserve", "interest rates", "inflation", "CPI",
              "market breadth", "risk sentiment", "recession odds"],
}

# --- Curated seed exposure map (the user's watchlist + common peers) ----------
# Compact but deliberate: suppliers = upstream, customers = downstream demand,
# competitors = read-through names, macro/regulatory = factor sensitivities.
SEED: dict[str, dict] = {
    "NVDA": {"direct": ["Nvidia", "Jensen Huang", "Blackwell", "Rubin", "CUDA"],
             "suppliers": ["TSMC", "ASML", "SK Hynix", "Micron", "Vertiv", "SK hynix HBM"],
             "customers": ["Microsoft", "Google", "Amazon", "Meta", "CoreWeave", "Oracle"],
             "competitors": ["AMD", "Google TPU", "AWS Trainium", "Cerebras", "Broadcom"],
             "macro": ["data-center power", "interest rates", "AI capex cycle"],
             "regulatory": ["US-China export controls", "Taiwan risk"]},
    "AMD": {"direct": ["AMD", "Lisa Su", "Instinct MI", "EPYC", "Ryzen"],
            "suppliers": ["TSMC", "ASML", "Micron", "SK Hynix"],
            "customers": ["Microsoft", "Meta", "Oracle", "hyperscalers"],
            "competitors": ["Nvidia", "Intel"],
            "macro": ["AI capex cycle", "PC demand"],
            "regulatory": ["US-China export controls"]},
    "INTC": {"direct": ["Intel", "Intel Foundry", "Gaudi", "18A"],
             "suppliers": ["ASML", "Applied Materials", "Lam Research"],
             "customers": ["PC OEMs", "data-center customers"],
             "competitors": ["TSMC", "AMD", "Nvidia", "Samsung Foundry"],
             "macro": ["PC demand", "US CHIPS Act subsidies"],
             "regulatory": ["CHIPS Act", "US-China export controls"]},
    "QCOM": {"direct": ["Qualcomm", "Snapdragon"],
             "suppliers": ["TSMC", "Samsung Foundry"],
             "customers": ["Apple", "Samsung", "Android OEMs", "smartphone makers"],
             "competitors": ["MediaTek", "Apple silicon"],
             "macro": ["smartphone demand", "China demand"],
             "regulatory": ["US-China trade", "Apple modem in-sourcing"]},
    "MU": {"direct": ["Micron", "DRAM", "NAND", "HBM"],
           "suppliers": ["ASML", "Applied Materials", "Lam Research"],
           "customers": ["Nvidia", "AMD", "hyperscalers", "smartphone makers"],
           "competitors": ["SK Hynix", "Samsung"],
           "macro": ["memory pricing cycle", "AI capex cycle"],
           "regulatory": ["US-China export controls"]},
    "TSM": {"direct": ["TSMC", "Taiwan Semiconductor", "advanced packaging", "CoWoS"],
            "suppliers": ["ASML", "Applied Materials", "Lam Research", "Tokyo Electron"],
            "customers": ["Nvidia", "AMD", "Apple", "Qualcomm", "Broadcom"],
            "competitors": ["Samsung Foundry", "Intel Foundry"],
            "macro": ["AI capex cycle", "global chip demand"],
            "regulatory": ["Taiwan risk", "US-China export controls", "US fab subsidies"]},
    "ASML": {"direct": ["ASML", "EUV", "High-NA lithography"],
             "suppliers": ["Zeiss", "optics suppliers"],
             "customers": ["TSMC", "Samsung", "Intel", "Micron", "SK Hynix"],
             "competitors": ["Nikon", "Canon"],
             "macro": ["semiconductor capex cycle"],
             "regulatory": ["Netherlands-China export rules", "US-China controls"]},
    "TSEM": {"direct": ["Tower Semiconductor", "analog foundry"],
             "suppliers": ["semi equipment vendors"],
             "customers": ["analog chip designers", "RF/power customers"],
             "competitors": ["GlobalFoundries", "TSMC specialty"],
             "macro": ["analog chip demand", "auto/industrial demand"],
             "regulatory": ["Israel geopolitics"]},
    "MSFT": {"direct": ["Microsoft", "Azure", "Copilot", "OpenAI stake"],
             "suppliers": ["Nvidia", "AMD", "OpenAI", "data-center builders"],
             "customers": ["enterprise IT", "cloud customers"],
             "competitors": ["Amazon AWS", "Google Cloud"],
             "macro": ["AI capex cycle", "enterprise IT spend"],
             "regulatory": ["antitrust", "EU regulation", "OpenAI governance"]},
    "GOOG": {"direct": ["Alphabet", "Google", "Gemini", "TPU", "Google Cloud", "Waymo"],
             "suppliers": ["Broadcom", "TSMC", "Nvidia"],
             "customers": ["advertisers", "cloud customers"],
             "competitors": ["Microsoft", "Amazon", "OpenAI", "Meta"],
             "macro": ["ad spend", "AI capex cycle"],
             "regulatory": ["antitrust", "search remedies", "EU DMA"]},
    "AMZN": {"direct": ["Amazon", "AWS", "Trainium", "Inferentia"],
             "suppliers": ["Nvidia", "AMD", "logistics"],
             "customers": ["cloud customers", "retail consumers"],
             "competitors": ["Microsoft Azure", "Google Cloud", "Walmart"],
             "macro": ["consumer spending", "AI capex cycle"],
             "regulatory": ["antitrust", "labor"]},
    "AAPL": {"direct": ["Apple", "iPhone", "Apple silicon", "Apple Intelligence"],
             "suppliers": ["TSMC", "Qualcomm", "Foxconn", "Broadcom", "Sony"],
             "customers": ["consumers"],
             "competitors": ["Samsung", "Google", "Huawei"],
             "macro": ["consumer spending", "China demand"],
             "regulatory": ["antitrust", "App Store rules", "EU DMA", "China exposure"]},
    "TSLA": {"direct": ["Tesla", "Elon Musk", "FSD", "Optimus", "Dojo", "Cybercab"],
             "suppliers": ["Panasonic", "CATL", "LG Energy", "Nvidia"],
             "customers": ["EV consumers"],
             "competitors": ["BYD", "legacy automakers", "Waymo"],
             "macro": ["EV demand", "interest rates", "lithium prices"],
             "regulatory": ["EV tax credits", "autonomy regulation", "China exposure"]},
    "PLTR": {"direct": ["Palantir", "Foundry", "Gotham", "AIP"],
             "suppliers": ["cloud providers", "LLM vendors"],
             "customers": ["US government", "defense", "enterprises"],
             "competitors": ["Snowflake", "Databricks", "in-house data teams"],
             "macro": ["defense budgets", "enterprise AI adoption"],
             "regulatory": ["government contracting", "defense policy"]},
    "LITE": {"direct": ["Lumentum", "optical transceivers", "photonics"],
             "suppliers": ["chip and optics suppliers"],
             "customers": ["Nvidia", "hyperscalers", "network equipment makers"],
             "competitors": ["Coherent", "Marvell optical"],
             "macro": ["AI data-center interconnect demand"],
             "regulatory": ["US-China trade"]},
    "SPCX": {"direct": ["SpaceX", "Starlink", "Starship", "Elon Musk"],
             "suppliers": ["aerospace suppliers"],
             "customers": ["satellite/launch customers", "governments", "telecom"],
             "competitors": ["Rocket Lab", "Blue Origin", "traditional telecom"],
             "macro": ["space/launch demand", "satellite broadband"],
             "regulatory": ["FAA", "FCC spectrum", "defense contracts"]},
}

_WEIGHT_RE = re.compile(
    r"([A-Za-z\.\-]{1,6})\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%?")


def parse_portfolio(text: str) -> list[dict]:
    """Parse 'NVDA 20%, TSM 15%, ASML 10' into [{ticker, weight}] (weights 0-1).

    Bare tickers with no number get an equal residual share. Weights are
    normalized to sum to 1.0 when any are given.
    """
    if not text:
        return []
    items: list[dict] = []
    # Split on commas/newlines; each chunk like "NVDA 20%" or "NVDA".
    for chunk in re.split(r"[,\n;]+", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = _WEIGHT_RE.match(chunk)
        if m:
            items.append({"ticker": m.group(1).upper(), "weight": float(m.group(2))})
        else:
            tok = re.match(r"[A-Za-z\.\-]{1,6}", chunk)
            if tok:
                items.append({"ticker": tok.group(0).upper(), "weight": None})
    if not items:
        return []
    # Fill missing weights with the average of the remainder, then normalize.
    known = [i["weight"] for i in items if i["weight"] is not None]
    known_sum = sum(known)
    missing = [i for i in items if i["weight"] is None]
    if missing:
        residual = max(0.0, 100.0 - known_sum) or float(len(missing))
        each = residual / len(missing)
        for i in missing:
            i["weight"] = each
    total = sum(i["weight"] for i in items) or 1.0
    for i in items:
        i["weight"] = round(i["weight"] / total, 4)
    return items


def _load_cache() -> dict:
    if _CACHE.exists():
        try:
            return json.loads(_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    except Exception as e:
        log.debug("exposure cache write failed: %s", e)


def _enrich_unknown(tickers: list[str], cfg) -> dict:
    """LLM-generate exposure entries for tickers not in SEED. Cached per ticker."""
    from . import providers
    model = cfg.graph_model or cfg.gemini_model
    key = providers.api_key_for(model, cfg)
    if not key or not providers.sdk_available(model):
        log.info("no key/SDK for graph enrichment; using direct-only for %s", tickers)
        return {t: {"direct": [t], "kind": "unknown"} for t in tickers}

    system = ("You are a financial analyst mapping equity exposure. For each "
              "ticker return suppliers (upstream), customers (downstream), "
              "competitors, macro sensitivities, and regulatory/geographic "
              "exposures. Return ONLY a JSON object keyed by ticker; each value "
              "has keys direct, suppliers, customers, competitors, macro, "
              "regulatory (arrays of short names). No prose.")
    user = "Tickers: " + ", ".join(tickers) + "\nReturn the JSON now."
    try:
        raw = providers.complete_json(model, system, user, key, temperature=0.1)
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned)
        out = {}
        for t in tickers:
            entry = data.get(t) or data.get(t.upper()) or {"direct": [t]}
            entry["kind"] = "llm"
            out[t] = entry
        return out
    except Exception as e:
        log.warning("graph enrichment failed (%s); direct-only fallback", e)
        return {t: {"direct": [t], "kind": "unknown"} for t in tickers}


def build_exposure_graph(portfolio: list[dict], cfg) -> dict:
    """Return {ticker: {weight, kind, direct, suppliers, ...}} for the holdings."""
    graph: dict[str, dict] = {}
    unknown: list[str] = []
    for h in portfolio:
        t = h["ticker"].upper()
        w = h.get("weight")
        if t in INDEX_TICKERS:
            graph[t] = {**_INDEX_ENTRY, "weight": w}
        elif t in SEED:
            graph[t] = {**SEED[t], "kind": "seed", "weight": w}
        else:
            unknown.append(t)
            graph[t] = {"direct": [t], "kind": "unknown", "weight": w}

    if unknown:
        cache = _load_cache()
        need = [t for t in unknown if t not in cache]
        if need:
            cache.update(_enrich_unknown(need, cfg))
            _save_cache(cache)
        for t in unknown:
            if t in cache:
                graph[t] = {**cache[t], "weight": graph[t]["weight"]}
    return graph


def exposure_to_prompt(graph: dict) -> str:
    """Render the graph as the READER PORTFOLIO block for the scoring prompt."""
    lines = ["READER PORTFOLIO (score each story by how much it moves these "
             "positions, including second-order effects via the listed "
             "suppliers, customers, competitors, and sensitivities):"]
    # Heaviest positions first so the model anchors on them.
    for t, e in sorted(graph.items(), key=lambda kv: -(kv[1].get("weight") or 0)):
        w = e.get("weight")
        wl = f" ({round(w*100)}% of book)" if w else ""
        if e.get("kind") == "index":
            lines.append(f"- {t}{wl}: broad-market/macro exposure "
                         f"[{', '.join(e.get('macro', []))}]")
            continue
        parts = []
        for label in ("direct", "suppliers", "customers", "competitors",
                      "macro", "regulatory"):
            vals = e.get(label)
            if vals:
                parts.append(f"{label}: {', '.join(vals)}")
        lines.append(f"- {t}{wl}: " + "; ".join(parts))
    return "\n".join(lines)
