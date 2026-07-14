"""
LLM provider abstraction for ranking + portfolio reasoning.

One entry point, `complete_json`, takes a model name and returns the model's
text response (expected to be JSON). The provider is inferred from the model
name so the rest of the app never branches on it:

    deepseek-*  -> DeepSeek  (OpenAI-compatible endpoint, via httpx; no new dep)
    everything  -> Gemini    (google-genai SDK)

DeepSeek V4 (`deepseek-v4-pro`, `deepseek-v4-flash`) is served behind an
OpenAI-compatible API at https://api.deepseek.com — cheap and strong at
financial/quant reasoning, which is why it's a first-class option here.
"""
from __future__ import annotations
import logging

log = logging.getLogger("newsagent.providers")

_DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def is_deepseek(model: str) -> bool:
    return (model or "").lower().startswith("deepseek")


def provider_name(model: str) -> str:
    return "deepseek" if is_deepseek(model) else "gemini"


def api_key_for(model: str, cfg) -> str | None:
    """Which configured key a given model needs."""
    return cfg.deepseek_api_key if is_deepseek(model) else cfg.gemini_api_key


def sdk_available(model: str) -> bool:
    if is_deepseek(model):
        try:
            import httpx  # noqa: F401
            return True
        except ImportError:
            return False
    try:
        import google.genai  # noqa: F401
        return True
    except ImportError:
        return False


def complete_json(model: str, system: str, user: str, api_key: str,
                  temperature: float = 0.2, timeout: float = 90.0) -> str:
    """Run one completion and return the raw text (JSON). Raises on failure."""
    if is_deepseek(model):
        return _deepseek(model, system, user, api_key, temperature, timeout)
    return _gemini(model, system, user, api_key, temperature, timeout)


def _deepseek(model, system, user, api_key, temperature, timeout) -> str:
    import httpx
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    resp = httpx.post(
        _DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json=payload, timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _gemini(model, system, user, api_key, temperature, timeout) -> str:
    from google import genai
    from google.genai import types
    # Bound the request so a network stall can't hang the run (timeout in ms).
    client = genai.Client(api_key=api_key,
                          http_options=types.HttpOptions(timeout=int(timeout * 1000)))
    resp = client.models.generate_content(
        model=model, contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=temperature,
            max_output_tokens=16384,   # headroom so a big chunk isn't truncated
        ),
    )
    text = resp.text
    if not text:
        # No text = safety block or truncation with no usable partial content.
        raise RuntimeError("empty response from Gemini (safety block or truncation)")
    return text
