# Фаза 5, часть Б: питание и соревнования (сервисы + REST)

Хендлеры бота не менялись. Отчётные GET (`/api/nutrition`, `/api/nutrition/days`, `/api/competitions`,
`/api/competition/{id}`) остались в `api.py`. Примеры JSON для фронта: `api-meal-comp-examples.md`.

## Миграции
| № | Что |
|---|---|
| 0050 `meals_api` | `meals.client_uuid` (nullable) + частичный уникальный индекс `(tg_id, client_uuid)`; `meals.photo_path` (уже даёт 0022, здесь страховка) |
| 0060 `comp_api` | индексы `comp_participants(division_id, tg_id)`, `comp_results(stage_id, athlete)`, уникальный `comp_stages(division_id, source_ref)` (для идемпотентного подтверждения этапов с фото) |

## Питание (`tj/services/meals.py`, `tjapp/routes/meals.py`, только Pro/admin)
Поток как в боте, но без состояния на сервере: клиент держит черновик и накопленные уточнения.

| Метод и путь | Что |
|---|---|
| `POST /api/meals/parse` `{upload_id \| text, correction?, notes?}` | -> `{job_id}`; результат job: `{recognized, reason, draft, notes, source}` |
| `POST /api/meals` `{draft, day?, ts?, uuid?, upload_id?, text?}` | сохранить -> `{created, meal}` |
| `GET /api/meals?day=` | приёмы дня + тоталы + вода |
| `PUT /api/meals/{id}` `{draft, day?, ts?}` | правка = замена (delete+add одной транзакцией, id/uuid/фото/описание/время сохраняются) |
| `POST /api/meals/{id}/reparse` `{correction, notes?}` | перепарс по сохранённому файлу (иначе по описанию) -> `{job_id}` |
| `DELETE /api/meals/{id}` | удалить |
| `POST /api/water` `{delta_ml, day?}` / `GET /api/water?day=` | вода дня (мл; в БД по-прежнему литры) |

Решения:
- **Фото** хранится как `meals.photo_path` (путь из `uploads`), Telegram `photo_id` для API-приёмов пустой; клиент видит `photo_url`
  (`/api/uploads/{id}`), а `photo_id`/`photo_path` наружу не отдаются. Приёмы из бота с одним `photo_id` не перепарсить (нет файла) —
  только если есть описание в `note`.
- **Уточнения**: `notes` — список накопленных; результат отдаёт обновлённый `notes`, клиент присылает его в следующем запросе
  вместе с новым `correction`. ИИ получает `"; ".join(notes)`, как `meal_notes` в боте.
- **Квота** `llm_quota_consume` (админ без лимита) списывается на каждый вызов ИИ, включая уточнения. В боте уточнения бесплатны, но
  в API это позволило бы обойти квоту, отправляя `correction`. Исчерпана -> `recognized=false, reason="quota"`;
  нет ИИ на фото -> `no_vision`; не разобралось -> `not_recognized`. Короткий текст (<3 знаков) -> ошибка job, квота не тратится.
- **Идемпотентность**: `POST /api/meals` с тем же `uuid` возвращает уже записанный приём (`created=false`). Без `uuid` каждый
  запрос — новый приём. `PUT` того же тела даёт то же состояние.
- **Черновик от клиента не доверенный**: сохранение прогоняет его через `vision._valid_meal` (тоталы пересчитываются, мусор -> 422).
- **Время**: день и «сегодня» по tz из `config.toml [user].timezone`; приём сегодня — текущее время, другого дня — `T12:00:00`
  (как `_meal_ts` бота); день позже завтрашнего -> 422.
- Вода не идемпотентна (это приращение); `delta_ml` от -5000 до 5000, не 0; итог не ниже 0.

## Соревнования (`tj/services/competitions.py`, `tjapp/routes/competitions.py`, любой вошедший)
Контекст «заполнения» бота (`user_data["fill"]`) — явные параметры: `event_id` в пути/теле, `division_id` (можно опустить, если вы
участвуете в одном дивизионе старта; иначе 422 «укажите division_id»), `athlete` (по умолчанию «Я», `comp_results.athlete` остаётся строкой).

| Метод и путь | Что |
|---|---|
| `GET /api/comp/list` | `{mine, others}` — мои и чужие старты (как «Другие старты» бота) |
| `GET /api/comp/events/{id}` | старт, дивизионы, этапы; результаты только в своих дивизионах |
| `POST /api/comp/events` `{name, date, city, category \| division, force_new?}` | создать старт + дивизион + участие; дубль -> `created=false, duplicate=true, candidates` |
| `POST /api/comp/events/{id}/join` `{division_id?}` | вступить (идемпотентно) |
| `POST /api/comp/events/{id}/stages` `{text, division_id?}` | этап текстом |
| `POST /api/comp/events/{id}/stages/parse` `{upload_id, division_id?}` | фото этапов -> `{job_id}` (превью, ничего не пишет) |
| `POST /api/comp/stages/confirm` `{event_id, stages, division_id?}` | сохранить распознанные этапы |
| `POST /api/comp/events/{id}/results` `{text, athlete?, division_id?, stage_idx?}` | результат текстом «значение, место[, размер поля]» |
| `POST /api/comp/events/{id}/results/parse` `{upload_id, athlete?, division_id?}` | фото таблицы -> `{job_id}` (строки с сопоставленными этапами) |
| `POST /api/comp/results/confirm` `{event_id, rows, athlete?, division_id?}` | сохранить строки |
| `GET /api/comp/events/{id}/total` | предложение итога (сумма мест) — добавлено сверх списка, нужно экрану «итог» |
| `PUT /api/comp/events/{id}/total` `{total_points?, final_place?}` | без значений — принять предложение; оба — вручную |
| `PUT /api/comp/divisions/{id}/field_size` `{field_size}` | размер поля |

Решения:
- **Права**: смотреть чужие старты можно; этапы, результаты, размер поля — участник дивизиона или админ (иначе 403); итог — только по
  своему участию (админ-не-участник получает 403). Чужой/несуществующий `upload_id` -> 404.
- **Дедуп старта**: `find_events_by_city_date` (город без регистра, дата внутри существующего старта). Клиент показывает
  кандидатов и вызывает `join`, либо повторяет POST с `force_new=true`.
- **Дата**: `ДД.ММ.ГГГГ`, `ДД.ММ` (текущий год) или ISO. Категории `newbie/pro/int/rx` (`Новички/PRO/INT/RX`) либо своё `division`.
- **Эвристики вынесены в чистые функции** (те же правила, что в хендлере): `parse_result_text`, `pick_stage_for_text_result`
  (последний этап без результата атлета, иначе последний), `map_result_rows` (номер этапа == idx, затем точное имя, затем позиция строки).
- **Размер поля** из текстового результата пишется, только если у дивизиона он ещё пуст (как в боте); явный `PUT` перезаписывает.
- **Идемпотентность**: `stages/confirm` — по `source_ref` (`upload:<id>#<n>`, его кладёт parse); `results/confirm` и текстовый
  результат с явным `stage_idx` заменяют результат атлета на этапе. Текстовый результат без `stage_idx` ведёт себя как в боте
  (везде заполнено -> добавляется вторая строка на последний этап).
- **Фото**: как у доски — job, квота `llm_quota_consume`, `reason` = `quota | no_vision | not_recognized`.

## Тесты
`tests/test_api_meals.py` (33), `tests/test_api_comp.py` (29), общие помощники `tests/api_common.py`. ИИ мокается
(`vision.parse_meal*`, `parse_stages`, `parse_results`, `has_vision`).

## Осталось
- Экраны PWA (запись еды, старты); `POST /api/uploads` живёт в ветке тренировок.
- Приём пищи не хранит уточнения между сессиями (только на клиенте); отдельного «черновика» на сервере нет.
- Удаление старта/дивизиона/этапа/результата через API не делалось (в боте тоже нет).
- Цель питания уже в профиле (другая ветка).
