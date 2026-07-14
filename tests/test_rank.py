"""Ranking: keyword scorer, JSON parsing, and fail-open behavior."""
from newsagent.config import Config
from newsagent.models import Headline
from newsagent.rank import keyword_score, _parse_scores, rank


def _h(title, summary=""):
    return Headline(title, "https://x", "Reuters", "Technology", None, summary)


def test_keyword_score_counts_distinct_hits():
    score, hits = keyword_score(_h("Nvidia AI chip export control to China"),
                                ["nvidia", "ai", "chip", "export control",
                                 "china", "oil"])
    assert set(hits) == {"nvidia", "ai", "chip", "export control", "china"}
    assert score == 10.0                       # 5 hits * 2, capped at 10


def test_keyword_score_zero_when_no_match():
    score, hits = keyword_score(_h("Local bakery wins award"), ["ai", "chip"])
    assert score == 0.0 and hits == []


def test_parse_scores_plain_json():
    raw = '[{"id":0,"score":8,"reason":"on profile"},{"id":1,"score":2}]'
    out = _parse_scores(raw)
    assert out[0]["score"] == 8.0 and out[0]["reason"] == "on profile"
    assert out[1]["score"] == 2.0


def test_parse_scores_strips_markdown_fences():
    raw = '```json\n[{"id":0,"score":5,"reason":"x"}]\n```'
    out = _parse_scores(raw)
    assert out[0]["score"] == 5.0


def test_parse_scores_object_form_with_affects():
    # DeepSeek json_object mode returns an object, and portfolio mode adds affects.
    raw = ('{"scores":[{"id":0,"score":9,"reason":"supplier signal",'
           '"affects":[{"ticker":"nvda","channel":"Supplier"},'
           '{"ticker":"AMD","channel":"competitor"}]}]}')
    out = _parse_scores(raw)
    assert out[0]["score"] == 9.0
    assert out[0]["affects"][0] == {"ticker": "NVDA", "channel": "supplier"}
    assert out[0]["affects"][1]["ticker"] == "AMD"


def test_parse_scores_salvages_truncated_response():
    # A response cut off mid-stream: first two objects complete, third truncated.
    raw = ('{"scores":[{"id":0,"score":9,"reason":"a","affects":[{"ticker":"NVDA","channel":"supplier"}]},'
           '{"id":1,"score":4,"reason":"b"},'
           '{"id":2,"score":7,"reaso')   # <- truncated here
    out = _parse_scores(raw)
    assert set(out.keys()) == {0, 1}                 # salvaged the 2 complete ones
    assert out[0]["affects"][0]["ticker"] == "NVDA"
    assert out[1]["score"] == 4.0


def test_parse_scores_empty_raises():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        _parse_scores("")


def test_classify_error_response_shapes():
    from newsagent.rank import classify_error
    assert classify_error("Expecting ',' delimiter: line 1") == "malformed response"
    assert classify_error("empty response from Gemini") == "empty/blocked response"


def test_parse_scores_skips_malformed_rows():
    raw = '[{"id":0,"score":7},{"score":9},{"id":"bad","score":"x"}]'
    out = _parse_scores(raw)
    assert list(out.keys()) == [0]             # only the well-formed row survives


def test_rank_fails_open_to_keywords_without_api_key():
    cfg = Config(gemini_api_key=None,
                 interest_keywords=["chip", "nvidia"])
    hs = [_h("Nvidia chip news"), _h("Celebrity gossip")]
    ranked = rank(hs, cfg)
    # Keyword scorer ran; on-profile item sorts first.
    assert ranked[0].title == "Nvidia chip news"
    assert ranked[0].score == 4.0             # 2 hits * 2
    assert ranked[1].score == 0.0


def test_rank_empty_input():
    assert rank([], Config(gemini_api_key=None)) == []


def test_classify_error_labels():
    from newsagent.rank import classify_error
    assert classify_error("429 RESOURCE_EXHAUSTED quota") == "rate limit (429)"
    assert classify_error("503 UNAVAILABLE overloaded") == "model overloaded (503)"
    assert classify_error("404 model not found") == "model not found (404)"
    assert classify_error("read timed out") == "timeout"


def test_rank_report_full_fallback_without_key():
    report = {}
    rank([_h("Nvidia chip")], Config(gemini_api_key=None), report=report)
    assert report["fallback"] == "full"
    assert any("GEMINI_API_KEY" in e for e in report["errors"])


def test_rank_report_partial_fallback(monkeypatch):
    import re, json as _json
    from newsagent import providers

    def fake(model, system, user, key, **kw):
        if "FAILME" in user:
            raise RuntimeError("503 UNAVAILABLE")
        ids = [int(m) for m in re.findall(r'^(\d+)\.', user, re.M)]
        return _json.dumps({"scores": [{"id": i, "score": 5, "reason": "x"} for i in ids]})

    monkeypatch.setattr(providers, "complete_json", fake)
    cfg = Config(gemini_api_key="x", rank_chunk_size=1, rank_workers=4)
    report = {}
    rank([_h("good"), _h("FAILME"), _h("good2")], cfg, report=report)
    assert report["fallback"] == "partial"
    assert report["chunks_failed"] == 1
    assert "model overloaded (503)" in report["errors"]


def test_rank_chunked_scores_all_headlines(monkeypatch):
    """Parallel chunking: every headline is scored across multiple chunks."""
    import re, json as _json
    from newsagent import providers

    def fake(model, system, user, key, **kw):
        ids = [int(m) for m in re.findall(r'^(\d+)\.', user, re.M)]
        return _json.dumps({"scores": [{"id": i, "score": 7, "reason": "x"} for i in ids]})

    monkeypatch.setattr(providers, "complete_json", fake)
    cfg = Config(gemini_api_key="x", rank_chunk_size=2, rank_workers=3)
    hs = [_h(f"Story number {i}") for i in range(5)]     # -> 3 chunks
    ranked = rank(hs, cfg)
    assert all(h.score == 7.0 for h in ranked)


def test_rank_chunk_failure_is_isolated(monkeypatch):
    """One failing chunk doesn't sink the run; its items fall back to keywords."""
    import re, json as _json
    from newsagent import providers

    def fake(model, system, user, key, **kw):
        if "FAILME" in user:
            raise RuntimeError("boom")                   # non-transient -> no retry
        ids = [int(m) for m in re.findall(r'^(\d+)\.', user, re.M)]
        return _json.dumps({"scores": [{"id": i, "score": 7, "reason": "x"} for i in ids]})

    monkeypatch.setattr(providers, "complete_json", fake)
    cfg = Config(gemini_api_key="x", rank_chunk_size=1, rank_workers=4,
                 interest_keywords=["zzz"])
    hs = [_h("good one"), _h("FAILME headline"), _h("good three")]
    ranked = rank(hs, cfg)
    assert sum(1 for h in ranked if h.score == 7.0) == 2   # two good chunks scored
    failed = [h for h in ranked if h.title == "FAILME headline"][0]
    assert failed.score != 7.0                              # keyword fallback, not LLM


def test_rank_portfolio_mode_uses_exposure_and_populates_affects(monkeypatch):
    """Portfolio mode: exposure graph -> materiality prompt -> affects on cards.
    Mocks the provider so no quota/network is used."""
    from newsagent import providers
    canned = ('{"scores":[{"id":0,"score":9,"reason":"supplier signal",'
              '"affects":[{"ticker":"NVDA","channel":"supplier"}]},'
              '{"id":1,"score":1,"reason":"n/a","affects":[]}]}')
    captured = {}

    def fake_complete(model, system, user, key, **kw):
        captured["system"] = system
        captured["user"] = user
        return canned

    monkeypatch.setattr(providers, "complete_json", fake_complete)
    cfg = Config(gemini_api_key="x")           # key present -> attempts LLM
    hs = [_h("TSMC raises 2026 capex on AI demand"), _h("Local fair opens")]
    exposure = {"NVDA": {"kind": "seed", "weight": 1.0,
                         "direct": ["Nvidia"], "suppliers": ["TSMC"]}}
    ranked = rank(hs, cfg, exposure=exposure)

    assert "MATERIALITY" in captured["system"]          # portfolio prompt used
    assert "NVDA" in captured["user"] and "TSMC" in captured["user"]  # exposure sent
    top = ranked[0]
    assert top.score == 9.0
    assert top.affects == [{"ticker": "NVDA", "channel": "supplier"}]
