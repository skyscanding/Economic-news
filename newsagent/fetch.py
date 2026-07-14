"""
Fetch + normalize.

Each feed is fetched independently and wrapped in try/except so one dead
feed never kills the run. Google News wraps article URLs in a redirect and
appends " - Publisher" to titles; we unwrap/clean both here so downstream
steps see uniform records.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

import feedparser
import httpx

from .feeds import FeedSource
from .models import Headline

log = logging.getLogger("newsagent.fetch")

# A real UA reduces the chance of being served an error page.
_UA = "Mozilla/5.0 (compatible; NewsAgent/1.0; +local)"
_TIMEOUT = 15.0


def _to_utc(struct_time) -> datetime | None:
    if not struct_time:
        return None
    try:
        return datetime(*struct_time[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _clean_gnews_title(title: str, vendor: str) -> str:
    # Google News appends " - Reuters" etc. Strip a trailing " - <vendor>".
    suffix = f" - {vendor}"
    if title.endswith(suffix):
        return title[: -len(suffix)].strip()
    # Also handle a generic trailing " - Publisher" pattern.
    if " - " in title:
        head, _, tail = title.rpartition(" - ")
        if len(tail) < 40 and head:
            return head.strip()
    return title.strip()


def _unwrap_gnews_url(link: str) -> str:
    # Google News links look like news.google.com/rss/articles/...?url=<real>
    try:
        parsed = urlparse(link)
        if "news.google.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "url" in qs and qs["url"]:
                return qs["url"][0]
    except Exception:
        pass
    return link


def _fetch_raw(url: str) -> bytes | None:
    try:
        with httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _UA},
                          follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception as e:  # network, HTTP, timeout
        log.warning("fetch failed for %s: %s", url, e)
        return None


def fetch_feed(source: FeedSource, limit: int = 40) -> list[Headline]:
    """Fetch and normalize one feed. Returns [] on any failure."""
    raw = _fetch_raw(source.url)
    if raw is None:
        return []

    parsed = feedparser.parse(raw)
    if parsed.bozo and not parsed.entries:
        log.warning("unparseable feed (%s / %s): %s",
                    source.vendor, source.section, parsed.bozo_exception)
        return []

    out: list[Headline] = []
    for entry in parsed.entries[:limit]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        if source.mode == "gnews":
            title = _clean_gnews_title(title, source.vendor)
            link = _unwrap_gnews_url(link)

        published = _to_utc(entry.get("published_parsed")) \
            or _to_utc(entry.get("updated_parsed"))
        summary = entry.get("summary", "").strip()

        out.append(Headline(
            title=title, url=link, vendor=source.vendor,
            section=source.section, published=published, summary=summary,
        ))

    log.info("%-18s %-11s -> %d items", source.vendor, source.section, len(out))
    return out


def fetch_all(sources: list[FeedSource], limit: int = 40) -> list[Headline]:
    headlines: list[Headline] = []
    failures: list[FeedSource] = []
    for src in sources:
        items = fetch_feed(src, limit=limit)
        if not items:
            failures.append(src)
        headlines.extend(items)
    if failures:
        log.warning("%d feed(s) returned nothing: %s", len(failures),
                    ", ".join(f"{f.vendor}/{f.section}" for f in failures))
    return headlines
