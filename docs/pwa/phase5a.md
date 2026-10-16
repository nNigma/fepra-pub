# Фаза 5, часть А: профиль, тренер, админка, программа зала

Логика перенесена из Telegram-хендлеров в сервисы (`src/tj/services/`) и REST-роуты (`src/tjapp/routes/`).
Хендлеры бота не менялись, бот работает параллельно на той же БД. Все роуты через `require_user`/`require_pro`/`require_admin`,
ошибки JSON `{detail}` (валидация профиля дополнительно `{detail, fields:{поле: сообщение}}`).
Тесты: `tests/test_profile_service.py`, `test_api_profile.py`, `test_coach_service_api.py`, `test_admin_service_api.py`,
`test_club_service_api.py`, `test_p5a_migrations.py`; общая оснастка `tests/p5a_env.py` (tmp-БД, пользователи с ролями, клиент с сессией).

## Миграции
| № | Что |
|---|---|
| 0050 | `users.updated_at` (nullable) |
| 0060 | `wod_programs.uuid`, `updated_at`, `created_by` (nullable) + индекс `(gym, day)` |

Бот и userbot пишут в `wod_programs` без новых колонок; сервис дозаполняет `uuid` лениво при первом чтении.
Новых таблиц нет: профиль — `users`, тренер — `coach_qa`, роли — `user_roles`, программы — `wod_programs`.

## Профиль и онбординг (`tj/services/profile.py`, `routes/profile.py`)
| Метод и путь | Что |
|---|---|
| `GET /api/profile` | профиль + `watch` + `available_watch_actions`; 404, если строки `users` нет |
| `PATCH /api/profile` | любое подмножество: `nick`(1–40), `height_cm`(100–250), `weight_kg`(20–400), `sex`(m/f), `age`(10–100), `gym`(из `/api/gyms` или `solo`/`other`), `lang`(ru/en), `goal`(`botdb.GOALS`), `city`(1–60), `astro`(bool). 422 `{detail, fields}`; при ошибке не пишется ничего. Только свой профиль (`?as=` игнорируется) |
| `GET /api/gyms` | `{gyms:[{name,is_default,members}], special:["solo","other"]}` |
| `GET /api/onboarding` | `{complete, missing[], optional_missing[], ranges}`; обязательные: nick, height_cm, weight_kg, sex, age, gym |

Валидация одна: `profile.validate_fields` (в боте она дублировалась в onboarding/profile_edit). Диапазон веса 20–400 новый (бот принимал любое число).
`available_watch_actions(profile)` — правило «один источник часов» из `menu._profile_kb`: пока подключён Garmin/Samsung/WHOOP/Apple,
подключение остальных скрыто; у Garmin с `expired` доступен `garmin_connect`. Действия — строки `garmin_connect|sync|history|disconnect`,
`samsung_connect|disconnect`, `whoop_connect|sync|disconnect`, `apple_connect|disconnect`.
Пользователю без строки `users` PATCH создаёт её, если передан `nick`.

## ИИ-тренер (`tj/services/coach.py`, `routes/coach.py`, только Pro)
- `POST /api/coach/ask {q ≤2000}` → `{job_id}`; результат задачи `{id, answer, engine, ts}`. Не-админ: `COACH_DAILY_LIMIT=3` вопроса в день
  и суточная квота ИИ (`access.llm_quota_consume`), иначе 429. Если предыдущий вопрос ещё думает, возвращается его `job_id` (квота второй раз не списывается).
  Пустой ответ движка — ошибка задачи (квота уже списана, как в боте).
- `GET /api/coach/recent?limit=5` (≤20) — `[{ts, lang, question, answer, engine}]`.
- Константа лимита продублирована из `handlers/coach.py` (импорт тянул бы telegram), совпадение проверяет тест.

## Админка (`tj/services/admin.py`, `routes/admin.py`, только админ)
| Метод и путь | Что |
|---|---|
| `GET /api/admin/users?q=` | все с профилем или ролью: `{id,nick,gym,created_at,roles:{allowlist,pro,admin,coach,coach_gym}}` |
| `PUT /api/admin/users/{id}/roles` | подмножество `{allowlist,pro,admin: bool, coach: "<зал>"|null}` |
| `DELETE /api/admin/users/{id}` | убрать доступ (allowlist, pro, coach, сессии); история остаётся |
| `GET/POST /api/admin/gyms` | список (участники, тренеры) / добавить `{name}` (≤60 симв., одна строка, не `solo`/`other`, без дублей; лимита callback_data больше нет) |
| `GET/POST /api/admin/coaches`, `DELETE /api/admin/coaches/{id}` | тренеры; назначить `{user_id, gym}` |
| `GET /api/admin/stats?days=` | `{days, since, total, users:[{id,nick,total,actions:[{key,label,n}]}]}`; без `days`/0 — всё время |
| `POST /api/admin/review` | «Разбор полётов» → `{job_id, already_running}`; 503 без LLM |

Жёсткие правила (409): нельзя снять `admin` у последнего админа (в том числе комбинированным запросом — ничего не применяется);
нельзя убрать `allowlist` у админа и удалить админа. Выдача `admin` добавляет и `allowlist`. Снятие `allowlist` отзывает сессии.
Для этого в `tjbot/access.py` добавлен `remove_admin`. Инвайты остались в `routes/auth.py`.
Флаг «уже идёт» общий для всех админов (по таблице `jobs`, `kind=admin_review`); `GET /api/jobs/{id}` отдаёт задачу только запустившему.
Результат задачи: `{ok, error, users:[{id, ok, skipped, errors, summary}]}` (как `_review_report`, но данными).

## Программа зала (`tj/services/club.py`, `routes/club.py`)
Права: смотреть свой зал и его статистику — любой пользователь с доступом; чужой зал (`?gym=`) — только админ;
управлять (правка, черновики, словарь, атлеты) — админ или тренер этого зала (`target_gym`/`can_manage` из бота, per-gym вместо «любой тренер»).

| Метод и путь | Что |
|---|---|
| `GET /api/club/program?day=&gym=` | `{gym, day, program, last_day, can_manage}`; `day` по умолчанию сегодня (tz из config.toml) |
| `PUT /api/club/program {day, raw_text, gym?}` | заменить программу на день (подтверждённая); повтор идемпотентен, `uuid` сохраняется. Ответ `{program, unknown, job_id}` |
| `POST /api/club/program/preview {raw_text}` | разбор без сохранения: `format, canon, unknown, annotated` |
| `GET /api/club/pending` | ожидающие черновики (админ — все залы, тренер — свой) |
| `POST /api/club/pending/{id}/confirm {raw_text?}` | подтвердить (с правкой текста пересчитываются формат/движения); повтор безопасен |
| `DELETE /api/club/pending/{id}` | отклонить неподтверждённый черновик |
| `GET /api/club/stats` | частота движений `[{canon,count,name}]` |
| `GET /api/club/athletes?days=30` | атлеты зала и число тренировок за период (SQL вынесен из `_athletes_text`) |
| `GET /api/club/dictionary`, `POST /api/club/aliases {pairs}`, `POST /api/club/movements/resolve {phrase, name?}` | словарь движений: без `name` — новое движение «как есть», с `name` — сопоставить существующему |

`job_id` из PUT — фоновая выверка блоков шаблона (`vision.verify_result_blocks`), только если блоки распознаны и движок по подписке готов;
в отличие от бота программа сохраняется сразу, `blocks` дописываются задачей (только если строку за это время не заменили).
Сервис: `add_from_board(con, uid, gym, day, raw_text, confirm=False, source="photo")` — точка входа для доски, уже распознанной vision:
`confirm=False` кладёт черновик в «ожидающие» (замена userbot), `True` сразу заменяет программу на день.
`strip_wrappers`, `slug`, SQL атлетов продублированы из `handlers/club.py` (хендлеры не менялись).

## Осталось
- Фото доски (загрузка + vision → `add_from_board`) — ветка тренировок; `ingest_universe` отключается вместе с ботом.
- Роут на полную замену/переименование залов и удаление зала (в боте этого не было).
- `?as=` для `/api/club/*` не поддержан намеренно: права считаются по вошедшему.
- Уведомление тренеру о новом черновике (`push.notify_user`) — когда появится источник черновиков.
- Фронт всех экранов фазы 5А.
