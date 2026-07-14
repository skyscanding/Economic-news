"""
Feed registry: one RSS feed per vendor per section.

Two mechanisms:
  - "native"  : the outlet publishes a working section RSS feed.
  - "gnews"   : the outlet has no reliable public feed, so we query
                Google News RSS filtered to that outlet's domain.

Native feeds (FT, WSJ, Washington Post) are preferred: richer metadata,
direct article links. Reuters dropped public RSS in 2020 and Bloomberg's
native feeds are flaky/rate-limited, so both go through Google News RSS.

SECTIONS is the canonical taxonomy. Every FeedSource is tagged with one of
these so the pipeline can group cleanly regardless of the vendor's own labels.
"""
from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import quote_plus

SECTIONS = ("Business", "Technology", "World")


def gnews_url(site: str, section_query: str) -> str:
    """Build a Google News RSS search URL scoped to one outlet + topic, last 24h."""
    q = f"site:{site} {section_query} when:1d"
    return (
        "https://news.google.com/rss/search?q="
        f"{quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
    )


@dataclass(frozen=True)
class FeedSource:
    vendor: str          # "Financial Times"
    section: str         # one of SECTIONS
    mode: str            # "native" | "gnews"
    url: str
    tier: str = "premium"    # "premium" (major outlet) | "independent" (specialist)


# --- Native section feeds (verified reachable July 2026) ---------------------
# FT format=rss on section pages; WSJ Dow Jones content feeds.
NATIVE = [
    # Financial Times
    FeedSource("Financial Times", "Business",   "native", "https://www.ft.com/companies?format=rss"),
    FeedSource("Financial Times", "Technology", "native", "https://www.ft.com/companies/technology?format=rss"),
    FeedSource("Financial Times", "World",      "native", "https://www.ft.com/world?format=rss"),

    # Wall Street Journal (Dow Jones content feeds)
    FeedSource("Wall Street Journal", "Business",   "native", "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness"),
    FeedSource("Wall Street Journal", "Technology", "native", "https://feeds.content.dowjones.io/public/rss/RSSWSJD"),
    FeedSource("Wall Street Journal", "World",      "native", "https://feeds.content.dowjones.io/public/rss/RSSWorldNews"),

    # The Economist (native section feeds; direct article links)
    FeedSource("The Economist", "Business",   "native", "https://www.economist.com/business/rss.xml"),
    FeedSource("The Economist", "Technology", "native", "https://www.economist.com/science-and-technology/rss.xml"),
    FeedSource("The Economist", "World",      "native", "https://www.economist.com/international/rss.xml"),
]

# --- Google News RSS fallbacks (no usable public/native feeds) ----------------
# Reuters dropped public RSS in 2020; Bloomberg's native feeds are flaky; and
# the Washington Post has gutted its feeds.washingtonpost.com output (most
# sections now return 0-4 items). All three route through Google News search,
# and gnews.py resolves the redirect links back to real source URLs.
GNEWS = [
    FeedSource("Reuters", "Business",   "gnews", gnews_url("reuters.com", "business")),
    FeedSource("Reuters", "Technology", "gnews", gnews_url("reuters.com", "technology")),
    FeedSource("Reuters", "World",      "gnews", gnews_url("reuters.com", "world")),

    FeedSource("Bloomberg", "Business",   "gnews", gnews_url("bloomberg.com", "markets business")),
    FeedSource("Bloomberg", "Technology", "gnews", gnews_url("bloomberg.com", "technology")),
    FeedSource("Bloomberg", "World",      "gnews", gnews_url("bloomberg.com", "world politics")),

    FeedSource("Washington Post", "Business",   "gnews", gnews_url("washingtonpost.com", "business economy markets")),
    FeedSource("Washington Post", "Technology", "gnews", gnews_url("washingtonpost.com", "technology")),
    FeedSource("Washington Post", "World",      "gnews", gnews_url("washingtonpost.com", "world")),
]

# --- Independent / specialist outlets (native RSS; direct links) -------------
# Smaller or specialized voices, shown as a separate tier from the majors.
# Skewed to the reader's tech/markets focus. Some (SemiAnalysis, the blogs)
# publish on a slower cadence, so they lean on vendor_max_age_hours overrides.
INDEPENDENT = [
    FeedSource("SemiAnalysis",   "Technology", "native", "https://www.semianalysis.com/feed", tier="independent"),
    FeedSource("Ars Technica",   "Technology", "native", "https://feeds.arstechnica.com/arstechnica/index", tier="independent"),
    FeedSource("Hacker News",    "Technology", "native", "https://hnrss.org/frontpage", tier="independent"),
    FeedSource("Calculated Risk", "Business",  "native", "https://www.calculatedriskblog.com/feeds/posts/default", tier="independent"),
    FeedSource("The Big Picture", "Business",  "native", "https://ritholtz.com/feed/", tier="independent"),
]

ALL_FEEDS: list[FeedSource] = NATIVE + GNEWS + INDEPENDENT


def feeds_for(vendors: list[str] | None = None,
              sections: list[str] | None = None) -> list[FeedSource]:
    """Filter the registry by vendor and/or section (both optional)."""
    out = ALL_FEEDS
    if vendors:
        vset = {v.lower() for v in vendors}
        out = [f for f in out if f.vendor.lower() in vset]
    if sections:
        sset = {s.lower() for s in sections}
        out = [f for f in out if f.section.lower() in sset]
    return out
