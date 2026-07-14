"""Google News link resolution — pure logic, no network.

The network handshake (_decode_one) is exercised indirectly: its response
parsing is factored into parse_batch_response, which we drive with a canned
body that mirrors Google's real batchexecute format.
"""
import json

from newsagent import gnews
from newsagent.models import Headline


def test_is_gnews_url():
    assert gnews.is_gnews_url("https://news.google.com/rss/articles/CBMiXXX")
    assert gnews.is_gnews_url("https://news.google.com/read/CBMiXXX")
    assert not gnews.is_gnews_url("https://www.reuters.com/tech/foo")
    assert not gnews.is_gnews_url("")
    assert not gnews.is_gnews_url("not a url")


def test_article_id_extraction():
    assert gnews.article_id(
        "https://news.google.com/rss/articles/CBMiABC123?oc=5") == "CBMiABC123"
    assert gnews.article_id(
        "https://news.google.com/read/CBMiXYZ") == "CBMiXYZ"
    # Non-article gnews URLs and foreign URLs yield nothing.
    assert gnews.article_id("https://news.google.com/rss/search?q=x") is None
    assert gnews.article_id("https://www.reuters.com/tech/foo") is None


def _canned_body(url: str) -> str:
    """Reproduce Google's )]}' + newline-delimited batchexecute envelope."""
    inner = json.dumps(["garturlres", url])
    chunk = json.dumps([["wrb.fr", "Fbv4je", inner, None, None, None, "generic"]])
    trailer = json.dumps([["e", 4, None, None, 131]])
    return ")]}'\n\n" + chunk + "\n\n26\n" + trailer


def test_parse_batch_response_extracts_url():
    url = "https://www.reuters.com/world/asia/tsmc-2026-07-13/"
    assert gnews.parse_batch_response(_canned_body(url)) == url


def test_parse_batch_response_missing_returns_none():
    body = ")]}'\n\n" + json.dumps([["di", 22], ["af.httprm", 21, "x", 30]])
    assert gnews.parse_batch_response(body) is None
    assert gnews.parse_batch_response("garbage") is None
    assert gnews.parse_batch_response("") is None


def test_build_payload_is_valid_form_body():
    body = gnews._build_payload("CBMiABC", 1710000000, "SIG123")
    assert body.startswith("f.req=")
    # The percent-encoded JSON must round-trip and carry our id/sig.
    from urllib.parse import unquote
    decoded = json.loads(unquote(body[len("f.req="):]))
    flat = json.dumps(decoded)
    assert "CBMiABC" in flat and "SIG123" in flat and "Fbv4je" in flat


def test_resolve_links_no_gnews_is_noop():
    hs = [Headline("Foo", "https://www.reuters.com/a", "Reuters", "World", None)]
    assert gnews.resolve_links(hs, cache_path=None) == 0
    assert hs[0].url == "https://www.reuters.com/a"


def test_resolve_links_uses_cache_without_network(tmp_path):
    """A pre-populated cache lets resolve_links run fully offline."""
    aid = "CBMiCACHED"
    gurl = f"https://news.google.com/rss/articles/{aid}?oc=5"
    real = "https://www.bloomberg.com/news/real-article"
    cache = tmp_path / "gnews.json"
    cache.write_text(json.dumps({aid: real}), encoding="utf-8")

    h = Headline("Story", gurl, "Bloomberg", "Technology", None)
    h.alternates = [{"vendor": "Reuters", "url": gurl}]

    resolved = gnews.resolve_links([h], cache_path=cache)
    assert resolved == 1
    assert h.url == real
    assert h.alternates[0]["url"] == real
