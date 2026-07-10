# Публичная «Кузница»: синхронизация + тумблер Claude/Gemini — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Догнать публичный `rgb/pub/kuznitsa` до актуального `gen_n/training-journal` без приватных данных и сделать Claude опциональным (`config.toml [llm] use_claude`, дефолт false): есть Claude — как сейчас, нет — всё через Gemini.

**Architecture:** Гейт ставится в одной точке — `tj/llm.py`. Резолвер `tj.config.claude_enabled()` читает `config.toml`/env. При выключенном Claude `claude_complete`/`claude_vision`/`has_claude_vision` короткозамыкают на None/False, и вся цепочка потребителей уходит в Gemini через уже существующие фолбэки. Новый `llm.deep_complete()` делает глубокие разборы движко-агностичными. Добавляется бэкенд Claude через `ANTHROPIC_API_KEY` (только текст).

**Tech Stack:** Python 3.12, pytest, python-telegram-bot, FastAPI, Gemini REST, Claude CLI (`claude -p`), Anthropic SDK (опционально), uv.

**Спека:** [docs/superpowers/specs/2026-07-10-pub-sync-claude-toggle-design.md](../specs/2026-07-10-pub-sync-claude-toggle-design.md)

**Пути (якорь — `~/REDACTED/rr`, без хардкода `/Users/...`):**
- `GEN=~/REDACTED/rr/rgb/gen_n/training-journal`
- `PUB=~/REDACTED/rr/rgb/pub/kuznitsa`

Тесты в `PUB`: `cd $PUB && PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:randomly -q`

---

## Структура файлов

**Фаза A — синхронизация (механическая):**
- `PUB/src/**` ← снимок `GEN/src/**` (весь код + статика), минус мусор.
- `PUB/tests/**` ← снимок `GEN/tests/**`.
- Удалить закоммиченный мусор: `PUB/src/**/__pycache__`, `PUB/src/training_journal.egg-info`, все `.DS_Store`.

**Фаза B — ядро тумблера:**
- Modify `PUB/src/tj/config.py` — `claude_enabled()` + `reset_claude_cache()`.
- Modify `PUB/src/tj/llm.py` — гейт в `claude_complete`/`claude_vision`/`has_claude_vision`; `_anthropic_complete()` (API-бэкенд, текст); `deep_complete()`.
- Test `PUB/tests/test_claude_toggle.py` — резолвер, гейт, API-бэкенд, deep_complete.

**Фаза C — потребители:**
- Modify `PUB/src/tjbot/vision.py` — `engine_for()` под гейтом.
- Modify `PUB/src/tjbot/handlers/record_workout.py` — при выключенном Claude шаг выбора движка пропускается (рефактор парса в хелпер).
- Modify `PUB/src/tjbot/handlers/club.py` — то же для `club`-флоу.
- Modify `PUB/src/tjbot/claude_review.py` — `_ask` через `deep_complete`; `run_all` не аборт при выключенном Claude.

**Фаза D — упаковка/доки:**
- Modify `PUB/pyproject.toml` — `anthropic` из `bot` в новый extra `[claude]`.
- Modify `PUB/config.example.toml`, `PUB/.env.example`, `PUB/README.md`, `PUB/deploy/README.md`.
- Modify `PUB/.gitignore` — мусор.

---

## Фаза A — Синхронизация кода

### Task A1: Снять снимок src и tests из gen_n в pub

**Files:**
- Sync: `PUB/src/` ← `GEN/src/`; `PUB/tests/` ← `GEN/tests/`

- [ ] **Step 1: Синхронизировать `src/` (с удалением лишнего, без мусора)**

```bash
GEN=~/REDACTED/rr/rgb/gen_n/training-journal
PUB=~/REDACTED/rr/rgb/pub/kuznitsa
rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
  --exclude '*.egg-info' \
  "$GEN/src/" "$PUB/src/"
```

- [ ] **Step 2: Синхронизировать `tests/`**

```bash
rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
  "$GEN/tests/" "$PUB/tests/"
```

- [ ] **Step 3: Добить остатки мусора в pub (если что-то было вне src/tests)**

```bash
cd "$PUB"
find . -name '__pycache__' -type d -prune -exec rm -rf {} +
find . -name '.DS_Store' -delete
rm -rf src/training_journal.egg-info
```

- [ ] **Step 4: Проверить, что новые модули доехали**

Run:
```bash
cd "$PUB" && ls src/tj/analysis/{coach,muscles,nutrition,nutrition_goals,watch_advice}.py \
  src/tjbot/{claude_review,backfill_meal_quality}.py \
  src/tjbot/handlers/{coach,bodyweight,meal,nutrition_profile}.py
```
Expected: все файлы существуют, без «No such file».

### Task A2: Скан на приватные значения + первый прогон тестов

**Files:** только чтение/прогон.

- [ ] **Step 1: Grep по перенесённому `src/` на приватное**

Run:
```bash
cd "$PUB"
grep -rnE 'REDACTED|duckdns|nNigma|nnigma|/Users/|/root/app|REDACTED' src/ \
  | grep -vE 'backfill_meal_quality\.py' || echo "CLEAN"
```
Expected: `CLEAN` (единственное допустимое упоминание `CLAUDE_BIN=/root/.local/bin/claude` — в docstring `backfill_meal_quality.py`, это общий хинт, не приватка; при желании обезличить в отдельном шаге).

- [ ] **Step 2: Установить окружение pub и прогнать тесты (базовая линия ДО правок)**

Run:
```bash
cd "$PUB" && make setup && PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:randomly -q
```
Expected: набор запускается. Часть тестов про Claude/engine может падать — это ожидаемо, чиним в Task C4/фиксах. Зафиксировать число прошедших/упавших как базовую линию.

- [ ] **Step 3: Commit**

```bash
cd "$PUB"
git add -A
git commit -m "sync src+tests из gen_n, чистка мусора"
```

---

## Фаза B — Ядро тумблера

### Task B1: Резолвер `claude_enabled()` в config.py

**Files:**
- Modify: `PUB/src/tj/config.py`
- Test: `PUB/tests/test_claude_toggle.py`

- [ ] **Step 1: Написать падающий тест**

```python
# PUB/tests/test_claude_toggle.py
import textwrap

from tj import config as cfgmod


def _write_cfg(tmp_path, body: str):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_claude_enabled_default_false(tmp_path, monkeypatch):
    monkeypatch.delenv("KUZ_USE_CLAUDE", raising=False)
    cfgmod.reset_claude_cache()
    monkeypatch.setattr(cfgmod, "load_config", lambda *a, **k: {})
    assert cfgmod.claude_enabled() is False


def test_claude_enabled_from_config_true(tmp_path, monkeypatch):
    monkeypatch.delenv("KUZ_USE_CLAUDE", raising=False)
    cfgmod.reset_claude_cache()
    monkeypatch.setattr(cfgmod, "load_config",
                        lambda *a, **k: {"llm": {"use_claude": True}})
    assert cfgmod.claude_enabled() is True


def test_claude_enabled_env_override_wins(monkeypatch):
    cfgmod.reset_claude_cache()
    monkeypatch.setattr(cfgmod, "load_config",
                        lambda *a, **k: {"llm": {"use_claude": True}})
    monkeypatch.setenv("KUZ_USE_CLAUDE", "0")
    assert cfgmod.claude_enabled() is False
    monkeypatch.setenv("KUZ_USE_CLAUDE", "1")
    assert cfgmod.claude_enabled() is True


def test_claude_enabled_missing_config_is_false(monkeypatch):
    monkeypatch.delenv("KUZ_USE_CLAUDE", raising=False)
    cfgmod.reset_claude_cache()

    def _raise(*a, **k):
        raise FileNotFoundError("no config")

    monkeypatch.setattr(cfgmod, "load_config", _raise)
    assert cfgmod.claude_enabled() is False
```

- [ ] **Step 2: Прогнать — убедиться что падает**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -q`
Expected: FAIL — `AttributeError: module 'tj.config' has no attribute 'reset_claude_cache'`.

- [ ] **Step 3: Реализовать резолвер в `config.py`**

Добавить в конец `src/tj/config.py`:

```python
_CLAUDE_ENABLED_CACHE: bool | None = None


def claude_enabled() -> bool:
    """Включён ли Claude-путь. Приоритет: env KUZ_USE_CLAUDE (живой, для тестов и
    systemd) -> config.toml [llm].use_claude -> False. Чтение config кэшируется."""
    env = os.environ.get("KUZ_USE_CLAUDE")
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    global _CLAUDE_ENABLED_CACHE
    if _CLAUDE_ENABLED_CACHE is None:
        try:
            cfg = load_config()
            _CLAUDE_ENABLED_CACHE = bool(cfg.get("llm", {}).get("use_claude", False))
        except FileNotFoundError:
            _CLAUDE_ENABLED_CACHE = False
    return _CLAUDE_ENABLED_CACHE


def reset_claude_cache() -> None:
    """Сброс кэша (для тестов)."""
    global _CLAUDE_ENABLED_CACHE
    _CLAUDE_ENABLED_CACHE = None
```

- [ ] **Step 4: Прогнать — убедиться что зелено**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -q`
Expected: PASS (4 теста).

- [ ] **Step 5: Commit**

```bash
cd "$PUB"
git add src/tj/config.py tests/test_claude_toggle.py
git commit -m "config: резолвер claude_enabled (config.toml/env, дефолт off)"
```

### Task B2: Гейт в `llm.py` — claude_complete/vision/has_claude_vision

**Files:**
- Modify: `PUB/src/tj/llm.py`
- Test: `PUB/tests/test_claude_toggle.py`

- [ ] **Step 1: Дописать падающие тесты гейта**

Добавить в `tests/test_claude_toggle.py`:

```python
from tj import llm


def test_claude_complete_gated_off(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "0")
    called = {"bin": False}
    monkeypatch.setattr(llm, "_claude_bin", lambda: (called.__setitem__("bin", True) or "/x/claude"))
    assert llm.claude_complete("привет") is None
    assert called["bin"] is False  # до бинарника даже не дошли


def test_claude_vision_gated_off(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "0")
    monkeypatch.setattr(llm, "_claude_bin", lambda: "/x/claude")
    assert llm.claude_vision(b"\xff\xd8", "prompt") is None


def test_has_claude_vision_gated_off(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "0")
    monkeypatch.setattr(llm, "_claude_bin", lambda: "/x/claude")
    assert llm.has_claude_vision() is False


def test_has_claude_vision_on_with_bin(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "1")
    monkeypatch.setattr(llm, "_claude_bin", lambda: "/x/claude")
    assert llm.has_claude_vision() is True
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -k gated -q`
Expected: FAIL (гейта ещё нет — `claude_complete` пытается дойти до бинарника).

- [ ] **Step 3: Вставить гейт в `llm.py`**

В `src/tj/llm.py` добавить импорт резолвера и гейты.

В начале функции `has_claude_vision` заменить тело:

```python
def has_claude_vision() -> bool:
    from tj.config import claude_enabled
    return claude_enabled() and bool(_claude_bin())
```

В начало `claude_vision` (сразу после docstring, ПЕРЕД `if not _claude_bin():`) добавить:

```python
    from tj.config import claude_enabled
    if not claude_enabled():
        return None
```

В начало `claude_complete` (сразу после docstring, ПЕРЕД `if not _claude_bin():`) добавить:

```python
    from tj.config import claude_enabled
    if not claude_enabled():
        return None
```

- [ ] **Step 4: Прогнать — зелено**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "$PUB"
git add src/tj/llm.py tests/test_claude_toggle.py
git commit -m "llm: гейт claude_complete/vision/has_claude_vision по claude_enabled"
```

### Task B3: API-бэкенд `_anthropic_complete` (текст) в claude_complete

**Files:**
- Modify: `PUB/src/tj/llm.py`
- Test: `PUB/tests/test_claude_toggle.py`

- [ ] **Step 1: Падающий тест — при включённом Claude без CLI, но с ключом, идём в API**

```python
def test_claude_complete_uses_api_when_no_cli(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "1")
    monkeypatch.setattr(llm, "_claude_bin", lambda: None)          # CLI нет
    monkeypatch.setattr(llm, "_anthropic_complete",
                        lambda prompt, **k: "API-ответ")
    assert llm.claude_complete("вопрос") == "API-ответ"


def test_claude_complete_prefers_cli_over_api(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "1")
    monkeypatch.setattr(llm, "_claude_bin", lambda: "/x/claude")
    monkeypatch.setattr(llm, "_claude_run", lambda *a, **k: "CLI-ответ")
    monkeypatch.setattr(llm, "_anthropic_complete",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("API не должен вызываться")))
    assert llm.claude_complete("вопрос") == "CLI-ответ"
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -k api -q`
Expected: FAIL — `_anthropic_complete` не существует, а `claude_complete` без CLI возвращает None.

- [ ] **Step 3: Реализовать API-бэкенд и переписать `claude_complete`**

В `src/tj/llm.py` добавить (рядом с прочими claude-функциями):

```python
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
```

Заменить тело `claude_complete` (сохранив гейт из Task B2):

```python
def claude_complete(prompt: str, *, timeout: float = 150.0) -> str | None:
    """Текстовая задача: CLI по подписке -> API-ключ -> None. cwd CLI = пустая
    временная папка (изоляция от CLAUDE.md). Сбой всех -> None, звонящий фолбэчит."""
    from tj.config import claude_enabled
    if not claude_enabled():
        return None
    if _claude_bin():
        with _claude_guard():
            with tempfile.TemporaryDirectory(prefix="tj-text-") as td:
                text = _claude_run(prompt, td, timeout, "claude_complete")
        if text:
            return text
    return _anthropic_complete(prompt, timeout=timeout)
```

- [ ] **Step 4: Прогнать — зелено**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "$PUB"
git add src/tj/llm.py tests/test_claude_toggle.py
git commit -m "llm: Claude через ANTHROPIC_API_KEY как фолбэк CLI (только текст)"
```

### Task B4: `deep_complete` — движко-агностичный глубокий разбор

**Files:**
- Modify: `PUB/src/tj/llm.py`
- Test: `PUB/tests/test_claude_toggle.py`

- [ ] **Step 1: Падающий тест**

```python
def test_deep_complete_claude_when_enabled(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "1")
    monkeypatch.setattr(llm, "claude_complete", lambda p, **k: "глубокий Claude")
    monkeypatch.setattr(llm, "complete",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Gemini не нужен")))
    assert llm.deep_complete("prompt") == "глубокий Claude"


def test_deep_complete_gemini_when_disabled(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "0")
    # claude_complete под гейтом сам вернёт None
    monkeypatch.setattr(llm, "complete", lambda system, user, **k: "глубокий Gemini")
    assert llm.deep_complete("prompt") == "глубокий Gemini"
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -k deep -q`
Expected: FAIL — `deep_complete` не существует.

- [ ] **Step 3: Реализовать**

В `src/tj/llm.py` добавить:

```python
def deep_complete(prompt: str, *, timeout: float = 300.0,
                  max_output_tokens: int = 2600) -> str | None:
    """Глубокий разбор движко-агностично: Claude (если включён и доступен) ->
    Gemini. claude_complete под гейтом сам вернёт None при выключенном Claude."""
    text = claude_complete(prompt, timeout=timeout)
    if text:
        return text
    return complete("", prompt, max_output_tokens=max_output_tokens)
```

- [ ] **Step 4: Прогнать — зелено**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -q`
Expected: PASS (весь файл).

- [ ] **Step 5: Commit**

```bash
cd "$PUB"
git add src/tj/llm.py tests/test_claude_toggle.py
git commit -m "llm: deep_complete — Claude или Gemini для глубоких разборов"
```

---

## Фаза C — Потребители

### Task C1: `engine_for()` под гейтом

**Files:**
- Modify: `PUB/src/tjbot/vision.py:32-35`
- Test: `PUB/tests/test_claude_toggle.py`

- [ ] **Step 1: Падающий тест**

```python
def test_engine_for_off_is_gemini(monkeypatch):
    from tjbot import vision
    monkeypatch.setenv("KUZ_USE_CLAUDE", "0")
    assert vision.engine_for(123) == "gemini"


def test_engine_for_on_is_claude(monkeypatch):
    from tjbot import vision
    monkeypatch.setenv("KUZ_USE_CLAUDE", "1")
    assert vision.engine_for(123) == "claude"
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -k engine_for -q`
Expected: FAIL — `engine_for` всегда `"claude"`.

- [ ] **Step 3: Реализовать**

В `src/tjbot/vision.py` заменить `engine_for`:

```python
def engine_for(tg_id: int) -> str:
    """Claude включён -> все фото в Claude CLI (Gemini — фолбэк роутера).
    Выключен -> Gemini единственный движок."""
    from tj.config import claude_enabled
    return "claude" if claude_enabled() else "gemini"
```

- [ ] **Step 4: Прогнать — зелено**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -k engine_for -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "$PUB"
git add src/tjbot/vision.py tests/test_claude_toggle.py
git commit -m "vision: engine_for под claude_enabled (off -> gemini)"
```

### Task C2: `claude_review` — движко-агностичный, без хардстопа

**Files:**
- Modify: `PUB/src/tjbot/claude_review.py` (`_ask` ~строка 117; `run_all` ~строка 209)
- Test: `PUB/tests/test_claude_toggle.py`

- [ ] **Step 1: Падающий тест — run_all не аборт при выключенном Claude**

```python
def test_review_ask_uses_deep_complete(monkeypatch):
    from tjbot import claude_review
    monkeypatch.setenv("KUZ_USE_CLAUDE", "0")
    from tj import llm
    monkeypatch.setattr(llm, "deep_complete", lambda p, **k: '{"blocks": []}')
    assert claude_review._ask("инструкция") == {"blocks": []}


def test_run_all_no_hardstop_without_claude(monkeypatch):
    from tjbot import claude_review
    from tj import llm
    monkeypatch.setenv("KUZ_USE_CLAUDE", "0")
    monkeypatch.setattr(llm, "has_claude_vision", lambda: False)
    monkeypatch.setattr(claude_review.access, "load_pro", lambda: set())
    # раньше возвращал [{"error": "claude CLI недоступен"}]; теперь — обычный (пустой) прогон
    out = claude_review.run_all(db_path=":memory:")
    assert out == [] or all("claude CLI недоступен" not in str(x) for x in out)
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -k "review or run_all" -q`
Expected: FAIL — `_ask` зовёт `claude_complete`; `run_all` возвращает ошибку про CLI.

- [ ] **Step 3: Реализовать**

В `src/tjbot/claude_review.py`, функция `_ask`, заменить строку
`raw = llm.claude_complete(_ROLE + "\n\n" + instr, timeout=_TIMEOUT)` на:

```python
    raw = llm.deep_complete(_ROLE + "\n\n" + instr, timeout=_TIMEOUT)
```

В `run_all` удалить хардстоп-гард (первые строки функции):

```python
    if not llm.has_claude_vision():
        return [{"error": "claude CLI недоступен (bin не найден)"}]
```

Заменить docstring `run_all` на движко-нейтральный:

```python
def run_all(db_path=None) -> list[dict]:
    """Прогон по всем Pro. Текст пишет Claude (если включён) или Gemini —
    через deep_complete. Сбой шага — пропуск, не порча данных."""
```

- [ ] **Step 4: Прогнать — зелено**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_claude_toggle.py -k "review or run_all" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "$PUB"
git add src/tjbot/claude_review.py tests/test_claude_toggle.py
git commit -m "claude_review: разбор через deep_complete, без хардстопа на нет-Claude"
```

### Task C3: Бот — пропуск выбора движка при выключенном Claude (record_workout)

**Files:**
- Modify: `PUB/src/tjbot/handlers/record_workout.py` (функции `board` ~160, `board_engine` ~194)
- Test: `PUB/tests/test_engine_skip.py`

- [ ] **Step 1: Падающий тест на хелпер выбора**

Логику «показывать ли выбор движка» вынесем в чистый предикат `_offer_engine_choice()`, чтобы тестировать без Telegram-моков.

```python
# PUB/tests/test_engine_skip.py
from tjbot.handlers import record_workout as rw
from tjbot.handlers import club


def test_no_engine_choice_when_claude_off(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "0")
    assert rw._offer_engine_choice() is False
    assert club._offer_engine_choice() is False


def test_engine_choice_when_claude_on(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "1")
    from tjbot import vision
    monkeypatch.setattr(vision, "has_claude", lambda: True)
    assert rw._offer_engine_choice() is True
    assert club._offer_engine_choice() is True
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_engine_skip.py -q`
Expected: FAIL — `_offer_engine_choice` не существует.

- [ ] **Step 3: Реализовать предикат и развилку в `record_workout.py`**

Добавить рядом с `_engine_kb` в `src/tjbot/handlers/record_workout.py`:

```python
def _offer_engine_choice() -> bool:
    """Показывать ли выбор движка доски: только когда Claude-vision доступен
    (включён и есть CLI). Иначе фото идёт сразу в Gemini."""
    from .. import vision
    return vision.has_claude()
```

В функции `board`, заменить ветку получения фото (строки, где сейчас):

```python
        await msg.reply_text(i18n.t("record.ask_engine", lang), reply_markup=_engine_kb(lang))
        return BOARD_ENGINE
```

на:

```python
        if _offer_engine_choice():
            await msg.reply_text(i18n.t("record.ask_engine", lang), reply_markup=_engine_kb(lang))
            return BOARD_ENGINE
        return await _parse_board_photo(msg, context, lang, "gemini", uid)
```

- [ ] **Step 4: Вынести тело парса фото в `_parse_board_photo` (рефактор `board_engine`)**

Тело `board_engine` (после определения `engine`) вынести в переиспользуемый хелпер. Добавить в `record_workout.py`:

```python
async def _parse_board_photo(message, context: ContextTypes.DEFAULT_TYPE,
                             lang: str, engine: str, uid: int) -> int:
    """Скачать фото доски и распознать выбранным движком. Общий код для выбора
    движка (Claude вкл) и прямого Gemini-пути (Claude выкл)."""
    file_id = context.user_data.get("board_photo")
    if not file_id:
        await message.reply_text(_result_prompt(lang))
        return RESULT
    if not access.llm_quota_consume(uid):
        context.user_data["board_text"] = "[фото доски — не распознано]"
        await message.reply_text(_llm_limit_msg(lang) + i18n.t("record.ask_board_text_fallback", lang))
        return BOARD
    await message.reply_text(i18n.t(
        "record.parsing_photo_slow" if engine == "claude" else "record.parsing_photo", lang))
    from .. import vision
    draft = None
    try:
        f = await context.bot.get_file(file_id)
        buf = await f.download_as_bytearray()
        draft = vision.parse_board(bytes(buf), engine=engine)
    except Exception:
        draft = None
    if draft and draft.get("raw_text"):
        context.user_data["board_text"] = draft["raw_text"]
        if draft.get("format"):
            context.user_data["wod_format"] = draft["format"]
        if draft.get("engine_used") and draft["engine_used"] != engine:
            await message.reply_text(i18n.t("record.board_engine_swapped", lang))
        return await _ask_board_confirm(message, context, lang)
    context.user_data["board_text"] = "[фото доски — не распознано]"
    await message.reply_text(
        i18n.t("record.board_not_recognized_head", lang)
        + i18n.t("record.ask_board_text_fallback", lang),
        reply_markup=_board_failed_kb(lang))
    return BOARD
```

Переписать `board_engine`, чтобы он звал хелпер:

```python
async def board_engine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор движка распознавания доски: быстрый Gemini или медленный Claude."""
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid)
    con.close()
    engine = "claude" if q.data == "beng:slow" else "gemini"
    await q.edit_message_text(i18n.t(
        "record.parsing_photo_slow" if engine == "claude" else "record.parsing_photo", lang))
    return await _parse_board_photo(q.message, context, lang, engine, uid)
```

> Примечание: `_parse_board_photo` берёт `message` (у `q.message` тот же интерфейс `reply_text`). `board_engine` уже отправил «parsing…» — в хелпере это повторное сообщение безвредно; при желании убрать дубль, вынести `parsing…` только в хелпер и не слать из `board_engine`. Для простоты оставляем как есть (одно лишнее «parsing…» в Claude-ветке некритично), либо удаляем `edit_message_text` из `board_engine` — на выбор исполнителя, тесты это не проверяют.

- [ ] **Step 5: Прогнать целевой тест + смоук-компиляцию**

Run:
```bash
cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_engine_skip.py -k record -q
PYTHONPATH=src .venv/bin/python -c "import tjbot.handlers.record_workout"
```
Expected: тест PASS (record-часть), импорт без ошибок.

- [ ] **Step 6: Commit**

```bash
cd "$PUB"
git add src/tjbot/handlers/record_workout.py tests/test_engine_skip.py
git commit -m "record_workout: пропуск выбора движка при выключенном Claude"
```

### Task C4: Бот — то же для club-флоу

**Files:**
- Modify: `PUB/src/tjbot/handlers/club.py` (`_engine_kb`/entry ~38, `add_engine` ~333, точка входа ~325)
- Test: `PUB/tests/test_engine_skip.py` (club-часть уже написана в C3 Step 1)

- [ ] **Step 1: Убедиться, что club-часть теста падает**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_engine_skip.py -k club -q`
Expected: FAIL — `club._offer_engine_choice` не существует.

- [ ] **Step 2: Добавить предикат `_offer_engine_choice` в `club.py`**

Рядом с `_engine_kb` в `src/tjbot/handlers/club.py`:

```python
def _offer_engine_choice() -> bool:
    """Показывать ли выбор движка доски в club-флоу (Claude-vision доступен)."""
    from .. import vision
    return vision.has_claude()
```

- [ ] **Step 3: Вынести парс фото в `_parse_add_photo` (рефактор `add_engine`)**

Добавить в `src/tjbot/handlers/club.py` (club-версия проще record: без quota-consume, `lang` из `user_data`):

```python
async def _parse_add_photo(message, context: ContextTypes.DEFAULT_TYPE,
                           lang: str, engine: str) -> int:
    """Скачать фото программы зала и распознать выбранным движком. Общий код для
    выбора движка (Claude вкл) и прямого Gemini-пути (Claude выкл)."""
    from .. import vision
    file_id = context.user_data.get("club_photo")
    if not file_id:
        await message.reply_text(i18n.t("club.send_text_or_photo", lang))
        return ADD_INPUT
    await message.reply_text(i18n.t(
        "record.parsing_photo_slow" if engine == "claude" else "record.parsing_photo", lang))
    db = None
    try:
        f = await context.bot.get_file(file_id)
        buf = await f.download_as_bytearray()
        db = vision.parse_board(bytes(buf), engine=engine)
    except Exception:
        db = None
    raw_text = db.get("raw_text") if db else None
    if not raw_text:
        await message.reply_text(i18n.t("club.photo_not_recognized", lang),
                                 reply_markup=_board_failed_kb(lang))
        return ADD_INPUT
    if db.get("engine_used") and db["engine_used"] != engine:
        await message.reply_text(i18n.t("record.board_engine_swapped", lang))
    return await _finish_add_input(message, context, raw_text, "photo")
```

Переписать `add_engine`, чтобы он звал хелпер:

```python
async def add_engine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор движка распознавания программы зала: быстрый Gemini / медленный Claude."""
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "ru")
    engine = "claude" if q.data == "ceng:slow" else "gemini"
    return await _parse_add_photo(q.message, context, lang, engine)
```

- [ ] **Step 4: Развилка в `add_input` и `add_retry`**

В `add_input`, ветку фото заменить

```python
        await msg.reply_text(i18n.t("record.ask_engine", lang), reply_markup=_engine_kb(lang))
        return ADD_ENGINE
```

на

```python
        if _offer_engine_choice():
            await msg.reply_text(i18n.t("record.ask_engine", lang), reply_markup=_engine_kb(lang))
            return ADD_ENGINE
        return await _parse_add_photo(msg, context, lang, "gemini")
```

В `add_retry` заменить

```python
    await q.edit_message_text(i18n.t("record.ask_engine", lang), reply_markup=_engine_kb(lang))
    return ADD_ENGINE
```

на

```python
    if _offer_engine_choice():
        await q.edit_message_text(i18n.t("record.ask_engine", lang), reply_markup=_engine_kb(lang))
        return ADD_ENGINE
    return await _parse_add_photo(q.message, context, lang, "gemini")
```

- [ ] **Step 5: Прогнать тест + смоук-импорт**

Run:
```bash
cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/test_engine_skip.py -q
PYTHONPATH=src .venv/bin/python -c "import tjbot.handlers.club"
```
Expected: PASS (оба теста), импорт без ошибок.

- [ ] **Step 6: Commit**

```bash
cd "$PUB"
git add src/tjbot/handlers/club.py tests/test_engine_skip.py
git commit -m "club: пропуск выбора движка при выключенном Claude"
```

### Task C5: Полный прогон набора + фикс упавших портированных тестов

**Files:**
- Modify: перенесённые тесты `PUB/tests/test_llm_claude.py`, `PUB/tests/test_claude_review_auto.py`, `PUB/tests/test_verify_blocks.py` и любые, что завязаны на «Claude всегда включён».

- [ ] **Step 1: Полный прогон, собрать список падений**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:randomly -q`
Expected: часть тестов падает из-за дефолта `use_claude=false`. Типовые причины:
- тест зовёт реальный `llm.claude_complete`/`engine_for`/`has_claude_vision`, ожидая Claude включённым;
- `test_claude_review_auto` ожидает старый хардстоп `run_all`.

- [ ] **Step 2: Чинить каждый — включать Claude там, где тест это подразумевает**

Для тестов, которым нужен включённый Claude, добавить в начало теста/фикстуры:

```python
    monkeypatch.setenv("KUZ_USE_CLAUDE", "1")
```

(тесты, которые монкейпатчат `llm.claude_complete`/`has_claude_vision` напрямую, — обычно уже проходят, т.к. подменяют функцию целиком; env нужен там, где вызывается настоящая реализация или `engine_for`).

Для `test_claude_review_auto`, где проверялся хардстоп «claude недоступен» — обновить ожидание под движко-агностичный `run_all` (см. Task C2): при выключенном Claude прогон идёт через Gemini, ошибки про CLI больше нет.

- [ ] **Step 3: Повторный полный прогон — всё зелено**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:randomly -q`
Expected: PASS (все тесты; ориентир — ~571 из gen_n + новые из этого плана).

- [ ] **Step 4: Проверка «работает без Claude из коробки» — дефолтный конфиг**

Run:
```bash
cd "$PUB"
cp -n config.example.toml config.toml 2>/dev/null || true
grep -A1 '\[llm\]' config.toml || echo "нет [llm] — ок, дефолт off"
PYTHONPATH=src .venv/bin/python -c "from tj.config import claude_enabled; print('claude_enabled =', claude_enabled())"
rm -f config.toml   # не оставляем локальный конфиг в дереве
```
Expected: `claude_enabled = False`.

- [ ] **Step 5: Commit**

```bash
cd "$PUB"
git add tests/
git commit -m "tests: адаптация под дефолт use_claude=false"
```

---

## Фаза D — Упаковка, конфиг, доки

### Task D1: `anthropic` в отдельный extra `[claude]`

**Files:**
- Modify: `PUB/pyproject.toml`

- [ ] **Step 1: Вынести `anthropic` из `bot` в `claude`**

В `PUB/pyproject.toml`, в `[project.optional-dependencies]`:
- убрать `"anthropic"` из списка `bot`;
- добавить строку:

```toml
claude = ["anthropic>=0.40"]
```

Итог секции:

```toml
[project.optional-dependencies]
bot = ["python-telegram-bot>=21", "fastapi", "uvicorn[standard]", "telethon"]
claude = ["anthropic>=0.40"]
```

- [ ] **Step 2: Проверить, что base+bot ставятся без anthropic, и что claude-extra тянет его**

Run:
```bash
cd "$PUB"
.venv/bin/python -c "import tomllib,sys; d=tomllib.load(open('pyproject.toml','rb')); \
print('bot:', d['project']['optional-dependencies']['bot']); \
print('claude:', d['project']['optional-dependencies']['claude'])"
```
Expected: в `bot` нет `anthropic`; в `claude` есть.

- [ ] **Step 3: Commit**

```bash
cd "$PUB"
git add pyproject.toml
git commit -m "pyproject: anthropic — опциональный extra [claude]"
```

### Task D2: `config.example.toml` — блок `[llm]`

**Files:**
- Modify: `PUB/config.example.toml`

- [ ] **Step 1: Добавить секцию `[llm]` (после `[store]` или в конец)**

Дописать в `PUB/config.example.toml`:

```toml
[llm]
# AI-движок разборов и распознавания фото.
#   false — всё через Gemini (нужен только GEMINI_API_KEY, работает из коробки).
#   true  — Claude-first, Gemini как фолбэк. Требует ЛИБО установленный и
#           залогиненный Claude Code CLI (claude в PATH / CLAUDE_BIN),
#           ЛИБО ANTHROPIC_API_KEY в .env (только текстовые разборы).
use_claude = false
```

- [ ] **Step 2: Смоук — файл валидный TOML**

Run: `cd "$PUB" && .venv/bin/python -c "import tomllib; tomllib.load(open('config.example.toml','rb')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
cd "$PUB"
git add config.example.toml
git commit -m "config.example: секция [llm] use_claude"
```

### Task D3: `.env.example` — ANTHROPIC_API_KEY в опциональную секцию

**Files:**
- Modify: `PUB/.env.example`

- [ ] **Step 1: Переписать блок про Claude**

Заменить в `PUB/.env.example` текущий блок Claude на:

```bash
# ── Claude (Anthropic) — optional, only if [llm].use_claude = true ───────
# Two ways to enable Claude (see config.toml [llm].use_claude):
#   1) Install & log in Claude Code CLI (subscription) — nothing to set here.
#   2) OR set an Anthropic API key below (text reviews only; photo OCR stays on Gemini).
# Leave empty for the default Gemini-only setup.
ANTHROPIC_API_KEY=
# Optional model override for the API path (default: claude-sonnet-5).
# ANTHROPIC_MODEL=claude-sonnet-5
```

- [ ] **Step 2: Commit**

```bash
cd "$PUB"
git add .env.example
git commit -m ".env.example: Claude — опционально, пояснение про CLI vs API"
```

### Task D4: README + deploy/README — секция про AI-бэкенд

**Files:**
- Modify: `PUB/README.md`, `PUB/deploy/README.md`

- [ ] **Step 1: В `PUB/README.md` добавить секцию (после «Быстрый старт»/«Quick start»)**

```markdown
## AI backend: Gemini-only (default) or Claude

Out of the box the bot runs on **Gemini only** — one free `GEMINI_API_KEY` and
you're done. All AI features (workout reviews, coach, board/meal photo OCR,
deep "Monsieur Claude" review) work through Gemini.

If you have Claude, flip one switch in `config.toml`:

```toml
[llm]
use_claude = true
```

Then the pipeline becomes Claude-first with Gemini as fallback. `use_claude = true`
needs **either**:
- Claude Code CLI installed and logged in (`claude` in `PATH`, subscription), **or**
- `ANTHROPIC_API_KEY` in `.env` (text reviews via the API; photo OCR stays on Gemini).

With neither present it logs a warning and falls back to Gemini, so nothing breaks.
```

- [ ] **Step 2: В `PUB/deploy/README.md` — в шаге установки зависимостей**

Заменить `uv pip install -e '.[bot]'` на пояснение про опциональный Claude:

```markdown
```bash
uv pip install -e '.[bot]'          # Gemini-only (default)
# uv pip install -e '.[bot,claude]' # only if you set use_claude = true with an API key
```
```

И добавить в раздел Configure строку про `config.toml [llm].use_claude` (по умолчанию `false`, оставить как есть для Gemini-only).

- [ ] **Step 3: Commit**

```bash
cd "$PUB"
git add README.md deploy/README.md
git commit -m "docs: AI backend — Gemini по умолчанию, Claude опционально"
```

### Task D5: `.gitignore` — мусор + локальный config

**Files:**
- Modify: `PUB/.gitignore`

- [ ] **Step 1: Убедиться, что в `.gitignore` есть**

Проверить/добавить в `PUB/.gitignore`:

```gitignore
__pycache__/
*.pyc
*.egg-info/
.DS_Store
config.toml
```

Run: `cd "$PUB" && grep -qE 'egg-info' .gitignore && grep -qE 'DS_Store' .gitignore && echo ok || echo "дополнить"`
Expected: `ok` (иначе дописать недостающее).

- [ ] **Step 2: Commit**

```bash
cd "$PUB"
git add .gitignore
git commit -m "gitignore: мусор сборки + локальный config.toml"
```

---

## Финальная приёмка

### Task E1: Прогон обоих режимов и очистка

- [ ] **Step 1: Gemini-only (дефолт) — полный прогон**

Run: `cd "$PUB" && PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:randomly -q`
Expected: PASS.

- [ ] **Step 2: Claude-режим — полный прогон под env-оверрайдом**

Run: `cd "$PUB" && KUZ_USE_CLAUDE=1 PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:randomly -q`
Expected: PASS (моки Claude покрывают отсутствие реального CLI).

- [ ] **Step 3: Проверить чистоту дерева и git-статус**

Run: `cd "$PUB" && git status --short && find . -name '__pycache__' -not -path './.venv/*' -o -name '.DS_Store' | grep -v '.venv' || echo "чисто"`
Expected: рабочее дерево без незакоммиченного мусора; локального `config.toml` в индексе нет.

- [ ] **Step 4: Финальный смоук-импорт всех новых подсистем**

Run:
```bash
cd "$PUB" && PYTHONPATH=src .venv/bin/python -c "
import tj.analysis.coach, tj.analysis.muscles, tj.analysis.nutrition, tj.analysis.nutrition_goals, tj.analysis.watch_advice
import tjbot.claude_review, tjbot.handlers.coach, tjbot.handlers.meal, tjbot.handlers.nutrition_profile, tjbot.handlers.bodyweight
print('all imports ok')"
```
Expected: `all imports ok`.

---

## Заметки для исполнителя

- **Якорь путей** — `~/REDACTED/rr`, никогда не хардкодить `/Users/<имя>/`.
- **Порядок фаз важен:** A (снимок) → B (ядро) → C (потребители) → D (упаковка/доки). B до C: `engine_for`/`claude_review`/бот опираются на `claude_enabled()` и `deep_complete`.
- **Гейт-инвариант:** тесты, которые монкейпатчат `llm.claude_complete`/`has_claude_vision` целиком, не задевают гейт (подменяют всю функцию). Env `KUZ_USE_CLAUDE` нужен там, где зовётся настоящая реализация или `engine_for`.
- **Vision по API не делаем** — `claude_vision` жив только при наличии CLI-бинарника; при `use_claude=true` без CLI фото уходят в Gemini.
- **Коммиты** — короткой строкой по сути, без Co-Authored-By и следов ИИ (правила проекта).
- **Приватное** не переносится: `training.db*`, `.env`, `*.session`, токены, `raw/`, `data/`, `backups/`, `*_users.json`, `admins.json` — их нет в `src/`, они в `.gitignore`.
