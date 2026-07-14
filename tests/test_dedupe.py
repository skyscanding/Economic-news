"""Cross-vendor deduplication."""
from datetime import datetime, timezone

from newsagent.dedupe import _norm, deduplicate
from newsagent.models import Headline


def _h(title, vendor="Reuters", when=None):
    return Headline(title, f"https://x/{vendor}", vendor, "World", when)


def test_norm_strips_vendor_suffix_and_punctuation():
    assert _norm("TSMC beats estimates - Reuters") == "tsmc beats estimates"
    assert _norm("Fed holds rates | Bloomberg") == "fed holds rates"
    assert _norm("A.I. chips, surging!") == "a i chips surging"


def test_deduplicate_clusters_near_identical_titles():
    now = datetime.now(timezone.utc)
    hs = [
        _h("TSMC raises full-year revenue forecast", "Reuters", now),
        _h("TSMC raises its full year revenue forecast", "Bloomberg", now),
        _h("Fed signals one more rate cut in 2026", "WSJ", now),
    ]
    out = deduplicate(hs, threshold=85)
    assert len(out) == 2                      # the two TSMC items merged
    tsmc = [h for h in out if "TSMC" in h.title][0]
    assert len(tsmc.alternates) == 1
    assert tsmc.alternates[0]["vendor"] in {"Reuters", "Bloomberg"}


def test_representative_prefers_timestamped_and_longer_title():
    now = datetime.now(timezone.utc)
    short_no_time = _h("TSMC lifts forecast", "Reuters", None)
    long_timed = _h("TSMC lifts full-year revenue forecast again", "WSJ", now)
    out = deduplicate([short_no_time, long_timed], threshold=80)
    assert len(out) == 1
    assert out[0].vendor == "WSJ"             # timestamped + longer title wins


def test_unrelated_titles_are_not_merged():
    out = deduplicate([_h("Oil prices climb"), _h("Nvidia unveils new GPU")], 85)
    assert len(out) == 2
