"""
Render the ranked headlines to one self-contained HTML file and open it.

No framework, no external assets: inline CSS + a tiny vanilla-JS score slider
so you can raise/lower the relevance cutoff without re-running the agent.
Headlines are the clickable links (open in a new tab); the article opens on
the source site, so you read full text yourself where you have access.
"""
from __future__ import annotations
import html
import logging
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from .models import Headline
from .feeds import SECTIONS

log = logging.getLogger("newsagent.render")


def _age_label(h: Headline) -> str:
    a = h.age_hours
    if a is None:
        return ""
    if a < 1:
        return f"{int(a * 60)}m ago"
    if a < 24:
        return f"{int(a)}h ago"
    return f"{int(a // 24)}d ago"


def _score_badge(h: Headline) -> str:
    if h.score is None:
        return ""
    s = round(h.score)
    cls = "hi" if s >= 7 else "mid" if s >= 4 else "lo"
    return f'<span class="badge {cls}">{s}</span>'


def _card(h: Headline) -> str:
    alts = ""
    if h.alternates:
        links = " · ".join(
            f'<a href="{html.escape(a["url"])}" target="_blank" rel="noopener">'
            f'{html.escape(a["vendor"])}</a>'
            for a in h.alternates
        )
        alts = f'<div class="alts">also at {links}</div>'
    reason = f'<div class="reason">{html.escape(h.reason)}</div>' if h.reason else ""
    meta = " · ".join(x for x in [html.escape(h.vendor), _age_label(h)] if x)
    score_attr = h.score if h.score is not None else 0
    return f"""
    <article class="card" data-score="{score_attr:.1f}">
      {_score_badge(h)}
      <a class="headline" href="{html.escape(h.url)}" target="_blank" rel="noopener">
        {html.escape(h.title)}
      </a>
      <div class="meta">{meta}</div>
      {reason}
      {alts}
    </article>"""


_CSS = """
:root{--bg:#0f1115;--card:#1a1d24;--fg:#e6e8eb;--mut:#8b90a0;--line:#282c36;
--hi:#2ea043;--mid:#b8860b;--lo:#484f5c;--link:#6ca0ff;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:#e6e8eb;
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
padding:16px 24px;z-index:5}
h1{margin:0 0 4px;font-size:18px}
.sub{color:var(--mut);font-size:13px}
.controls{margin-top:10px;display:flex;align-items:center;gap:10px;font-size:13px;color:var(--mut)}
.controls input{flex:0 0 180px}
main{max-width:820px;margin:0 auto;padding:24px}
section h2{font-size:14px;text-transform:uppercase;letter-spacing:.08em;
color:var(--mut);border-bottom:1px solid var(--line);padding-bottom:6px;margin:28px 0 12px}
.card{position:relative;background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:14px 16px 14px 52px;margin:10px 0}
.badge{position:absolute;left:14px;top:14px;width:26px;height:26px;border-radius:6px;
display:flex;align-items:center;justify-content:center;font-weight:600;font-size:13px;color:#fff}
.badge.hi{background:var(--hi)}.badge.mid{background:var(--mid)}.badge.lo{background:var(--lo)}
.headline{color:#e6e8eb;text-decoration:none;font-weight:600;font-size:15.5px}
.headline:hover{color:var(--link);text-decoration:underline}
.meta{color:var(--mut);font-size:12.5px;margin-top:5px}
.reason{color:#a6accb;font-size:12.5px;margin-top:6px;font-style:italic}
.alts{font-size:12px;margin-top:6px}.alts a{color:var(--link);text-decoration:none}
.empty{color:var(--mut);font-style:italic;padding:8px 0}
footer{max-width:820px;margin:0 auto;padding:8px 24px 40px;color:var(--mut);font-size:12px}
"""

_JS = """
const slider=document.getElementById('cut');
const out=document.getElementById('cutval');
function apply(){const v=parseFloat(slider.value);out.textContent=v.toFixed(0);
document.querySelectorAll('.card').forEach(c=>{
  c.style.display=parseFloat(c.dataset.score)>=v?'':'none';});
document.querySelectorAll('section').forEach(s=>{
  const any=[...s.querySelectorAll('.card')].some(c=>c.style.display!=='none');
  s.querySelector('.empty')?.style.setProperty('display',any?'none':'block');});}
slider.addEventListener('input',apply);apply();
"""


def render_html(headlines: list[Headline], cfg, out_dir: Path) -> Path:
    now = datetime.now(timezone.utc).astimezone()
    by_section: dict[str, list[Headline]] = {s: [] for s in SECTIONS}
    for h in headlines:
        by_section.setdefault(h.section, []).append(h)

    sections_html = []
    for sec in SECTIONS:
        items = by_section.get(sec, [])
        cards = "".join(_card(h) for h in items) or ""
        sections_html.append(
            f'<section><h2>{html.escape(sec)} '
            f'<span class="sub">({len(items)})</span></h2>'
            f'<div class="empty" style="display:none">Nothing above the cutoff.</div>'
            f'{cards}</section>'
        )

    vendors = sorted({h.vendor for h in headlines})
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily News — {now:%Y-%m-%d}</title><style>{_CSS}</style></head><body>
<header>
  <h1>Daily News Brief</h1>
  <div class="sub">{now:%A, %d %B %Y · %H:%M %Z} · {len(headlines)} stories · {", ".join(vendors)}</div>
  <div class="controls">
    <label for="cut">Min relevance</label>
    <input type="range" id="cut" min="0" max="10" step="1" value="0">
    <span id="cutval">0</span>
  </div>
</header>
<main>{"".join(sections_html)}</main>
<footer>Generated locally · headlines link to source sites · scored by {html.escape(cfg.gemini_model)} with keyword fallback</footer>
<script>{_JS}</script></body></html>"""

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"news_{now:%Y-%m-%d}.html"
    path.write_text(page, encoding="utf-8")
    log.info("wrote %s", path)
    return path


def open_in_browser(path: Path) -> None:
    try:
        webbrowser.open(path.resolve().as_uri())
    except Exception as e:
        log.warning("could not auto-open browser: %s", e)
