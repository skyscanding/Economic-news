"""
Local web front end for the news agent.

A tiny stdlib HTTP server (no Flask/extra deps) that serves an interactive
single-page app and a small JSON API. Because it's served from http://localhost
the page's JavaScript can call the backend directly — something a file:// page
cannot do — so you can re-fetch, change sources, set the key/model, and re-rank
entirely from the browser window.

Endpoints:
  GET  /              -> the single-page app (HTML/CSS/JS, self-contained)
  GET  /api/config    -> available vendors/sections, current model, key status
  GET  /api/status    -> current job state (phase/progress/error)
  GET  /api/news      -> the most recent ranked headlines as JSON
  POST /api/refresh   -> start a fetch+rank job (body: vendors, sections, key, model)

Bound to 127.0.0.1 only — it exposes an endpoint that accepts an API key, so it
must never listen on a public interface.
"""
from __future__ import annotations
import json
import logging
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import Config
from .feeds import feeds_for, SECTIONS, ALL_FEEDS
from .fetch import fetch_all
from .dedupe import deduplicate
from .gnews import resolve_links
from .main import _filter_age
from .portfolio import parse_portfolio, build_exposure_graph
from . import providers
from .rank import rank
from .webapp import PAGE

log = logging.getLogger("newsagent.server")

ALL_VENDORS = sorted({f.vendor for f in ALL_FEEDS})
_CACHE = Path.cwd() / "output" / ".gnews_cache.json"

# Curated model suggestions for the front end's picker (verified available on
# AI Studio keys, newest first). Users can still type any model name.
SUGGESTED_MODELS = [
    "gemini-3.5-flash",        # default: fast, current
    "gemini-3-pro-preview",    # strongest Gemini reasoning
    "gemini-flash-latest",     # always-newest alias
    "deepseek-v4-flash",       # DeepSeek: cheap, strong quant/financial reasoning
    "deepseek-v4-pro",         # DeepSeek: strongest reasoning
    "gemini-2.5-flash-lite",   # cheapest Gemini
]

VENDOR_TIER = {f.vendor: f.tier for f in ALL_FEEDS}

# Recommended one-click filter chips (distinct tokens; no redundant ticker/name
# pairs). Clicking one drops it into the search box on the front end.
SUGGESTED_FILTERS = [
    "nvidia", "amd", "intel", "tsmc", "asml", "micron", "qualcomm",
    "apple", "microsoft", "google", "amazon", "tesla", "palantir", "spacex",
    "chip", "semiconductor", "data center", "export control",
    "fed", "earnings", "s&p 500", "nasdaq",
]

# --- Shared job state (guarded by a lock) ------------------------------------
_LOCK = threading.Lock()
_JOB = {
    "running": False,
    "phase": "idle",
    "error": None,
    "generated": None,     # ISO timestamp of last successful run
    "headlines": [],       # list[dict] from Headline.to_dict()
    "notice": None,        # {level, text} when ranking hit API problems
}


def _build_notice(report: dict) -> dict | None:
    """Turn a rank() report into a UI reminder, or None when all went well."""
    fb = report.get("fallback", "none")
    if fb == "none":
        return None
    errs = report.get("errors", [])
    model = report.get("model", "")
    total = report.get("total", 0)
    detail = (" — " + ", ".join(errs)) if errs else ""
    if fb == "full":
        return {"level": "error",
                "text": (f"AI ranking unavailable{detail}. All {total} stories "
                         f"scored by keyword fallback (less accurate). Model: {model}.")}
    failed = report.get("chunks_failed", 0)
    chunks = report.get("chunks", 0)
    scored = report.get("scored", 0)
    return {"level": "warn",
            "text": (f"{failed} of {chunks} scoring batches failed{detail}; those "
                     f"stories used keyword fallback ({scored}/{total} AI-scored "
                     f"by {model}).")}


def _set(**kw) -> None:
    with _LOCK:
        _JOB.update(kw)


# --- Auto-shutdown: stop the server when the browser tab(s) close ------------
# The page sends a heartbeat every few seconds. A watchdog shuts the server down
# once heartbeats stop for `timeout` seconds. It only arms AFTER the first beat,
# so a headless run (no browser) stays up, and it survives reloads / multiple
# tabs (any open tab keeps it alive).
_HEARTBEAT = {"last": None}


def _record_beat() -> None:
    with _LOCK:
        _HEARTBEAT["last"] = time.monotonic()


def _should_autostop(last: float | None, now: float, timeout: float) -> bool:
    return last is not None and (now - last) > timeout


def _start_watchdog(httpd, timeout: float) -> None:
    def loop():
        while True:
            time.sleep(3)
            with _LOCK:
                last = _HEARTBEAT["last"]
            if _should_autostop(last, time.monotonic(), timeout):
                log.info("browser closed (no heartbeat for %.0fs); shutting down",
                         timeout)
                httpd.shutdown()
                return
    threading.Thread(target=loop, daemon=True).start()


def _snapshot() -> dict:
    with _LOCK:
        return dict(_JOB)


def _run_pipeline(vendors, sections, portfolio) -> None:
    """Run fetch -> dedupe -> resolve -> rank, updating _JOB['phase'] as we go."""
    try:
        cfg = Config.load()
        sources = feeds_for(vendors=vendors or None, sections=sections or None)
        _set(phase=f"fetching {len(sources)} feeds")
        headlines = fetch_all(sources, limit=cfg.per_feed_limit)

        headlines = _filter_age(headlines, cfg)
        _set(phase=f"deduplicating {len(headlines)} headlines")
        headlines = deduplicate(headlines, threshold=cfg.dedupe_threshold)

        if cfg.resolve_gnews:
            _set(phase="resolving source links")
            resolve_links(headlines, workers=cfg.gnews_workers, cache_path=_CACHE)

        exposure = None
        if portfolio:
            _set(phase=f"mapping {len(portfolio)} holdings to exposure graph")
            exposure = build_exposure_graph(portfolio, cfg)

        has_key = bool(providers.api_key_for(cfg.gemini_model, cfg))
        mode = (providers.provider_name(cfg.gemini_model) if has_key else "keywords")
        scope = "portfolio materiality" if exposure else "relevance"
        _set(phase=f"ranking {len(headlines)} stories by {scope} ({mode})")
        report: dict = {}
        headlines = rank(headlines, cfg, exposure=exposure, report=report)
        notice = _build_notice(report)

        from datetime import datetime, timezone
        _set(running=False, phase="done", error=None, notice=notice,
             generated=datetime.now(timezone.utc).astimezone().isoformat(),
             headlines=[h.to_dict() for h in headlines])
        log.info("web refresh complete: %d stories (%s)",
                 len(headlines), "portfolio" if exposure else "profile")
    except Exception as e:                    # never let the job thread die silently
        log.exception("refresh failed")
        _set(running=False, phase="error", error=str(e))


def _start_job(vendors, sections, key, model, portfolio) -> bool:
    with _LOCK:
        if _JOB["running"]:
            return False
        _JOB.update(running=True, phase="starting", error=None, notice=None)
    # Apply per-request model override, then route the key to the right provider.
    if model:
        os.environ["GEMINI_MODEL"] = model
    if key:
        if providers.is_deepseek(model or os.environ.get("GEMINI_MODEL", "")):
            os.environ["DEEPSEEK_API_KEY"] = key
        else:
            os.environ["GEMINI_API_KEY"] = key
    threading.Thread(target=_run_pipeline, args=(vendors, sections, portfolio),
                     daemon=True).start()
    return True


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):             # quiet the default per-request noise
        return

    def _send(self, code, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/config":
            cfg = Config.load()
            models = list(dict.fromkeys([cfg.gemini_model] + SUGGESTED_MODELS))
            self._json({
                "vendors": ALL_VENDORS,
                "sections": list(SECTIONS),
                "model": cfg.gemini_model,
                "models": models,
                "vendor_tiers": VENDOR_TIER,         # {vendor: premium|independent}
                "key_present": bool(cfg.gemini_api_key),
                "deepseek_key_present": bool(cfg.deepseek_api_key),
                "filters": SUGGESTED_FILTERS,        # quick-filter chips
            })
        elif self.path == "/api/status":
            s = _snapshot()
            self._json({"running": s["running"], "phase": s["phase"],
                        "error": s["error"], "generated": s["generated"],
                        "notice": s["notice"], "count": len(s["headlines"])})
        elif self.path == "/api/news":
            s = _snapshot()
            self._json({"generated": s["generated"], "notice": s["notice"],
                        "headlines": s["headlines"]})
        else:
            self._json({"error": "not found"}, code=404)

    def do_POST(self):
        if self.path == "/api/heartbeat":
            _record_beat()
            self._json({"ok": True})
            return
        if self.path != "/api/refresh":
            self._json({"error": "not found"}, code=404)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or "{}")
        except json.JSONDecodeError:
            body = {}
        # Portfolio may arrive as a text string ("NVDA 20%, TSM 15%") or a list.
        pf = body.get("portfolio")
        if isinstance(pf, str):
            portfolio = parse_portfolio(pf)
        elif isinstance(pf, list):
            portfolio = pf
        else:
            portfolio = None
        started = _start_job(
            vendors=body.get("vendors") or None,
            sections=body.get("sections") or None,
            key=(body.get("key") or "").strip(),
            model=(body.get("model") or "").strip(),
            portfolio=portfolio,
        )
        self._json({"started": started,
                    "error": None if started else "a refresh is already running"})


def serve(host="127.0.0.1", port=8765, open_browser=True,
          autostop=True, heartbeat_timeout=12.0) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-18s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S")
    httpd = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}/"
    log.info("serving news agent front end at %s", url)
    if autostop:
        _start_watchdog(httpd, heartbeat_timeout)
        log.info("auto-stop enabled: server exits ~%.0fs after the last tab closes",
                 heartbeat_timeout)
    if open_browser:
        _open_in_chrome_or_edge(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
        httpd.shutdown()
    log.info("server stopped")


def _open_in_chrome_or_edge(url: str) -> None:
    """Open the URL preferring Chrome, then Edge, then the default browser."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for exe in candidates:
        if Path(exe).exists():
            try:
                webbrowser.register("_pref", None,
                                    webbrowser.BackgroundBrowser(exe))
                webbrowser.get("_pref").open(url)
                return
            except Exception:
                break
    webbrowser.open(url)


def main():
    port = int(os.environ.get("NEWSAGENT_PORT", "8765"))
    # Auto-stop when the browser closes; disable with NEWSAGENT_NO_AUTOSTOP=1.
    autostop = os.environ.get("NEWSAGENT_NO_AUTOSTOP", "") != "1"
    serve(port=port, autostop=autostop)


if __name__ == "__main__":
    main()
