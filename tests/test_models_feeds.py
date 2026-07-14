"""Data model + feed registry."""
from datetime import datetime, timedelta, timezone

import pytest

from newsagent.models import Headline
from newsagent import feeds


def test_age_hours_none_when_no_timestamp():
    assert Headline("t", "u", "v", "World", None).age_hours is None


def test_age_hours_roughly_correct():
    published = datetime.now(timezone.utc) - timedelta(hours=5)
    h = Headline("t", "u", "v", "World", published)
    assert 4.9 < h.age_hours < 5.1


def test_sort_key_orders_by_score_then_recency():
    now = datetime.now(timezone.utc)
    older = Headline("a", "u", "v", "World", now - timedelta(hours=3))
    newer = Headline("b", "u", "v", "World", now)
    older.score, newer.score = 9.0, 9.0
    assert sorted([older, newer], key=lambda h: h.sort_key())[0] is newer
    # Higher score beats recency.
    low_new = Headline("c", "u", "v", "World", now); low_new.score = 3.0
    hi_old = Headline("d", "u", "v", "World", now - timedelta(hours=9)); hi_old.score = 8.0
    assert sorted([low_new, hi_old], key=lambda h: h.sort_key())[0] is hi_old


def test_gnews_url_is_scoped_and_encoded():
    url = feeds.gnews_url("reuters.com", "business")
    assert "site%3Areuters.com" in url and "when%3A1d" in url
    assert url.startswith("https://news.google.com/rss/search?q=")


def test_feeds_for_filters_by_vendor_and_section():
    only_reuters = feeds.feeds_for(vendors=["Reuters"])
    assert {f.vendor for f in only_reuters} == {"Reuters"}

    tech = feeds.feeds_for(sections=["Technology"])
    assert {f.section for f in tech} == {"Technology"}

    both = feeds.feeds_for(vendors=["Bloomberg"], sections=["World"])
    assert len(both) == 1 and both[0].vendor == "Bloomberg"


def test_feeds_for_is_case_insensitive():
    assert feeds.feeds_for(vendors=["reuters"]) == feeds.feeds_for(vendors=["Reuters"])


def test_filter_age_applies_per_vendor_override():
    from newsagent.main import _filter_age
    from newsagent.config import Config
    now = datetime.now(timezone.utc)
    cfg = Config(gemini_api_key=None)          # default override: Economist 336h
    reuters = Headline("r", "u", "Reuters", "World", now - timedelta(hours=100))
    econ = Headline("e", "u", "The Economist", "World", now - timedelta(hours=100))
    kept = _filter_age([reuters, econ], cfg)
    assert econ in kept                        # 100h < 336h window -> kept
    assert reuters not in kept                 # 100h > 36h default -> dropped


def test_premium_grid_is_complete_and_independents_present():
    premium = [f for f in feeds.ALL_FEEDS if f.tier == "premium"]
    # 6 premium vendors x 3 sections = 18, one per cell.
    assert len(premium) == 18
    assert len({(f.vendor, f.section) for f in premium}) == 18
    assert "The Economist" in {f.vendor for f in premium}
    # Independents are a partial, specialist set tagged distinctly.
    indep = [f for f in feeds.ALL_FEEDS if f.tier == "independent"]
    assert len(indep) >= 3
    assert "SemiAnalysis" in {f.vendor for f in indep}
    assert {f.tier for f in feeds.ALL_FEEDS} == {"premium", "independent"}
