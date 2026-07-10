# Публичная «Кузница»: синхронизация с gen_n + тумблер Claude/Gemini

Дата: 2026-07-10

## Цель

Две связанные задачи над публичным репозиторием `rgb/pub/kuznitsa`:

1. **Догнать код до актуального `gen_n/training-journal`** — перенести все новые
   подсистемы и правки, но без приватных данных.
2. **Сделать Claude опциональным.** При установке пользователь выбирает
   `use_claude = true/false`. Есть Claude — пайплайн работает как сейчас
   (Claude-first, Gemini-фолбэк). Нет — всё идёт только через Gemini. Любой может
   развернуть бота в 1-2 команды и пользоваться независимо от наличия Claude.

Не-цель: менять поведение личного `gen_n` (там Claude всегда включён). Спека про
публичный срез. Гейт делается так, что при желании тривиально переносится в
`gen_n`, но это отдельная работа.

## Контекст (как устроено сейчас)

- Claude вызывается через **CLI `claude -p`** (подписка Max/Pro), НЕ через
  API-ключ. `tj/llm.py::_claude_bin()` = `CLAUDE_BIN` env или `which claude`.
  `has_claude_vision()` = наличие бинарника.
- Точки, где Claude участвует:
  - `tj/llm.py`: `claude_complete()`, `claude_vision()`, `vision(engine=...)` роутер.
  - `tjbot/vision.py::engine_for()` — сейчас хардкод `"claude"`.
  - `tjbot/handlers/{record_workout,club}.py` — шаг выбора движка доски
    (⚡ Gemini / 🎩 Claude), состояния `BOARD_ENGINE`/`ADD_ENGINE`, retry.
  - `tjbot/handlers/meal.py`, `handlers/competition.py` — vision через `engine_for`.
  - `tj/analysis/coach.py`, `tj/analysis/llm_coach.py` — `claude_complete` с
    Gemini-фолбэком.
  - `tjbot/claude_review.py` — крон глубоких «Разборов от Месье Клода», сейчас
    Claude-only.
  - `tjbot/backfill_meal_quality.py` — `claude_complete or complete` (уже с фолбэком).
- Ниже границы `llm.py` почти везде уже есть Gemini-фолбэк — поэтому гейт ставится
  в одной точке, а не пробрасывается флагом через хендлеры.
- `src/` уже чист от хардкода приватного: owner id, токены, IP, домен берутся из
  env / gitignored-файлов.

## Дельта `pub` ← `gen_n`

Отсутствуют в `pub` целиком:
`tj/analysis/{coach,muscles,nutrition,nutrition_goals,watch_advice}.py`,
`tjbot/claude_review.py`, `tjbot/backfill_meal_quality.py`,
`tjbot/handlers/{coach,bodyweight,meal,nutrition_profile}.py`.
Плюс правки десятков существующих файлов (dashboard, llm_coach, report, workouts,
api.py, vision.py, record_workout.py, club.py, статика app.js/strings.js/index.html,
db.py, i18n.py, garmin.py и др.).

Мусор, закоммиченный в `pub` сейчас и подлежащий удалению: `__pycache__/`,
`src/training_journal.egg-info/`, `.DS_Store`.

## Дизайн

### 1. Синхронизация кода

- Заменить `pub/kuznitsa/src/` снимком `gen_n/.../src/` целиком (весь код +
  статика). Перенести тесты `gen_n/tests/` → `pub/tests/`.
- **Приватное не переносится:** копируем только `src/`, `tests/` и не-секретные
  артефакты. `training.db*`, `.env`, `*.session`, токены, `raw/`, `data/`,
  `backups/`, `pro_users.json`/`admins.json`/`users_allow.json`, `cache.duckdb` —
  не трогаем; их нет в `src/` и они в `.gitignore`.
- Почистить закоммиченный мусор (`__pycache__`, `*.egg-info`, `.DS_Store`) и
  дополнить `.gitignore`.
- После переноса — grep по `src/` на приватные значения (IP `REDACTED.*`, `duckdns`,
  реальные tg id, `nNigma`, юзер-пути) для страховки; ожидаемо чисто.
- `pyproject.toml`, `Makefile`, `scripts/`, `deploy/` в `pub` остаются, но
  правятся под новые зависимости/подсистемы (см. ниже).

### 2. Тумблер Claude (ядро)

Один флаг в `config.toml`:

```toml
[llm]
# false — всё идёт через Gemini (работает из коробки на одном GEMINI_API_KEY).
# true  — если стоит и залогинен Claude Code CLI ЛИБО задан ANTHROPIC_API_KEY.
use_claude = false
```

Резолвер `tj.config.claude_enabled() -> bool`:
- читает `[llm].use_claude` из `config.toml` (кэш на процесс);
- env-override `KUZ_USE_CLAUDE` (для тестов и systemd drop-in) имеет приоритет;
- дефолт `False`.

**Гейт на границе `tj/llm.py`:**
- `has_claude_vision()` → `claude_enabled() and (есть CLI-бинарник ИЛИ ANTHROPIC_API_KEY)`.
- `claude_complete()` / `claude_vision()` → если `not claude_enabled()`, сразу
  `None` (потребители падают на Gemini как сегодня — логика хендлеров не меняется).

**Новый бэкенд через ANTHROPIC_API_KEY** (в дополнение к CLI):
- при `use_claude=true` порядок выбора: **CLI-бинарник** (подписка, без
  маржинальной цены) → **API-ключ** (`anthropic` SDK, Messages API, модель
  sonnet по умолчанию) → **Gemini**;
- **API-ключ покрывает только текст** (`claude_complete`). Vision (фото доски/еды)
  через Anthropic API НЕ реализуем в этой итерации: если Claude доступен только по
  ключу без CLI, фото-распознавание идёт через Gemini. Причина — формат
  vision-сообщений API отличается от CLI, это лишний объём без спроса. Так что
  `claude_vision` жив только при наличии CLI-бинарника.
- `claude_complete`/`claude_vision` инкапсулируют этот выбор; наружу интерфейс
  прежний;
- если `use_claude=true`, но нет ни CLI, ни ключа — предупреждение в лог и мягкий
  фолбэк на Gemini (бот не падает).
- `anthropic` — опциональная зависимость: extra `[claude]` в `pyproject.toml`.
  Gemini-юзеры её не тянут.

### 3. Поведение при `use_claude=false`

- `tjbot/vision.py::engine_for()` → `"gemini"` (вместо хардкода `"claude"`).
- **Выбор движка доски в боте:** при выключенном Claude шаг выбора
  (⚡/🎩) пропускается — фото сразу в Gemini. Кнопка `🎩 Медленное (Claude)`
  показывается только когда `vision.has_claude()`. Затрагивает `record_workout.py`
  (`BOARD_ENGINE`) и `club.py` (`ADD_ENGINE`); retry-ветки сохраняются.
- **Глубокий «Разбор от Месье Клода»** (`claude_review.py`) — движко-агностичен
  через новый хелпер `llm.deep_complete(prompt, *, timeout, max_tokens)`:
  `claude_enabled()` → Claude (CLI/API), иначе Gemini `complete()` с поднятым
  потолком токенов. Крон разборов работает в обоих режимах; при Gemini-only текст
  «Разбора полётов» пишет Gemini.
- **Брендинг «Месье Клод» оставляем как есть** — это персона-пасхалка, не движок.
  При Gemini-only разбор всё равно подписан «Месье Клод».
- `coach()`/`llm_coach.coach()` уже с фолбэком claude→gemini; с гейтом просто
  сразу идут в Gemini, правок логики не требуется.

### 4. Установка и деплой

Цель — «1-2 команды, работает у всех без Claude»:
- `.env.example`: `ANTHROPIC_API_KEY` из обязательного блока убрать в опциональную
  секцию с пояснением (нужен только при `use_claude=true` без CLI-подписки).
  Обязательный минимум — `TG_KUZ_BOT_TOKEN`, `OWNER_TG_ID`, `GEMINI_API_KEY`,
  `MINIAPP_URL`.
- `config.example.toml`: добавить блок `[llm] use_claude = false` с комментарием.
- `README.md` (корень) и `deploy/README.md`: секция «AI backend — Gemini-only
  (default) vs Claude», явно: из коробки хватает одного `GEMINI_API_KEY`; Claude —
  опция для тех, у кого есть CLI-подписка или API-ключ.
- Робастность старта: убедиться, что импорт и запуск не падают без Claude и без
  `OWNER_TG_ID` не роняют то, что не должно (проверить `tj/store/build.py`
  импорт-тайм резолв owner id).

### 5. Тестирование

- `claude_enabled()`: true/false из `config.toml`, env-override `KUZ_USE_CLAUDE`.
- Гейт `llm.py`: `use_claude=false` → `claude_complete`/`claude_vision` вернут
  `None` без попытки запустить бинарник; `has_claude_vision()==False`.
- `engine_for()` == `"gemini"` при выключенном, `"claude"` при включённом.
- `deep_complete()`: Claude-путь при enabled, Gemini-путь при disabled (мок обоих).
- Новый API-бэкенд: мок `anthropic`-клиента — при наличии ключа и без CLI идём в API.
- Бот: при `use_claude=false` шаг выбора движка доски не показывается / `🎩`-кнопки нет.
- Прогон всего перенесённого набора тестов `gen_n` на `pub` (ориентир — 571
  зелёный), с дефолтным `use_claude=false`.

## Открытые риски

- Тесты `gen_n` могут неявно предполагать `use_claude=true`/наличие CLI — на
  публичном дефолте `false` часть моков Claude может потребовать правки на
  движко-агностичность. Ловим на прогоне.
