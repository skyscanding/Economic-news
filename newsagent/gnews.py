"""
Resolve Google News RSS redirect links to their real source URLs.

Google News RSS wraps every article in a `news.google.com/rss/articles/CBMi...`
link whose real destination is protobuf-encoded and is NO LONGER exposed as a
`?url=` query param (Google removed that years ago). Recovering the source URL
needs a two-step handshake against Google's internal batchexecute endpoint:

  1. GET the article page to read a per-article signature + timestamp
     (`data-n-a-sg` / `data-n-a-ts` attributes).
  2. POST those to `/_/DotsSplashUi/data/batchexecute`, which returns the URL.

Design decisions (mirroring the rest of the pipeline):
  * FAIL OPEN. Any article we can't resolve keeps its original Google link,
    which still works if clicked in a browser. One dead decode never breaks a run.
  * CONCURRENT. Resolving is I/O-bound (2 requests each); a small thread pool
    turns minutes into seconds for a few hundred links.
  * CACHED. Successful decodes are memoized on disk keyed by the stable article
    id, so a second run the same day re-hits nothing. Failures are NOT cached,
    so they get retried next run.

Reuters and Bloomberg come entirely through Google News, so without this every
link from those two vendors would dead-end on a Google interstitial.
"""
from __future__ import annotations
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from .models import Headline

log = logging.getLogger("newsagent.gnews")

_UA = "Mozilla/5.0 (compatible; NewsAgent/1.0; +local)"
_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_SIG_RE = re.compile(r'data-n-a-sg="([^"]+)"')
_TS_RE = re.compile(r'data-n-a-ts="([^"]+)"')


def is_gnews_url(url: str) -> bool:
    try:
        return urlparse(url).netloc.endswith("news.google.com")
    except Exception:
        return False


def article_id(url: str) -> str | None:
    """Extract the CBMi... article id from a Google News articles/read link."""
    try:
        parts = urlparse(url).path.strip("/").split("/")
    except Exception:
        return None
    if len(parts) >= 2 and parts[-2] in ("articles", "read") and parts[-1]:
        return parts[-1]
    return None


def _build_payload(art_id: str, ts: int, sig: str) -> str:
    """Build the f.req form body for a single-article garturlreq call."""
    inner = [
        "garturlreq",
        [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
          None, None, None, None, None, 0, 1],
         "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
        art_id, ts, sig,
    ]
    req = [[["Fbv4je", json.dumps(inner), None, "generic"]]]
    return "f.req=" + quote(json.dumps(req))


def parse_batch_response(text: str) -> str | None:
    """Pull the decoded URL out of a batchexecute response body.

    The body is Google's anti-JSON-hijack format: a `)]}'` guard, then
    newline-delimited chunks. The Fbv4je chunk holds a JSON string whose
    second element is the real article URL. Returns None if not present.
    """
    for chunk in text.split("\n\n"):
        chunk = chunk.strip()
        if "Fbv4je" not in chunk and "garturlres" not in chunk:
            continue
        try:
            arr = json.loads(chunk)
            for row in arr:
                if isinstance(row, list) and len(row) > 2 and row[1] == "Fbv4je":
                    payload = json.loads(row[2])
                    if isinstance(payload, list) and len(payload) > 1:
                        url = payload[1]
                        if isinstance(url, str) and url.startswith("http"):
                            return url
        except (json.JSONDecodeError, TypeError, IndexError):
            continue
    return None


def _decode_one(client: httpx.Client, art_id: str) -> str | None:
    """Resolve one article id to its source URL. Returns None on any failure."""
    try:
        page = client.get(f"https://news.google.com/rss/articles/{art_id}")
        page.raise_for_status()
        sig = _SIG_RE.search(page.text)
        ts = _TS_RE.search(page.text)
        if not (sig and ts):
            return None
        body = _build_payload(art_id, int(ts.group(1)), sig.group(1))
        resp = client.post(
            _BATCH_URL,
            headers={"content-type":
                     "application/x-www-form-urlencoded;charset=UTF-8"},
            content=body,
        )
        resp.raise_for_status()
        return parse_batch_response(resp.text)
    except Exception as e:  # network, HTTP, parse — all non-fatal
        log.debug("decode failed for %s: %s", art_id, e)
        return None


def _decode_many(art_ids: list[str], workers: int, timeout: float) -> dict[str, str]:
    out: dict[str, str] = {}
    with httpx.Client(timeout=timeout, headers={"User-Agent": _UA},
                      follow_redirects=True) as client:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for aid, url in zip(art_ids,
                                pool.map(lambda a: _decode_one(client, a), art_ids)):
                if url:
                    out[aid] = url
    return out


def _load_cache(path: Path | None) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(path: Path | None, cache: dict[str, str]) -> None:
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=0), encoding="utf-8")
    except Exception as e:
        log.debug("could not write gnews cache: %s", e)


def resolve_links(headlines: list[Headline], workers: int = 8,
                  cache_path: Path | None = None, timeout: float = 20.0) -> int:
    """Rewrite Google News links (and alternates) to real source URLs in place.

    Returns the number of representative headlines that were resolved.
    """
    # Collect every distinct gnews article id across headlines + alternates.
    ids: dict[str, str] = {}       # art_id -> original gnews url (for logging)

    def note(url: str) -> None:
        if is_gnews_url(url):
            aid = article_id(url)
            if aid:
                ids[aid] = url

    for h in headlines:
        note(h.url)
        for a in h.alternates:
            note(a.get("url", ""))

    if not ids:
        return 0

    cache = _load_cache(cache_path)
    todo = [aid for aid in ids if aid not in cache]
    log.info("resolving google-news links: %d to fetch, %d cached",
             len(todo), len(ids) - len(todo))

    if todo:
        cache.update(_decode_many(todo, workers=workers, timeout=timeout))
        _save_cache(cache_path, cache)

    def swap(url: str) -> str:
        aid = article_id(url) if is_gnews_url(url) else None
        return cache.get(aid, url) if aid else url

    resolved = 0
    for h in headlines:
        new = swap(h.url)
        if new != h.url:
            h.url = new
            resolved += 1
        for a in h.alternates:
            a["url"] = swap(a.get("url", ""))

    unresolved = len(ids) - sum(1 for aid in ids if aid in cache)
    log.info("resolved %d/%d google-news links (%d still redirect)",
             len(ids) - unresolved, len(ids), unresolved)
    return resolved
