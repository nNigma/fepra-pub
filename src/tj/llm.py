"""Единый клиент Gemini (текст + зрение). Без ключа/при ошибке -> None (фолбэк)."""
from __future__ import annotations

import base64
import os
import time

import httpx

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_RETRY_STATUS = {429, 500, 502, 503, 504}


def _post_json(url: str, body: dict, timeout: float, kind: str) -> dict | None:
    """POST в Gemini с мягкими ретраями по транзиентным ошибкам. Ключ в логи не попадает."""
    for attempt in range(3):
        try:
            resp = httpx.post(url, json=body, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code in _RETRY_STATUS and attempt < 2:
                print(f"[llm] {kind} http {code}, повтор {attempt + 1}/2", flush=True)
                time.sleep(1.5 * (attempt + 1))
                continue
            print(f"[llm] {kind} http {code}", flush=True)
            return None
        except Exception as e:
            print(f"[llm] {kind} error: {type(e).__name__}", flush=True)
            return None
    return None


def _pick_key(env: dict, *names: str) -> str | None:
    for n in names:
        v = os.environ.get(n) or env.get(n)
        if v:
            return v
    return None


def gemini_key(paid: bool = False) -> str | None:
    """paid=True → платный ключ (GEMINI_COST_API_KEY, для распознавания фото);
    иначе бесплатный (GEMINI_API_KEY, для текстового разбора). Каждый с фолбэком на другой."""
    from tj import config as cfgmod
    env = cfgmod.load_dotenv(cfgmod.default_env_path())
    if paid:
        return _pick_key(env, "GEMINI_COST_API_KEY", "GEMINI_API_KEY")
    return _pick_key(env, "GEMINI_API_KEY", "GEMINI_COST_API_KEY")


def _model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def has_llm() -> bool:
    return bool(gemini_key(paid=True) or gemini_key())


def _log_usage(kind: str, data: dict) -> None:
    u = data.get("usageMetadata") or {}
    print(f"[llm] {kind} tokens in={u.get('promptTokenCount')} out={u.get('candidatesTokenCount')}",
          flush=True)


def _extract_text(data: dict) -> str | None:
    cands = data.get("candidates") or []
    if not cands:
        return None
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    return text or None


def complete(system: str, user: str, *, max_output_tokens: int = 800, model: str | None = None,
             paid: bool = False) -> str | None:
    key = gemini_key(paid=paid)
    if not key:
        return None
    url = _ENDPOINT.format(model=model or _model()) + f"?key={key}"
    body = {
        "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
        "generationConfig": {"maxOutputTokens": max_output_tokens, "temperature": 0.7,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    data = _post_json(url, body, 30.0, "complete")
    if data is None:
        return None
    _log_usage("complete", data)
    return _extract_text(data)


def vision(image_bytes: bytes, prompt: str, *, media_type: str = "image/jpeg",
           max_output_tokens: int = 1200, model: str | None = None) -> str | None:
    key = gemini_key(paid=True)
    if not key:
        return None
    url = _ENDPOINT.format(model=model or _model()) + f"?key={key}"
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    body = {
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": media_type, "data": b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {"maxOutputTokens": max_output_tokens, "temperature": 0.2,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    data = _post_json(url, body, 60.0, "vision")
    if data is None:
        return None
    _log_usage("vision", data)
    return _extract_text(data)
