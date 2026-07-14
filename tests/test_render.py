"""HTML rendering: labels, badges, escaping, and file output."""
from datetime import datetime, timedelta, timezone

from newsagent.config import Config
from newsagent.models import Headline
from newsagent import render


def _h(**kw):
    base = dict(title="t", url="https://x", vendor="Reuters",
                section="World", published=None)
    base.update(kw)
    return Headline(**base)


def test_age_label_buckets():
    now = datetime.now(timezone.utc)
    assert render._age_label(_h(published=now - timedelta(minutes=30))).endswith("m ago")
    assert render._age_label(_h(published=now - timedelta(hours=5))) == "5h ago"
    assert render._age_label(_h(published=now - timedelta(days=2))) == "2d ago"
    assert render._age_label(_h(published=None)) == ""


def test_score_badge_class_thresholds():
    assert 'badge hi' in render._score_badge(_h(score=8))
    assert 'badge mid' in render._score_badge(_h(score=5))
    assert 'badge lo' in render._score_badge(_h(score=1))
    assert render._score_badge(_h(score=None)) == ""


def test_card_escapes_html_in_title():
    h = _h(title='Chips & <script>alert(1)</script> "war"', score=6)
    card = render._card(h)
    assert "<script>alert(1)</script>" not in card
    assert "&lt;script&gt;" in card and "&amp;" in card


def test_card_includes_alternates():
    h = _h(title="Story", score=7)
    h.alternates = [{"vendor": "Bloomberg", "url": "https://b/x"}]
    card = render._card(h)
    assert "also at" in card and "Bloomberg" in card and "https://b/x" in card


def test_render_html_writes_file(tmp_path):
    now = datetime.now(timezone.utc)
    hs = [_h(title="Nvidia chip", section="Technology", published=now, score=9),
          _h(title="Election result", section="World", published=now, score=4)]
    hs[0].alternates = [{"vendor": "WSJ", "url": "https://wsj/x"}]
    path = render.render_html(hs, Config(gemini_api_key=None), tmp_path)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Daily News Brief" in text
    assert "Nvidia chip" in text and "Election result" in text
    assert 'id="cut"' in text                  # relevance slider present
    assert "gemini-3.5-flash" in text          # footer names the model
