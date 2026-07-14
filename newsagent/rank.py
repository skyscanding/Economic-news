"""
Relevance / materiality ranking.

Two modes, same batched-JSON machinery:
  * PROFILE mode — score each story 0-10 against a prose interest profile.
  * PORTFOLIO mode — score each story for MATERIALITY to a holdings-based
    exposure graph, including second-order effects (supplier/customer/
    competitor/macro/regulatory), and attribute which holdings it affects.

Design decisions:
  * RANK, don't hard-filter. Every headline gets a score; the cutoff is applied
    at render/UI time.
  * BATCH the whole deduped list into ONE request.
  * PROVIDER-AGNOSTIC. The model name selects Gemini or DeepSeek (see providers).
  * FAIL OPEN. Any API/parse error -> keyword fallback so a page still renders.
"""
from __future__ import annotations
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

from .models import Headline
from .config import Config
from . import providers

log = logging.getLogger("newsagent.rank")

_TRANSIENT = ("429", "500", "502", "503", "504",
              "unavailable", "resource_exhausted", "overloaded", "timeout")


def _is_transient(err: Exception) -> bool:
    msg = str(err).lower()
    return any(tok in msg for tok in _TRANSIENT)


# --- Cheap keyword scorer (fallback + cross-check) ---------------------------
def keyword_score(h: Headline, interests: list[str]) -> tuple[float, list[str]]:
    text = f"{h.title} {h.summary}".lower()
    hits = [kw for kw in interests if kw.lower() in text]
    return (min(10.0, 2.0 * len(hits)), hits)


def _apply_keyword_scores(headlines: list[Headline], interests: list[str]) -> None:
    for h in headlines:
        score, hits = keyword_score(h, interests)
        h.keyword_hits = hits
        if h.score is None:          # only fill if LLM didn't
            h.score = score
            if hits:
                h.reason = "keyword match: " + ", ".join(hits[:4])


# --- Prompts -----------------------------------------------------------------
_SYSTEM_PROFILE = """You are a news relevance filter for a single reader.
Score each headline 0-10 for how much it matches the reader's interest profile.
10 = squarely on-profile and important; 0 = irrelevant.
Judge on the headline and summary only. Be decisive; spread scores across the
range rather than clustering everything at 5.
Return ONLY JSON (no prose, no fences):
{"scores":[{"id":<int>,"score":<int 0-10>,"reason":"<max 12 words>"}]}"""

_SYSTEM_PORTFOLIO = """You are a portfolio news analyst for a single investor.
Score each story 0-10 for MATERIALITY to the reader's portfolio below: how much
it could move the value of their positions, INCLUDING second-order effects. A
supplier, customer, competitor, sector, macro, or regulatory development that
affects a holding counts even if that holding is not named in the story.
Weight by position size — larger positions mean higher materiality.
10 = highly material to a large position; 0 = irrelevant to the book.

Attribution rules (be strict — attribution should be a signal, not noise):
- "ticker" MUST be one of the reader's actual holdings listed above. Never
  invent placeholders like "MACRO"; attribute macro impact to the specific
  holdings it most affects.
- "channel" MUST be exactly one of: direct, supplier, customer, competitor,
  macro, regulatory.
- List only the 1-3 MOST materially affected holdings, not every loose link.
- Use "macro" ONLY when the story plausibly moves the broad market or a key
  driver of the position (rates, a major geopolitical/energy shock, CPI). Do
  NOT tag routine company news as macro.
- If a story is not genuinely material to any holding, return an empty affects
  list and a low score.
Be decisive; spread scores widely.
Return ONLY JSON (no prose, no fences):
{"scores":[{"id":<int>,"score":<int 0-10>,"reason":"<max 14 words>",
"affects":[{"ticker":"NVDA","channel":"supplier"}]}]}"""


def _build_user_prompt(headlines: list[Headline], context: str) -> str:
    lines = [context, "", "HEADLINES:"]
    for i, h in enumerate(headlines):
        summary = (h.summary[:200] + "…") if len(h.summary) > 200 else h.summary
        lines.append(f'{i}. [{h.section}] {h.title} ({h.vendor})'
                     + (f" — {summary}" if summary else ""))
    lines.append("\nReturn the JSON now.")
    return "\n".join(lines)


def _salvage_objects(cleaned: str) -> list:
    """Extract complete {...} score objects from a truncated/malformed array.

    Walks the string tracking brace depth (string-aware) and collects every
    balanced top-level object inside the scores array. A response cut off
    mid-way still yields all the objects that completed before the cut.
    """
    start = cleaned.find("[")
    body = cleaned[start + 1:] if start != -1 else cleaned
    objs, depth, obj_start, instr, esc = [], 0, None, False, False
    for i, c in enumerate(body):
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
            continue
        if c == '"':
            instr = True
        elif c == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                objs.append(body[obj_start:i + 1])
                obj_start = None
    out = []
    for o in objs:
        try:
            out.append(json.loads(o))
        except json.JSONDecodeError:
            continue
    return out


def _parse_scores(raw: str) -> dict[int, dict]:
    """Parse the model's JSON. Accepts a bare array or {"scores":[...]}, and
    salvages complete objects from a truncated response rather than failing."""
    if not raw or not raw.strip():
        raise ValueError("empty response")
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            data = data.get("scores") or data.get("results") or []
    except json.JSONDecodeError:
        data = _salvage_objects(cleaned)      # truncated/malformed -> salvage
    out: dict[int, dict] = {}
    for row in data:
        try:
            affects = row.get("affects") or []
            affects = [{"ticker": str(a.get("ticker", "")).upper(),
                        "channel": str(a.get("channel", "")).lower()}
                       for a in affects if a.get("ticker")]
            out[int(row["id"])] = {
                "score": float(row["score"]),
                "reason": str(row.get("reason", "")).strip(),
                "affects": affects,
            }
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    return out


def classify_error(err: Exception | str) -> str:
    """Map an API error to a short, user-facing label for the UI reminder."""
    s = str(err).lower()
    if "429" in s or "resource_exhausted" in s or "quota" in s:
        return "rate limit (429)"
    if "503" in s or "unavailable" in s or "overloaded" in s:
        return "model overloaded (503)"
    if "404" in s or "not found" in s or "no longer available" in s:
        return "model not found (404)"
    if "401" in s or "403" in s or "permission" in s or "api key" in s:
        return "auth error (401/403)"
    if "timeout" in s or "timed out" in s:
        return "timeout"
    if any(t in s for t in ("expecting", "delimiter", "unterminated",
                            "json", "malformed")):
        return "malformed response"
    if any(t in s for t in ("empty response", "blocked", "safety",
                            "nonetype", "finish_reason")):
        return "empty/blocked response"
    return "error"


def _rank_with_llm(headlines: list[Headline], cfg: Config,
                   exposure: dict | None, report: dict) -> bool:
    """Score via the configured model. Fills `report`; returns True on success."""
    model = cfg.gemini_model
    report.update(provider=providers.provider_name(model), model=model,
                  mode="portfolio" if exposure else "profile",
                  total=len(headlines), scored=0, chunks=0, chunks_failed=0,
                  errors=[], fallback="none")

    if not providers.sdk_available(model):
        log.warning("SDK for %s not installed; using keyword fallback", model)
        report.update(fallback="full", errors=["SDK not installed"])
        return False
    key = providers.api_key_for(model, cfg)
    if not key:
        which = "DEEPSEEK_API_KEY" if providers.is_deepseek(model) else "GEMINI_API_KEY"
        log.warning("%s unset; using keyword fallback", which)
        report.update(fallback="full", errors=[f"{which} not set"])
        return False

    if exposure:
        from .portfolio import exposure_to_prompt
        system = _SYSTEM_PORTFOLIO
        context = exposure_to_prompt(exposure)
    else:
        system = _SYSTEM_PROFILE
        context = f"READER INTEREST PROFILE:\n{cfg.interest_profile}"

    # Split into chunks scored concurrently. This cuts wall-clock for large
    # batches and is resilient: one chunk failing only loses that chunk, and
    # its headlines fall through to keyword scoring instead of the whole run.
    size = max(1, cfg.rank_chunk_size)
    chunks = [(i, headlines[i:i + size]) for i in range(0, len(headlines), size)]

    def score_chunk(offset: int, chunk: list[Headline]):
        user = _build_user_prompt(chunk, context)   # ids are local (0..len-1)
        last = None
        for attempt in range(1, cfg.gemini_max_retries + 1):
            try:
                raw = providers.complete_json(model, system, user, key, temperature=0.2)
                return {offset + k: v for k, v in _parse_scores(raw).items()}, None
            except Exception as e:
                last = e
                if _is_transient(e) and attempt < cfg.gemini_max_retries:
                    time.sleep(2 ** attempt)
                    continue
                log.warning("%s chunk @%d failed (%s)",
                            providers.provider_name(model), offset, str(e)[:80])
                return {}, classify_error(e)
        return {}, classify_error(last)

    scores: dict[int, dict] = {}
    errors: list[str] = []
    workers = max(1, min(cfg.rank_workers, len(chunks)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part, err in pool.map(lambda c: score_chunk(*c), chunks):
            scores.update(part)
            if err:
                errors.append(err)

    report.update(chunks=len(chunks), chunks_failed=len(errors),
                  scored=len(scores), errors=sorted(set(errors)))

    if not scores:
        log.warning("model returned no usable scores; using keyword fallback")
        report["fallback"] = "full"
        return False

    report["fallback"] = "partial" if errors else "none"
    for i, h in enumerate(headlines):
        if i in scores:
            h.score = scores[i]["score"]
            h.reason = scores[i]["reason"]
            h.affects = scores[i]["affects"]
    log.info("%s (%s) scored %d/%d headlines across %d chunks (%d failed)",
             providers.provider_name(model), model, len(scores),
             len(headlines), len(chunks), len(errors))
    return True


def rank(headlines: list[Headline], cfg: Config, exposure: dict | None = None,
         report: dict | None = None) -> list[Headline]:
    """Score in place, then sort. Portfolio mode when `exposure` is given.

    If `report` is provided it is filled with a status summary (provider, model,
    scored/total, chunks_failed, errors, fallback) so callers can surface any
    API problems instead of silently degrading to keywords.
    """
    if report is None:
        report = {}
    if not headlines:
        report.update(total=0, scored=0, fallback="none", errors=[])
        return headlines

    used_llm = _rank_with_llm(headlines, cfg, exposure, report)
    _apply_keyword_scores(headlines, cfg.interest_keywords)  # always cross-check

    if not used_llm:
        log.info("ranked by keywords only")

    headlines.sort(key=lambda h: h.sort_key())
    return headlines
