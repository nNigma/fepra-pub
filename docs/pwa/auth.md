# Вход, роли, миграции, задачи (Волна 1)

## Миграции
`src/tj/migrations/NNNN_name.py` с `upgrade(con)`; реестр `run_migrations(con)` применяет только новее
`meta.schema_version`. Вызывается в конце `tjbot.db.init_schema` (бот, `server_sync.py`, `server_review.py`)
и при старте API (lifespan в `api.py`, там же зависшие задачи помечаются ошибкой).
Только добавление таблиц и nullable-колонок: бот живёт на той же БД.

| № | Что |
|---|---|
| 0001 | `user_roles` + разовый импорт из `users_allow.json`, `admins.json`, `pro_users.json`, `coaches.json` (файлы рядом с БД; для боевой БД по умолчанию — там, где их искал `access.py`) |
| 0002 | `auth_identities`, `invites`, `sessions`, `passkeys`, `webauthn_challenges` |
| 0020 | `jobs` |

## Роли
`user_roles(user_id, role, gym)`, роли: `allowlist`, `admin`, `pro`, `coach` (gym — зал тренера).
`tjbot/access.py`: без `path` работает с БД (`FEPRA_DB_PATH` / `training.db`), с явным `path` — прежний JSON
(так пишут существующие тесты). Соединение открывается на вызов и закрывается. Если файла БД ещё нет,
чтение возвращает пусто и файл не создаёт. JSON после импорта больше не читается ботом; правки ролей идут
в БД (`/admin` бота уже вызывает `access.add_*`).

## Идентичность
`user_id` = `tg_id` для старых, для новых без Telegram `WEB_ID_BASE = 5_000_000_000_000_000` и выше
(`max(веб-id)+1`), запись в `users` (`tg_id`, ник, `lang='ru'`) и роль `allowlist`.
`auth_identities(provider, subject → user_id)`: провайдеры `invite` (subject = хеш инвайта) и `passkey`
(subject = credential id).

## Токены
Инвайты и сессии хранятся sha256-хешами, сырой токен отдаётся один раз. Инвайт одноразовый (атомарный
`UPDATE ... WHERE used_at IS NULL`), с TTL (по умолчанию 72 ч, максимум 720). Сессия: cookie
`fepra_session` (httpOnly, SameSite=Lax, Secure за https / при `X-Forwarded-Proto: https` / когда
`FEPRA_PUBLIC_URL` https и хост не localhost), скользящие 60 дней (продление не чаще раза в 5 минут).
Убрали из allowlist — сессия перестаёт работать (401), passkey-вход даёт 403.

## Passkey
Библиотека `webauthn` (py_webauthn). RP id и origin из `FEPRA_PUBLIC_URL`
(по умолчанию `https://fepra.example`). Вход по discoverable credential, аккаунт выбирается на
устройстве. Challenge хранится в `webauthn_challenges` (5 минут, одноразовый, привязан к операции и, при
регистрации, к пользователю); в API клиент возвращает `challenge_id`. `sign_count` должен расти
(0/0 допустимо). Реальную церемонию тесты не воспроизводят: верификация мокается.

## Эндпоинты
| Метод и путь | Доступ | Что |
|---|---|---|
| `POST /api/admin/invites` | admin | body `{role: user\|pro\|coach\|admin, gym, existing_user_id, ttl_hours, note}` → `{token, url}` |
| `GET /api/admin/invites` | admin | список без токенов: статус `active/used/expired` |
| `POST /api/auth/redeem` | без сессии | `{token, nick}` → cookie + `/api/me` (для `existing_user_id` ник не нужен) |
| `POST /api/auth/passkey/register/options`, `.../verify` | сессия | verify: `{challenge_id, credential, name}` |
| `POST /api/auth/passkey/login/options`, `.../verify` | без сессии | verify: `{challenge_id, credential}` → cookie + `/api/me` |
| `POST /api/auth/logout` | любой | отзывает сессию, стирает cookie |
| `GET /api/me` | сессия / initData | `{id, nick, lang, roles:{admin,pro,coach}, gym, has_passkey, garmin:{connected,status}\|null, public_url}` |
| `GET /api/jobs/{id}` | сессия / initData | `{id, status, result, error}`, чужая задача = 404 |

Лимит попыток по IP в памяти: redeem 10 за 10 минут, passkey login (options+verify) 20 за 10 минут,
далее 429. За Funnel берётся последний элемент `X-Forwarded-For`, если прямой клиент — loopback.

`tjapp/deps.py`: `require_user` (cookie или `X-Init-Data`; возвращает dict с `id`), `require_pro`,
`require_admin`, `resolve_effective_user` (`?as=` только админ, цель в allowlist), `client_ip`.
`api.require_auth` — реэкспорт `require_user`, старые эндпоинты Mini App не менялись.

## Задачи
`tj/services/jobs.py`: `create_job(con, kind, uid, payload)`, `run_in_background(job_id, fn)` (поток;
возврат `fn()` → `done`, исключение → `error`), `set_result/set_error`, `get_job(con, id, uid)`,
`fail_stale` при старте (pending/running → error). Статусы `pending|running|done|error`.

## Как выдать первую ссылку
Админа без Telegram нет, поэтому на сервере (из каталога проекта, с тем же `FEPRA_DB_PATH`, что у API):

    PYTHONPATH=src python -m tj.services.auth_cli invite --admin
    # -> https://fepra.example/app/#/invite/<token>

Открыть ссылку, ввести ник, затем зарегистрировать passkey (Face ID / отпечаток). Остальным ссылки
выдаёт админ через `POST /api/admin/invites`. Восстановление доступа: новый инвайт от админа.

## Как связать старый аккаунт
Админ выдаёт инвайт на существующий `user_id`:
CLI `... auth_cli invite --existing-id <tg_id>` или `POST /api/admin/invites {"existing_user_id": <tg_id>}`.
Тот, кто откроет ссылку, получает сессию именно этого пользователя, вся история сохраняется.
Ник не спрашивается, роли не меняются. Команда `/link` в боте не делалась (бот заморожен).

## Осталось
Фронт входа (`#/invite/<token>`, passkey-кнопки) — Волна 2; управление passkey (список/удаление) и сессиями;
Telegram как провайдер входа не реализован (старые аккаунты связываются инвайтом).
