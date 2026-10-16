# Garmin-коннектор и Web Push (сервисный слой)

Роутов пока нет: они добавятся после слияния фундамента (`tjapp/deps.py`, `tj/services/jobs.py`).

## Сервисы
- `tj/services/garmin.py` — вход в Garmin без Telegram. Функции принимают `con` (sqlite), кроме `sync_*` (собственное соединение, для jobs).
  - `start_login(con, uid, email, password)` -> `{"state": "ok"|"need_mfa"|"error", "message"}`; блокирует до 60 с (вызывать из sync-хендлера/потока).
  - `submit_mfa(con, uid, code)` -> то же. `status(con, uid)` -> `{connected, status(ok|expired|none), email, last_sync, fail_count, mfa_pending}`.
  - `sync_recent(uid)` / `sync_history(uid, days)` (days 1..365) -> для jobs; исключения летят наружу, статус аккаунта обновляется.
  - `disconnect(con, uid)` — rmtree tokenstore, удалить аккаунт, сбросить счётчики и баннеры.
- Реестр сессий входа: память процесса, TTL 5 мин, один активный вход на uid (новый вытесняет старый и будит его поток). Пароль живёт только в аргументах потока `GarminConnectSession`; в БД, логах, сообщениях об ошибках, `repr` его нет (наружу идёт только тип исключения, сообщение — из фиксированного словаря). Бот использует прежний `tjbot.garmin_connect` без изменений.
- `tj/services/notices.py` — `user_notices` (`add` с дедупом непрочитанного того же kind, `list_notices`, `mark_read` только своё, `mark_kind_read`).
- `tj/services/push.py` — `subscribe/unsubscribe/subscriptions`, `send(con, uid, title, body, url, tag)` (404/410 -> мягкое удаление), `public_key()`, `notify_user(con, uid, kind, text, title, url, tag, tg, dedupe)` = запись в `user_notices` + push + (опционально) Telegram-запас. Каждый канал независим.
- `python -m tj.services.push_cli gen-keys` — печатает `FEPRA_VAPID_PRIVATE/PUBLIC/SUBJECT` для `.env`. Ключей в репозитории нет; без них push тихо пропускается (`skipped: no_vapid`), баннер остаётся.

## Таблицы (миграции 0040, 0041; идемпотентны, сервисы применяют их лениво)
- `user_notices(id UUID, uid, kind, text, created_at, read_at)`. Виды: `garmin_expired`, `garmin_sync_failed`, `review_ready`.
- `push_subscriptions(id UUID, uid, endpoint UNIQUE, p256dh, auth, ua, created_at, deleted_at)`. Повторная подписка на тот же endpoint оживляет строку и переписывает владельца.
- Статус/время синка: `meta` (`garmin_sync_at:<uid>`, `garmin_fail:<uid>`), как и раньше для счётчика.

## Где подключено
- `tjbot/garmin_alerts.py`: логика вынесена в `record_success/record_failure` (`apply` для крона использует их). При переходе в `expired` — уведомление пользователю (баннер + push + Telegram); при сетевых сбоях — только когда пора алертить (2 подряд, далее раз в неделю). Алерт админам в Telegram не менялся.
- `tjbot/claude_review.run_all`: «разбор готов» пользователю, если появились новые поденные разборы (баннер + push + Telegram-запас).
- Telegram-запас отключается `FEPRA_NOTIFY_TG=0`; веб-пользователям (`uid >= 5e15`) и в тестах не шлётся.
- `server_sync.py` -> `garmin_sync.sync_all`: пауза между пользователями `FEPRA_SYNC_PAUSE_MIN/MAX` (по умолчанию 20–60 с; 0 отключает), при 429 backoff `FEPRA_SYNC_429_BACKOFF` (300 с, удваивается, `FEPRA_SYNC_429_RETRIES=2`).

## Роуты (все через `require_user`)
- `src/tjapp/routes/garmin.py`: GET `/api/garmin/status`; POST `/api/garmin/login {email,password}` -> `{status: ok|need_mfa|error, message}`; POST `/api/garmin/mfa {code}` (то же); POST `/api/garmin/sync` -> `{job_id}`; POST `/api/garmin/history {days 1..365}` -> `{job_id}`; POST `/api/garmin/disconnect` -> `{ok}`.
  - login/mfa — обычные `def` (threadpool), блокируют до 60 с. Лимит по uid: login 5 и mfa 10 за 10 минут, иначе 429.
  - sync/history без подключённого аккаунта -> 409. Если синк уже идёт (pending/running), возвращается его же `job_id`. Результат — `GET /api/jobs/{id}` (только владелец).
  - Поле пароля не попадает в repr модели, ответы и логи (тесты).
- `src/tjapp/routes/notices.py`: GET `/api/notices?unread=&limit=`; POST `/api/notices/{id}/read` (чужое или несуществующее -> 404).
- `src/tjapp/routes/push.py`: GET `/api/push/key` -> `{public_key}` (503, если VAPID не настроен); POST `/api/push/subscribe` (формат `PushSubscription.toJSON()`: `{endpoint, keys:{p256dh, auth}}`, endpoint только https); POST `/api/push/unsubscribe {endpoint}` -> `{ok}`.

## Плановые пуши
- `push.notify_program_today(con, uid, today)` — «программа на сегодня»: раз в день на пользователя (`meta push_daily:*`), только если есть сессия. Читает `program_sessions` + `program_enrollments` (схема из плана: `enrollment_id, planned_day, activity_id`, `user_id, status`) с проверкой существования таблиц и колонок; нет таблиц или схема другая — тихо 0. Когда ветка программ будет слита, сверить имена колонок.
- `push.notify_rest_over(con, uid, exercise)` — «отдых закончен», только push, без записи в `user_notices`. Вызывать из роута записи подхода/таймера.
- `server_notify.py` — крон раз в час (`5 * * * *`): `push.run_daily` по пользователям с активной подпиской; до `FEPRA_NOTIFY_FROM_HOUR` (7) по локальной tz не шлёт.

## Осталось
Фронт: service worker с обработчиком `push`, кнопка включения уведомлений (iPhone — только после «На экран Домой»), баннеры из `/api/notices`. Вызов `notify_rest_over` из роутов тренировки. Сверка схемы `program_sessions` после слияния ветки программ. Замена Telegram в остальных алертах `server_sync` — намеренно не делалась.
