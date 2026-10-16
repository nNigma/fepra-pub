# PWA-фронт (`web/`) — фаза 2

Vite + TypeScript (strict) + React 19 + react-router (hash) + Chart.js. Сборка кладётся в
`src/tjapp/static/app/` и отдаётся по `/app/` (см. `src/tjapp/webapp.py`). Клиент общается
только с `/api/*` по cookie-сессии, same-origin. Telegram WebApp SDK не грузится.

## Структура

```
web/
  index.html, vite.config.ts, tsconfig.json, eslint.config.js
  public/                иконки PWA (сгенерированы scripts/make-icons.mjs)
  scripts/               make-icons.mjs (SVG→PNG), convert-legacy.mjs (одноразовая конверсия strings.js/body.js)
  src/
    api/                 client.ts (fetch, 401→вход, ошибки, ?as=), endpoints.ts, types.ts, webauthn.ts
    i18n/                ru.ts / en.ts (новые ключи), legacy.{ru,en}.json (перенос из strings.js), index.tsx
    lib/                 session.tsx (GET /api/me), useFetch.ts, jobs.ts (поллинг), format.ts, markdown.ts
    components/          Shell (навигация, «нет соединения», баннер A2HS, ?as=), charts, svgparts, LlmBlock, ui
    screens/             Auth (вход, инвайт), Summary, Workouts, Nutrition, Competitions, Goals,
                         Leaderboard, Profile (+«Ещё»), Garmin, Invites
  test/                  vitest (client, webauthn, i18n, компоненты)
src/tjapp/webapp.py      mount(app): StaticFiles(html=True) + SPA-fallback + Cache-Control
```

## Запуск в разработке

```bash
# 1. бэкенд на локальной БД (FEPRA_DB_PATH), порт 8765
TJAPP_PORT=8765 PYTHONPATH=src .venv/bin/python -m tjapp.server
# 2. фронт с горячей перезагрузкой; /api проксируется на 8765
cd web && npm install && npm run dev                                               # http://localhost:5173/app/
```

Вход — по инвайту (`python -m tj.services.auth_cli invite --admin`, см. `auth.md`). Другой прокси-адрес: `FEPRA_DEV_API=http://host:port npm run dev`. Ссылка-инвайт: `http://localhost:5173/app/#/invite/<token>`.

## Сборка и проверки

```bash
cd web
npm run build     # tsc --noEmit + vite build → ../src/tjapp/static/app/ (артефакт, в git не хранится)
npm test          # vitest
npm run lint      # eslint
npm run icons     # перегенерировать иконки
```

Сборку нужно перезапускать после изменения исходников и до деплоя: на сервер уезжает `src/` вместе со `static/app/`.
Python-тесты раздачи: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_webapp.py -p no:randomly -q`.

## Что реализовано

- **Оболочка**: manifest (standalone, `start_url=/app/`, иконки 192/512 + maskable), service worker (workbox,
  предкэш только оболочки; `/api/*` не кэшируется, runtime-кэша нет), экран «Нет соединения» с повтором,
  нижняя навигация (тач ≥44px, safe-area), тёмная/светлая тема по `prefers-color-scheme`, RU/EN (RU по умолчанию),
  баннер «Добавь на экран Домой» на iPhone (один раз, `localStorage`).
- **Вход**: `#/invite/<token>` → ник → `POST /api/auth/redeem` → предложение passkey; экран входа по Face ID/отпечатку;
  `GET /api/me` — состояние сессии; 401 на любой запрос → экран входа.
- **Отчёты** на существующих GET: сводка, тренировки (лента, деталь, разбор Клода), питание (Pro), старты
  (+деталь), цели, лидерборд, ИИ-разборы (GET статус + POST запуск + поллинг). Админ-режим `?as=` — переключатель
  показывается только при `roles.admin`.
- **Профиль**: язык, выход, passkey, приглашения админа, «Подключить Garmin» (логин/MFA/синк/история/отключение;
  пароль в state не задерживается, `autocomplete=off`, не логируется).

## Допущения по контракту (проверить при сшивке с Волной 1)

- `POST /api/auth/passkey/*/options` возвращает options py-webauthn (`options_to_json`) напрямую либо в `{publicKey}`;
  если в ответе есть `challenge_id`, клиент вернёт его в теле `verify`. Тело `verify` — сам credential JSON
  (`id, rawId, type, response{…}`) в base64url.
- `POST /api/auth/redeem` при успехе ставит cookie-сессию; после него клиент вызывает `GET /api/me`.
- Ошибки редима отдают 4xx → «ссылка недействительна или использована».
- `GET /api/admin/invites` — массив или `{invites: [...]}`; поля `role, gym, note, expires_at, used_at`.
- Старые отчётные GET (`/api/summary` и др.) к моменту выката должны принимать cookie-сессию (`require_user`),
  иначе PWA получит 401.

## Осталось

- Запись тренировки, доска, ввод максов/целей, программы (Волны 3–4) — экранов нет; в «Целях» убраны кнопки
  «в боте», пока нет ввода.
- Офлайн-режим данных (часть 2): сейчас SW кэширует только оболочку.
- Пуши, лента изменений `GET /api/changes`.
- Не портированы из Mini App: подсказка `add_cta`/`enter_pm` (вход в бота).
- Бандл ~600 КБ (200 КБ gzip): при желании вынести Chart.js в отдельный чанк через lazy-маршруты.
