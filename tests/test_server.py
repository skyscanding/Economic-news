"""Web front end: JSON serialization + live API endpoints (no news fetch)."""
import json
import threading
import urllib.request
from datetime import datetime, timezone

import pytest

from newsagent.models import Headline
from newsagent import server
from newsagent.webapp import PAGE


def test_headline_to_dict_is_json_serializable():
    h = Headline("T", "https://x", "Reuters", "World",
                 datetime.now(timezone.utc), "sum")
    h.score, h.reason = 8.0, "why"
    h.keyword_hits = ["nvidia"]
    h.alternates = [{"vendor": "WSJ", "url": "https://y"}]
    d = h.to_dict()
    json.dumps(d)                              # must not raise
    assert d["score"] == 8.0 and d["keyword_hits"] == ["nvidia"]
    assert d["published"] is not None and d["age_hours"] is not None


def test_page_is_self_contained_html():
    assert PAGE.lstrip().startswith("<!DOCTYPE html>")
    assert "/api/refresh" in PAGE and "/api/news" in PAGE
    assert "<script" in PAGE                   # inline JS, no external assets
    assert "http://" not in PAGE.split("<script")[0] or "cdn" not in PAGE.lower()


@pytest.fixture
def live_server():
    """Start the real server on an ephemeral port; no network fetch triggered."""
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server._Handler)
    port = httpd.socket.getsockname()[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read()


def test_index_served(live_server):
    status, body = _get(live_server + "/")
    assert status == 200 and b"News Agent" in body


def test_api_config(live_server):
    status, body = _get(live_server + "/api/config")
    data = json.loads(body)
    assert status == 200
    assert "Reuters" in data["vendors"] and "Technology" in data["sections"]
    assert "model" in data and "key_present" in data


def test_api_status_idle(live_server):
    status, body = _get(live_server + "/api/status")
    data = json.loads(body)
    assert status == 200 and data["running"] is False
    assert "notice" in data


def test_should_autostop_logic():
    # never beat -> stay up (headless run); recent beat -> stay up; stale -> stop.
    assert server._should_autostop(None, 100.0, 12.0) is False
    assert server._should_autostop(100.0, 105.0, 12.0) is False
    assert server._should_autostop(100.0, 120.0, 12.0) is True


def test_heartbeat_endpoint_records_beat(live_server):
    server._HEARTBEAT["last"] = None
    req = urllib.request.Request(live_server + "/api/heartbeat", data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        assert json.loads(r.read())["ok"] is True
    assert server._HEARTBEAT["last"] is not None      # beat recorded


def test_build_notice_levels():
    assert server._build_notice({"fallback": "none"}) is None
    full = server._build_notice(
        {"fallback": "full", "errors": ["rate limit (429)"], "total": 100, "model": "m"})
    assert full["level"] == "error" and "keyword fallback" in full["text"]
    partial = server._build_notice(
        {"fallback": "partial", "errors": ["model overloaded (503)"],
         "chunks_failed": 2, "chunks": 5, "scored": 240, "total": 300, "model": "m"})
    assert partial["level"] == "warn" and "2 of 5" in partial["text"]
