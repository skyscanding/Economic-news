"""Portfolio parsing + exposure graph (offline: no LLM enrichment)."""
from newsagent import portfolio
from newsagent.config import Config


def test_parse_portfolio_weights_normalize():
    p = portfolio.parse_portfolio("NVDA 20%, TSM 15%, ASML 10%")
    tickers = {i["ticker"]: i["weight"] for i in p}
    assert set(tickers) == {"NVDA", "TSM", "ASML"}
    assert abs(sum(tickers.values()) - 1.0) < 0.01      # normalized (4dp rounding)
    assert tickers["NVDA"] > tickers["TSM"] > tickers["ASML"]


def test_parse_portfolio_bare_tickers_equal_weight():
    p = portfolio.parse_portfolio("NVDA, TSM, ASML")
    weights = [i["weight"] for i in p]
    assert abs(sum(weights) - 1.0) < 0.01
    assert max(weights) - min(weights) < 1e-6           # roughly equal


def test_parse_portfolio_various_separators():
    p = portfolio.parse_portfolio("NVDA=20\nTSM 15\nMU:5")
    assert {i["ticker"] for i in p} == {"NVDA", "TSM", "MU"}


def test_build_exposure_graph_uses_seed_offline():
    cfg = Config(gemini_api_key=None, deepseek_api_key=None)  # no enrichment
    graph = portfolio.build_exposure_graph(
        [{"ticker": "NVDA", "weight": 0.6}, {"ticker": "TSM", "weight": 0.4}], cfg)
    assert graph["NVDA"]["kind"] == "seed"
    assert "TSMC" in graph["NVDA"]["suppliers"]          # second-order link
    assert graph["NVDA"]["weight"] == 0.6


def test_build_exposure_graph_index_is_macro():
    cfg = Config(gemini_api_key=None, deepseek_api_key=None)
    graph = portfolio.build_exposure_graph([{"ticker": "SPY", "weight": 1.0}], cfg)
    assert graph["SPY"]["kind"] == "index"
    assert not graph["SPY"]["direct"]                    # no single-name exposure
    assert any("Fed" in m or "rate" in m for m in graph["SPY"]["macro"])


def test_build_exposure_graph_unknown_offline_direct_only(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio, "_CACHE", tmp_path / "exp.json")
    cfg = Config(gemini_api_key=None, deepseek_api_key=None)
    graph = portfolio.build_exposure_graph([{"ticker": "ZZZZ", "weight": 1.0}], cfg)
    assert graph["ZZZZ"]["kind"] == "unknown"
    assert graph["ZZZZ"]["direct"] == ["ZZZZ"]


def test_exposure_to_prompt_mentions_holdings_and_weights():
    cfg = Config(gemini_api_key=None, deepseek_api_key=None)
    graph = portfolio.build_exposure_graph([{"ticker": "NVDA", "weight": 0.5}], cfg)
    text = portfolio.exposure_to_prompt(graph)
    assert "NVDA" in text and "50% of book" in text
    assert "TSMC" in text                                # supplier surfaced to LLM
