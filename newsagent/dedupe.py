"""
Cross-vendor deduplication.

The same story (e.g. a DeepSeek chip report) appears across every outlet.
We cluster near-identical titles and keep one representative per cluster,
attaching the others as `alternates` so the UI can show "also at Bloomberg".

Matching is token-set based (order-independent, tolerant of extra words)
via rapidfuzz. Daily volume is small (~100-300 items) so naive O(n^2)
comparison is fine.
"""
from __future__ import annotations
import logging
import re

from rapidfuzz import fuzz

from .models import Headline

log = logging.getLogger("newsagent.dedupe")

_STOP_SUFFIXES = re.compile(
    r"\s*[-|–—]\s*(reuters|bloomberg|financial times|ft|wsj|"
    r"wall street journal|washington post)\s*$",
    re.IGNORECASE,
)


def _norm(title: str) -> str:
    t = _STOP_SUFFIXES.sub("", title)
    t = t.lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _pick_representative(cluster: list[Headline]) -> Headline:
    # Prefer a native-vendor item with a real timestamp and the longest title.
    def rank(h: Headline) -> tuple:
        has_time = 1 if h.published else 0
        return (has_time, len(h.title))
    return max(cluster, key=rank)


def deduplicate(headlines: list[Headline], threshold: int = 85) -> list[Headline]:
    """Return one Headline per story cluster, with alternates attached."""
    clusters: list[list[Headline]] = []
    norms: list[str] = []

    for h in headlines:
        n = _norm(h.title)
        placed = False
        for i, existing in enumerate(norms):
            if fuzz.token_set_ratio(n, existing) >= threshold:
                clusters[i].append(h)
                placed = True
                break
        if not placed:
            clusters.append([h])
            norms.append(n)

    result: list[Headline] = []
    for cluster in clusters:
        rep = _pick_representative(cluster)
        for other in cluster:
            if other is rep:
                continue
            rep.alternates.append({"vendor": other.vendor, "url": other.url})
        result.append(rep)

    log.info("deduplicated %d -> %d (%d clusters merged)",
             len(headlines), len(result),
             len(headlines) - len(result))
    return result
