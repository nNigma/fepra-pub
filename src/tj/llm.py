"""Единый LLM-клиент: Gemini (текст + зрение) + Claude CLI (зрение).
Без ключа/при ошибке -> None (фолбэк)."""
from __future__ import annotations

import base64
import fcntl
import json
import os
import shlex
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
    """Роутер зрения: engine="agent" — через внешний хелпер (opt-in), engine="claude" —
    Claude CLI по подписке, иначе Gemini API. При любом сбое верхнего движка —
    фолбэк на Gemini. claude_model: sonnet — доски (быстро), opus — еда."""
    if engine == "agent":
        try:
            out = agent_run(prompt, image_bytes=image_bytes, media_type=media_type,
                            model=claude_model)
            if out:
                return out
            print("[llm] agent не ответил, фолбэк на gemini", flush=True)
        except Exception as e:
            print(f"[llm] agent_vision упал ({type(e).__name__}: {e}), фолбэк на gemini", flush=True)
    elif engine == "claude":
        try:
            out = claude_vision(image_bytes, prompt, media_type=media_type,
                                model=claude_model)
            if out:
                return out
            print("[llm] claude_vision не ответил, фолбэк на gemini", flush=True)
        except Exception as e:
            print(f"[llm] claude_vision упал ({type(e).__name__}: {e}), фолбэк на gemini", flush=True)
    attempts = _attempts(paid=True, model=model)
    if not attempts:
        return None
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    contents = [{"role": "user", "parts": [
        {"inline_data": {"mime_type": media_type, "data": b64}},
        {"text": prompt},
    ]}]
    return _run(contents, attempts, max_output_tokens, 0.2, 90.0, "vision")


# --- Внешний инференс-хелпер (opt-in): зрение + текст ---------------------------
# Выключен, пока не задан FEPRA_AGENT_HELPER (путь к скрипту-обёртке) и
# FEPRA_LLM_ENGINE=agent. Хелпер получает файл промпта, файл картинки и имя модели,
# печатает JSON с текстом. FEPRA_AGENT_USER — запуск от имени другого пользователя
# (su), если сервис работает от root. Промпт идёт файлом: в argv не влезает и
# светился бы в ps.

_AGENT_MODELS = {"sonnet": "anthropic/claude-sonnet-5",
                 "opus": "anthropic/claude-opus-4-8"}


def _agent_helper() -> str | None:
    p = os.environ.get("FEPRA_AGENT_HELPER")
    return p if p and os.path.exists(p) else None


def has_agent() -> bool:
    return bool(_agent_helper())


def agent_run(prompt: str, *, image_bytes: bytes | None = None,
              media_type: str = "image/jpeg", model: str = "sonnet",
              timeout: float = 180.0) -> str | None:
    """Один ход модели через агента. Возвращает текст или None (тогда фолбэк)."""
    helper = _agent_helper()
    if not helper:
        return None
    full_model = _AGENT_MODELS.get(model, model)
    with tempfile.TemporaryDirectory(prefix="tj-agent-") as td:
        os.chmod(td, 0o755)
        pf = os.path.join(td, "prompt.txt")
        with open(pf, "w", encoding="utf-8") as f:
            f.write(prompt)
        os.chmod(pf, 0o644)
        img = ""
        if image_bytes:
            img = os.path.join(td, "image" + _CLAUDE_EXT.get(media_type, ".jpg"))
            with open(img, "wb") as f:
                f.write(image_bytes)
            os.chmod(img, 0o644)
        inner = " ".join(shlex.quote(x) for x in (helper, pf, img, full_model))
        run_as = os.environ.get("FEPRA_AGENT_USER")
        cmd = (["su", "-", run_as, "-c", inner] if run_as and os.geteuid() == 0
               else [helper, pf, img, full_model])
        t0 = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            print(f"[llm] agent rc={proc.returncode}: {proc.stderr.strip()[:160]}", flush=True)
            return None
        raw = proc.stdout.strip()
        if not raw.startswith("{"):
            # CLI иногда печатает диагностику перед JSON — берём с первой скобки
            i = raw.find("{")
            raw = raw[i:] if i >= 0 else raw
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print("[llm] agent вернул не JSON", flush=True)
            return None
        text = _agent_text(data)
        print(f"[llm] agent ok model={full_model} {time.time() - t0:.1f}s", flush=True)
        return text


def _agent_text(data: dict) -> str | None:
    """Достаёт текст из ответа `infer model run --json` в любом из форматов."""
    if not isinstance(data, dict) or data.get("ok") is False:
        return None
    outs = data.get("outputs")
    if isinstance(outs, list) and outs:
        first = outs[0]
        if isinstance(first, dict):
            for k in ("text", "content", "output"):
                if isinstance(first.get(k), str) and first[k].strip():
                    return first[k]
        elif isinstance(first, str) and first.strip():
            return first
    for k in ("text", "content", "output"):
        if isinstance(data.get(k), str) and data[k].strip():
            return data[k]
    return None


def subscription_complete(prompt: str, *, engine: str = "claude",
                         model: str = "sonnet", timeout: float = 150.0) -> str | None:
    """Текст по подписке: агент или Claude CLI. Любой сбой -> None, звонящий
    фолбэчит на Gemini. Исключения наружу не выпускаем: сбой инфраструктуры не
    должен выглядеть как отказ задачи."""
    try:
        if engine == "agent":
            return agent_run(prompt, model=model, timeout=timeout)
        if engine == "claude":
            return claude_complete(prompt, model=model, timeout=timeout)
    except Exception as e:
        print(f"[llm] subscription_complete упал ({type(e).__name__}: {e})", flush=True)
    return None


def has_text_llm() -> bool:
    """Есть ли хоть один движок для текстовых разборов (agent/claude/gemini)."""
    want = (os.environ.get("FEPRA_LLM_ENGINE") or "claude").strip().lower()
    if want == "agent" and has_agent():
        return True
    if has_claude_text():
        return True
    return has_llm()


def text_complete(prompt: str, *, timeout: float = 150.0,
                  gemini_system: str | None = None,
                  gemini_user: str | None = None,
                  max_output_tokens: int = 2200) -> tuple[str | None, str | None]:
    """Текстовый разбор: agent/claude по FEPRA_LLM_ENGINE, затем Gemini.
    -> (text | None, engine | None). gemini_system/user — отдельные части для
    Gemini-фолбэка (coach); без них уходит весь prompt одним user-сообщением."""
    want = (os.environ.get("FEPRA_LLM_ENGINE") or "claude").strip().lower()
    if want == "agent" and has_agent():
        text = subscription_complete(prompt, engine="agent", timeout=timeout)
        if text:
            return text, "agent"
    if has_claude_text():
        text = subscription_complete(prompt, engine="claude", timeout=timeout)
        if text:
            return text, "claude"
    if has_llm():
        if gemini_system is not None and gemini_user is not None:
            text = complete(gemini_system, gemini_user,
                            max_output_tokens=max_output_tokens, paid=True)
        else:
            text = complete("", prompt, max_output_tokens=max_output_tokens, paid=True)
        if text:
            return text, "gemini"
    return None, None


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
    from tj.config import claude_enabled
    return claude_enabled() and bool(_claude_bin())


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
    from tj.config import claude_enabled
    if not claude_enabled():
        return None
    if not _claude_bin():
        return None
    ext = _CLAUDE_EXT.get(media_type, ".jpg")
    full = f"{prompt}\n\nФото лежит рядом в файле board{ext} — прочитай его."
    with _claude_guard():
        with tempfile.TemporaryDirectory(prefix="tj-vision-") as td:
            with open(os.path.join(td, "board" + ext), "wb") as f:
                f.write(image_bytes)
            return _claude_run(full, td, timeout, "claude_vision", model=model)


def has_claude_text() -> bool:
    """Claude для текста: включён и есть CLI или ANTHROPIC_API_KEY."""
    from tj.config import claude_enabled
    return claude_enabled() and bool(_claude_bin() or _anthropic_key())


def _anthropic_key() -> str | None:
    from tj import config as cfgmod
    env = cfgmod.load_dotenv(cfgmod.default_env_path())
    return _pick_key(env, "ANTHROPIC_API_KEY")


def _anthropic_complete(prompt: str, *, timeout: float = 150.0,
                        max_tokens: int = 4096) -> str | None:
    """Текст через Anthropic Messages API (когда есть ключ, но нет CLI). Модель —
    ANTHROPIC_MODEL или дефолт. Любой сбой -> None (звонящий фолбэчит на Gemini)."""
    key = _anthropic_key()
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        print("[llm] anthropic SDK не установлен (pip install '.[claude]')", flush=True)
        return None
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
    try:
        client = anthropic.Anthropic(api_key=key, timeout=timeout)
        msg = client.messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(getattr(b, "text", "") for b in msg.content
                       if getattr(b, "type", None) == "text").strip()
        print(f"[llm] anthropic_api model={model} ok", flush=True)
        return text or None
    except Exception as e:
        print(f"[llm] anthropic_api error: {type(e).__name__}", flush=True)
        return None


def claude_complete(prompt: str, *, timeout: float = 150.0,
                    max_tokens: int = 4096, model: str = "sonnet") -> str | None:
    """Текстовая задача: CLI по подписке -> API-ключ -> None. cwd CLI = пустая
    временная папка (изоляция от CLAUDE.md). Сбой всех -> None, звонящий фолбэчит."""
    from tj.config import claude_enabled
    if not claude_enabled():
        return None
    if _claude_bin():
        with _claude_guard():
            with tempfile.TemporaryDirectory(prefix="tj-text-") as td:
                text = _claude_run(prompt, td, timeout, "claude_complete", model=model)
        if text:
            return text
    return _anthropic_complete(prompt, timeout=timeout, max_tokens=max_tokens)


def deep_complete(prompt: str, *, timeout: float = 300.0,
                  max_output_tokens: int = 2600) -> str | None:
    """Глубокий разбор движко-агностично: Claude (если включён и доступен) ->
    Gemini. claude_complete под гейтом сам вернёт None при выключенном Claude."""
    text = claude_complete(prompt, timeout=timeout, max_tokens=max_output_tokens)
    if text:
        return text
    return complete("", prompt, max_output_tokens=max_output_tokens)
