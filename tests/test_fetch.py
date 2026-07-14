"""Fetch-layer normalization helpers (title cleaning, URL unwrap, dates)."""
import time
from datetime import timezone

from newsagent import fetch


def test_clean_gnews_title_strips_trailing_vendor():
    assert fetch._clean_gnews_title(
        "TSMC beats estimates - Reuters", "Reuters") == "TSMC beats estimates"
    # Generic short publisher suffix.
    assert fetch._clean_gnews_title(
        "Fed holds rates - Some Blog", "Reuters") == "Fed holds rates"
    # No suffix: returned unchanged (trimmed).
    assert fetch._clean_gnews_title("  Plain title  ", "Reuters") == "Plain title"


def test_unwrap_gnews_url_legacy_param():
    # Old-style links exposed the real URL as ?url=; still honored if present.
    wrapped = "https://news.google.com/rss/articles/X?url=https%3A%2F%2Fr.com%2Fa&hl=en"
    assert fetch._unwrap_gnews_url(wrapped) == "https://r.com/a"
    # Modern links have no ?url= — returned as-is for the resolver to handle.
    modern = "https://news.google.com/rss/articles/CBMiABC?oc=5"
    assert fetch._unwrap_gnews_url(modern) == modern
    # Non-gnews URL untouched.
    assert fetch._unwrap_gnews_url("https://r.com/a") == "https://r.com/a"


def test_to_utc_from_struct_time():
    st = time.struct_time((2026, 7, 13, 8, 30, 0, 0, 0, 0))
    dt = fetch._to_utc(st)
    assert dt is not None
    assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 7, 13, 8)
    assert dt.tzinfo == timezone.utc


def test_to_utc_handles_missing():
    assert fetch._to_utc(None) is None
