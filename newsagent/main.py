"""
Entry point. Wires the pipeline together:

  fetch -> normalize -> filter by age -> dedupe -> rank (Gemini) -> render -> open

Run:
    python -m newsagent.main                 # all vendors, all sections
    python -m newsagent.main --sections Technology World
    python -m newsagent.main --vendors Reuters "Financial Times"
    python -m newsagent.main --no-open       # write file, don't launch browser
"""
from __future__ import annotations
import argparse
import logging
from pathlib import Path

from .config import Config
from .feeds import feeds_for, SECTIONS
from .fetch import fetch_all
from .dedupe import deduplicate
from .gnews import resolve_links
from .rank import rank
from .render import render_html, open_in_browser


def _filter_age(headlines, cfg):
    """Drop stale items. Per-vendor overrides let weekly outlets (e.g. The
    Economist) use a longer window than the daily-news default."""
    overrides = cfg.vendor_max_age_hours or {}
    kept = []
    for h in headlines:
        limit = overrides.get(h.vendor, cfg.max_age_hours)
        if h.age_hours is None or h.age_hours <= limit:
            kept.append(h)
    return kept


def run(vendors=None, sections=None, no_open=False, out_dir=None,
        portfolio=None) -> Path:
    cfg = Config.load()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-18s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("newsagent")

    sources = feeds_for(vendors=vendors, sections=sections)
    log.info("fetching %d feeds", len(sources))

    headlines = fetch_all(sources, limit=cfg.per_feed_limit)
    log.info("fetched %d raw headlines", len(headlines))

    headlines = _filter_age(headlines, cfg)
    headlines = deduplicate(headlines, threshold=cfg.dedupe_threshold)

    out_dir = out_dir or Path.cwd() / "output"
    if cfg.resolve_gnews:
        resolve_links(headlines, workers=cfg.gnews_workers,
                      cache_path=out_dir / ".gnews_cache.json")

    exposure = None
    if portfolio:
        from .portfolio import build_exposure_graph
        exposure = build_exposure_graph(portfolio, cfg)
        log.info("portfolio mode: %d holdings", len(exposure))
    headlines = rank(headlines, cfg, exposure=exposure)
    path = render_html(headlines, cfg, out_dir)
    if not no_open:
        open_in_browser(path)
    log.info("done: %s", path)
    return path


def main():
    p = argparse.ArgumentParser(description="Daily RSS news agent with Gemini ranking")
    p.add_argument("--vendors", nargs="*", help="subset of vendors")
    p.add_argument("--sections", nargs="*", choices=list(SECTIONS),
                   help="subset of sections")
    p.add_argument("--no-open", action="store_true", help="don't open browser")
    p.add_argument("--out", type=Path, default=None, help="output directory")
    args = p.parse_args()
    run(vendors=args.vendors, sections=args.sections,
        no_open=args.no_open, out_dir=args.out)


if __name__ == "__main__":
    main()
