"""Единый LLM-клиент: Gemini (текст + зрение) + Claude CLI (зрение).
Без ключа/при ошибке -> None (фолбэк)."""
from __future__ import annotations

import base64
import fcntl
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager

import httpx

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Транзиентные коды Gemini (перегрузка/лимит РPM) — по ним есть смысл повторить.
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
    """paid=True → платный ключ (GEMINI_COST_API_KEY); иначе бесплатный
    (GEMINI_API_KEY). Каждый с фолбэком на другой."""
    from tj import config as cfgmod
    env = cfgmod.load_dotenv(cfgmod.default_env_path())
    if paid:
        return _pick_key(env, "GEMINI_COST_API_KEY", "GEMINI_API_KEY")
    return _pick_key(env, "GEMINI_API_KEY", "GEMINI_COST_API_KEY")


_FREE_MODEL = "gemini-2.5-flash"


def _attempts(paid: bool = True, model: str | None = None) -> list[tuple[str, str]]:
    """Список попыток (ключ, модель) по порядку. Платный ключ — на основной
    модели; бесплатный фолбэк — на flash (бесплатный тариф не тянет pro)."""
    from tj import config as cfgmod
    env = cfgmod.load_dotenv(cfgmod.default_env_path())
    cost = _pick_key(env, "GEMINI_COST_API_KEY")
    free = _pick_key(env, "GEMINI_API_KEY")
    cost_pair = (cost, model or _model()) if cost else None
    free_pair = (free, _FREE_MODEL) if free else None
    order = [cost_pair, free_pair] if paid else [free_pair, cost_pair]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for p in order:
        if p and p[0] not in seen:
            seen.add(p[0])
            out.append(p)
    return out


def _model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _gen_config(model: str, max_output_tokens: int, temperature: float) -> dict:
    if "flash" in model:
        return {"maxOutputTokens": max_output_tokens, "temperature": temperature,
                "thinkingConfig": {"thinkingBudget": 0}}
    return {"maxOutputTokens": max_output_tokens + 6144, "temperature": temperature,
            "thinkingConfig": {"thinkingBudget": 2048}}


def has_llm() -> bool:
    return bool(_attempts(paid=True))


def _log_usage(kind: str, data: dict) -> None:
    u = data.get("usageMetadata") or {}
    fin = ((data.get("candidates") or [{}])[0] or {}).get("finishReason")
    tail = f" finish={fin} (ОТВЕТ ОБРЕЗАН)" if fin and fin != "STOP" else ""
    print(f"[llm] {kind} tokens in={u.get('promptTokenCount')} "
          f"out={u.get('candidatesTokenCount')}{tail}", flush=True)


def _extract_text(data: dict) -> str | None:
    cands = data.get("candidates") or []
    if not cands:
        return None
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    return text or None


def _run(contents: list, attempts: list, max_output_tokens: int,
         temperature: float, timeout: float, kind: str) -> str | None:
    for i, (key, model) in enumerate(attempts):
        body = {"contents": contents,
                "generationConfig": _gen_config(model, max_output_tokens, temperature)}
        data = _post_json(_ENDPOINT.format(model=model) + f"?key={key}", body, timeout, kind)
        if data is not None:
            _log_usage(kind, data)
            return _extract_text(data)
        if i + 1 < len(attempts):
            print(f"[llm] {kind}: попытка #{i + 1} ({model}) не удалась, пробую запасной", flush=True)
    return None


def complete(system: str, user: str, *, max_output_tokens: int = 800, model: str | None = None,
             paid: bool = False) -> str | None:
    attempts = _attempts(paid, model)
    if not attempts:
        return None
    contents = [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}]
    return _run(contents, attempts, max_output_tokens, 0.7, 60.0, "complete")


def vision(image_bytes: bytes, prompt: str, *, media_type: str = "image/jpeg",
           max_output_tokens: int = 1200, model: str | None = None,
           engine: str = "gemini", claude_model: str = "sonnet") -> str | None:
    """Роутер зрения: engine="claude" — Claude CLI по подписке (фолбэк на Gemini
    при любом сбое), иначе Gemini API. claude_model: sonnet — доски (быстро),
    opus — еда (лучше счёт объектов и классификация)."""
    if engine == "claude":
        out = claude_vision(image_bytes, prompt, media_type=media_type,
                            model=claude_model)
        if out:
            return out
        print("[llm] claude_vision не ответил, фолбэк на gemini", flush=True)
    attempts = _attempts(paid=True, model=model)
    if not attempts:
        return None
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    contents = [{"role": "user", "parts": [
        {"inline_data": {"mime_type": media_type, "data": b64}},
        {"text": prompt},
    ]}]
    return _run(contents, attempts, max_output_tokens, 0.2, 90.0, "vision")


# --- Claude CLI (headless `claude -p`): зрение + текст --------------------------
# Своя подписка Claude на сервере: фикс-цена вместо API-счётчика. Только для
# admin-контента (программа зала) — развилка по ролям живёт в хендлерах.

# Сервер маленький: два node-процесса параллельно — OOM-лотерея. threading.Lock
# сериализует внутри процесса, flock — между процессами (бот и крон-скрипты).
_CLAUDE_THREAD_LOCK = threading.Lock()

_CLAUDE_EXT = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def _claude_bin() -> str | None:
    return os.environ.get("CLAUDE_BIN") or shutil.which("claude")


def has_claude_vision() -> bool:
    return bool(_claude_bin())


def _claude_lock_path() -> str:
    return os.environ.get("CLAUDE_LOCK_FILE",
                          os.path.join(tempfile.gettempdir(), "tj-claude.lock"))


@contextmanager
def _claude_guard():
    with _CLAUDE_THREAD_LOCK:
        with open(_claude_lock_path(), "w") as lockf:
            fcntl.flock(lockf, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lockf, fcntl.LOCK_UN)


def _claude_run(prompt: str, cwd: str, timeout: float, kind: str,
                model: str = "sonnet") -> str | None:
    """Один вызов `claude -p` с разбором JSON-конверта. Любой сбой -> None."""
    cmd = [_claude_bin(), "-p", prompt, "--output-format", "json",
           "--allowedTools", "Read", "--model", model]
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[llm] {kind} rc=timeout", flush=True)
        return None
    except Exception as e:
        print(f"[llm] {kind} error: {type(e).__name__}", flush=True)
        return None
    if proc.returncode != 0:
        err = " ".join((proc.stderr or "").split())[:300]
        print(f"[llm] {kind} rc={proc.returncode} stderr={err}", flush=True)
        return None
    try:
        env = json.loads(proc.stdout)
    except ValueError:
        print(f"[llm] {kind} rc=0, битый JSON-конверт", flush=True)
        return None
    if env.get("is_error"):
        print(f"[llm] {kind} is_error=true", flush=True)
        return None
    usage = env.get("usage") or {}
    print(f"[llm] {kind} tokens in={usage.get('input_tokens')} "
          f"out={usage.get('output_tokens')}", flush=True)
    text = (env.get("result") or "").strip()
    return text or None


def claude_vision(image_bytes: bytes, prompt: str, *, media_type: str = "image/jpeg",
                  timeout: float = 150.0, model: str = "sonnet") -> str | None:
    """Фото -> текст через `claude -p` (--output-format json, только Read).
    cwd = временная папка с одним фото: CLI не видит ничего лишнего и не
    подхватывает CLAUDE.md. Любой сбой (нет бинаря, протух login, таймаут,
    битый конверт) -> None, роутер уйдёт в Gemini."""
    if not _claude_bin():
        return None
    ext = _CLAUDE_EXT.get(media_type, ".jpg")
    full = f"{prompt}\n\nФото лежит рядом в файле board{ext} — прочитай его."
    with _claude_guard():
        with tempfile.TemporaryDirectory(prefix="tj-vision-") as td:
            with open(os.path.join(td, "board" + ext), "wb") as f:
                f.write(image_bytes)
            return _claude_run(full, td, timeout, "claude_vision", model=model)


def claude_complete(prompt: str, *, timeout: float = 150.0) -> str | None:
    """Текстовая задача через `claude -p` (без фото). cwd = пустая временная
    папка (изоляция от CLAUDE.md и файлов). Сбой -> None, звонящий фолбэчит."""
    if not _claude_bin():
        return None
    with _claude_guard():
        with tempfile.TemporaryDirectory(prefix="tj-text-") as td:
            return _claude_run(prompt, td, timeout, "claude_complete")
