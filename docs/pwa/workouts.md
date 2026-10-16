# Запись тренировки через API — сервисы (фаза 3, часть 1)

Готова чистая доменная логика с тестами; HTTP-роуты, `jobs` и `deps` — следующий шаг.
Хендлеры бота не менялись (кроме реэкспортов, см. ниже).

## Сервисы (`src/tj/services/`)

Все функции — над sqlite-соединением `con`, первый аргумент после него — `uid`. Ошибки — `tj.services.errors`
(`BadRequest 400`, `Forbidden 403`, `NotFound 404`, `Invalid 422`, `QuotaExceeded 429`; у каждой есть `.status`,
`.detail`, `.code`). Роуты должны только превратить их в `HTTPException(status, detail)`.

| Модуль | Что делает |
|---|---|
| `workouts.py` | `save_result`, `get`, `recent`, `update`, `delete`, `restore`, `trash`, `confirm_maxes`, `resolve_lift`, `set_bodyweight`, `set_feel`, `build_activity`, `normalize_activity_id`, `FAMILY_VARIANTS` |
| `board.py` | `parse` (фото/текст → блоки + форма), `build` (текст доски → блоки/форма), `result_form`, `fill_template`, `gym_program` (программа зала на день) |
| `uploads.py` | `save`, `get`, `read_bytes`, `delete`, `attach_to_meal`, `uploads_root` |
| `goals.py` | `screen` (= `goals_screen_data`), `list_goals`, `add`, `archive`, `complete`, `enter_pm` |
| `errors.py` | исключения |

Вынесено в `tj/`: `tj/analysis/parse_input.py` — `parse_lift`, `parse_benchmark`, `est_1rm_for`, `parse_rpe`,
`detect_scaling`, `parse_lift_lines`. В `tjbot/handlers/record_result.py` и `record_workout.py` осталась строка-реэкспорт
(тесты хендлеров зелёные). В `lift_disambig.py` дубль `_epley` заменён на `tj.analysis.progression.epley_1rm`, а словарь
`FAMILY_VARIANTS` теперь один — в `tj.services.workouts`.

## Таблицы и миграции (`src/tj/migrations/`, только добавление)

- `0022_uploads.py` — таблица `uploads(id UUID, uid, kind, path, mime, size, sha256, created_at, deleted_at)`;
  колонка `meals.photo_path` (nullable; `photo_id` с Telegram `file_id` остаётся для бота).
- `0023_activity_trash.py` — таблица `activity_trash(uid, activity_id, row_json, results_json, deleted_at)`.

Обе с `upgrade(con)`, идемпотентны. `__init__.py` в `migrations/` и `services/` я не создавал: их заводит ветка фундамента
(без них пакеты работают как namespace, тесты запускают `importlib.import_module("tj.migrations.0022_uploads")`).

### Почему корзина, а не колонка `deleted_at` в `activities`
Строки `activities` читаются десятком запросов (отчёты, нагрузка, дашборд, питание, клуб) и вставляются бота позиционно
(`INSERT INTO activities VALUES (...)`). Колонка `deleted_at` потребовала бы фильтра в каждом запросе и переписи вставки,
иначе удалённая тренировка продолжала бы считаться. Поэтому мягкое удаление = перенос строки и её авто-ПМ в `activity_trash`
с `deleted_at`; `restore` возвращает всё обратно. Для офлайн-синка «надгробия» отдаёт `workouts.trash(...)`.
`updated_at`/`created_at` тренировки лежат в `activities.extra` (JSON).

## Идентификатор и несколько тренировок в день

`activity_id` ручной записи — клиентский UUID (строка, канонизируется в нижний регистр). Запись идемпотентна:
повторный `save_result` с тем же id заменяет строку и авто-максы (дублей нет). В день можно сколько угодно тренировок любых
видов, включая две ТА. Старые `manual-{uid}-{день}-{вид}` читаются и правятся (только свой uid), новых таких id не создаём.
Один и тот же UUID у разных пользователей — независимые записи. Перезаписать/удалить запись с часов нельзя (403).

## Слияние с часами (`tj/analysis/workouts.py`)

Раньше: ручная запись + запись часов сливались, если совпали день и семья спорта (кроссфит/ТА/Hyrox — одна) и источник разный.
Теперь, если у обеих сторон известно время старта, сливаются только **пересекающиеся по времени** интервалы (с запасом 15 мин;
у ручной записи без длительности — 60 мин). Иначе (у старых ручных записей времени нет) работает прежнее правило «по дню»,
причём при нескольких кандидатах приоритет у пересечения по времени. Результат не зависит от порядка строк.
Как получаем время: часы — `db._activity_row` теперь кладёт `start_ts` (ISO с tz) в `extra` не-ручных записей; ручная —
`start_time: "ЧЧ:ММ"` из PUT (сохраняется как `extra.start_ts`; без него время не выдумываем). `start_ts` вынимается из `extra`
при чтении (`_row`), так что «extra» отчёта не изменился, а в строке появилось поле `start_ts`. Записи часов, синкнутые до
этого изменения, времени не имеют и сливаются по дню.

## Форма результата (`board.result_form`)

`board.parse(...)` и `board.gym_program(...)` отдают вместе с блоками **форму** — данные, а не текст «заполни ___».
Она строится из тех же строк, что и текстовый шаблон бота (`render_template`), поэтому заполненную форму можно
превратить обратно в текст (`fill_template`) и отдать существующим разборщикам `summarize_filled`/`extract_maxes`:
логика метконов и максов одна на бота и API (тест сверяет пустую форму с шаблоном бота построчно).

```json
{"version": 1,
 "blocks": [
  {"index": 0, "title": "приседание со штангой на спине", "format": "emom_strength", "kind": "strength",
   "has_cap": false,
   "fields": [{"key": "0.0", "label": "раунд 1 (вес×повторы)", "type": "weight_reps", "unit": "кг×повт",
               "section": "приседание со штангой на спине", "group": null,
               "movement": "приседание со штангой на спине"}]},
  {"index": 2, "title": "WOD 1", "format": "for_time", "kind": "metcon",
   "fields": [{"key": "2.0", "label": "вес «фронтальный присед с гантелью»", "type": "weight", "unit": "кг", ...},
              {"key": "2.1", "label": "время (мм:сс)", "type": "time", "unit": "мм:сс", ...}]}]}
```

Типы полей и что принимает `form_result[key]`:

| type | значение |
|---|---|
| `weight_reps` | `"100x5"`, `100` (= 1 повтор), `[100, 5]`, `{"weight":100,"reps":5}` |
| `weight` | число кг или строка как написал атлет (`"16/24"`) |
| `time` | `"4:12"` или секунды (`252`) |
| `int` | целое ≥ 0 (круги, повторы, минута, ккал) |
| `rounds_reps` | `"5+3"`, `5`, `{"rounds":5,"reps":3}` |
| `text` | строка |

Ключ `"<блок>.<номер>"` стабилен для одних и тех же блоков (блоки клиент присылает обратно в `board.blocks`, чтобы форма и
разбор совпали). Пустое/`null` = не заполнено. Неизвестный ключ или неверный формат = `Invalid` (422), ничего не пишется.
`group` — подзаголовок внутри блока (лесенка: по движениям), `null` для основной секции.

## Разбор доски `board.parse(con, uid, *, upload_id=None, text=None, engine="fast", verbatim=False)`

Синхронная, подходит для `jobs`. Ровно один источник: `upload_id` (файл из `uploads`, только свой) или `text`.
`engine`: `fast`/`gemini` или `slow`/`claude` (`agent`). Поверх `tjbot/vision.py`: `parse_board`/`parse_text` →
`enrich_aliases` → детерминированный `parse_program` → (если доступен Claude) `verify_result_blocks` → `result_form`.
Квота ИИ — `access.llm_quota_consume(uid, con)`. Возвращает:

```
{recognized, reason (null|"quota"|"no_vision"|"not_recognized"), board_text, format, engine_used, sport,
 blocks, blocks_verified, form, template_text, annotated}
```
Фото при исчерпанной квоте / без ИИ / не распознанное → `recognized=false` и `reason` (UI предлагает ввести текст, как бот).
Текст при исчерпанной квоте разбирается без ИИ. `verbatim=true` — текст уже правил человек: без ИИ и без квоты.

## Сохранение `workouts.save_result(con, uid, activity_id, payload, *, tz="UTC", lang="ru")`

```
payload = {day, sport,                       # sport: crossfit|weightlifting|hyrox|run|bike|swim|other
           board?: {text, source: "own"|"gym", format?, blocks?, blocks_verified?},
           form_result?: {ключ: значение} | "свободный текст",
           rpe?, scaling? ("rx"|"scaled"|null), bodyweight?,
           start_time? "ЧЧ:ММ", duration_min?, distance_km?}
```
- Доска-виды (кроссфит/ТА/Hyrox): `board` + `form_result`. Форма → текст → `summarize_filled` (метконы в `extra.metcon`,
  `perf_score` = компактный счёт «8:36 · 9»), максы → `extract_maxes` → `split_lifts` → `record_lift_results`
  (пишутся сразу, как `save_filled_result` бота). Блоки берутся из `board.blocks`, иначе детерминированно из текста.
- Свободный текст без блоков (как «Записать» в боте): RPE/scaling из текста (`RPE 8`, `scaled/rx`); максы **предлагаются** в
  `proposed_maxes` (ИИ `parse_lifts` по квоте, иначе построчный разбор; `lifts_skipped_quota=true`, если квота кончилась) и
  записываются только через `confirm_maxes`.
- Бег/вело/плавание: `duration_min`, `distance_km` (темп считается), `rpe`, текст.
- `board.source = "gym"`: текст и блоки берутся **только** из подтверждённой программы зала на день (`gym_program`), клиентский
  текст игнорируется; нет программы → 422 `no_gym_program`. Зальную запись нельзя превратить в «свою» (403).
- `bodyweight` → `daily.weight_kg` за день тренировки.
- Ответ: `{activity_id, created, day, sport, score, rpe, scaling, board_source, metcon_lines, credited, ambiguous,
  proposed_maxes, lifts_skipped_quota, bodyweight}`.

### Неоднозначные лифты
`ambiguous` — список вопросов `{movement, family: "snatch"|"clean", weight, reps, variants: [{id, label}]}`.
Клиент отвечает `resolve_lift(con, uid, activity_id, movement, variant, weight, reps)`; выбор запоминается в
`extra.lift_resolutions`, поэтому повторный PUT не переспрашивает и не теряет вариант.

## Правка, удаление, чтение

- `update(con, uid, id, changes)` — как «Редактировать» в боте: `rpe`, `scaling`, `form_result` (пересчёт метконов и максов),
  `board {text}` (**только** если `board_source == "own"`, иначе 403; пересчитывает блоки), `maxes`/`maxes_text`, `bodyweight`.
  Правятся только ручные записи (`source=manual`), чужие — 404.
- `get` → поля, `board_text`, `blocks`, `form`, `form_values`, `metcon`, `maxes`, `bodyweight`, флаги `editable`/`board_editable`.
- `recent(con, uid, limit)` — последние ручные, в день по порядку записи.
- `delete` / `restore` / `trash` — мягкое удаление (см. выше); ПМ из удалённой тренировки уходят и возвращаются вместе с ней.

## Цели и ПМ (`goals.py`)
`add(kind="numeric"|"level", discipline, target)`, `list_goals`, `archive`, `complete` — **всегда с проверкой владельца**
(чужая цель = `NotFound`, ничего не меняется; в боте `archive_goal(con, id, tg_id)` молча ничего не делал). Числовая цель:
лифт — кг (`"140"`/число), бенчмарк — `мм:сс`/секунды/круги. `screen` = `goals_screen_data`. `enter_pm(discipline, value, reps=None)` —
ручной ввод ПМ: лифт `"100x3"`/число, оценка 1ПМ по Эпли, ответ с текущим уровнем (`tier`).

## Вес тела и самочувствие
`set_bodyweight(uid, kg, day=None)` — 20–500 кг, дата не позже завтра. `set_feel(uid, score)` — целое 1–10, **день по tz пользователя**
(`tz=`/`today=`), а не `date.today()` сервера, как в `self_feel.py`.

## Загрузки (`uploads.py`)
Файл → `data/uploads/<uid>/<uuid>.<ext>` (`FEPRA_UPLOADS_DIR` переопределяет корень; по умолчанию `<каталог БД>/data/uploads`).
Тип определяется по сигнатуре байтов (jpeg/png/webp/heic, «как есть», без перекодирования), заявленный mime и имя клиента не
используются; ≤ 10 МБ; путь строится только из uid и UUID и на каждом чтении проверяется на вхождение в корень. Чужая или удалённая
загрузка = `NotFound`. `attach_to_meal` пишет `meals.photo_path` вместо Telegram `file_id`. `save` возвращает `{id, url, ...}`,
`url = /api/uploads/<id>` (роут отдачи файла — в списке ниже).

## HTTP-эндпоинты (`src/tjapp/routes/`)

Все — через `deps.require_user` (cookie или Mini App). `ServiceError` → `HTTPException(status, detail)`; `tz` — из
`config.toml [user].timezone` (нет конфига — UTC); таблицы загрузок и корзины создаются лениво (`_schema.ensure`).
Примеры запросов и ответов — `docs/pwa/api-workouts-examples.md`.

| Метод и путь | Модуль | Что делает |
|---|---|---|
| `POST /api/uploads` (multipart: `file`, `kind`) | `uploads.py` | → `{id, url, mime, size, kind}`; 10 МБ проверяется по `Content-Length` и потоком (гигантский файл не принимаем), тип — по сигнатуре байтов, `Content-Type` клиента ничего не решает; ошибки 422 |
| `GET /api/uploads/{id}` | `uploads.py` | файл; владельцу или админу (`nosniff`, `private` cache), чужому 404 |
| `POST /api/board/parse` `{upload_id\|text, sport, engine, verbatim}` | `board.py` | → `{job_id}`; результат `GET /api/jobs/{id}` = блоки + форма (см. ниже). `sport` — значение `tj.models.Sport`, доска есть у crossfit/weightlifting/hyrox (иначе 422); `engine`: fast/slow/gemini/claude; чужая загрузка 404 сразу; квота ИИ внутри job |
| `PUT /api/workouts/{uuid}` | `workouts.py` | идемпотентная запись (`save_result`) |
| `GET /api/workouts/recent?limit=` | `workouts.py` | последние ручные |
| `GET /api/workouts/{uuid}` | `workouts.py` | тренировка целиком (доска, форма, значения, максы, вес тела, флаги прав) |
| `PATCH /api/workouts/{uuid}` | `workouts.py` | правка (`update`); доска — только `board_source=own` |
| `DELETE /api/workouts/{uuid}` / `POST …/restore` | `workouts.py` | мягкое удаление и возврат |
| `POST /api/workouts/{uuid}/lifts/resolve` `{movement, variant, weight, reps}` | `workouts.py` | ответ на вопрос «рывок/взятие» |
| `POST /api/workouts/{uuid}/maxes` `{maxes[]\|text}` | `workouts.py` | подтверждение/ввод максов |
| `POST /api/bodyweight` `{kg, day?}`, `POST /api/feel` `{score}` | `workouts.py` | вес тела; самочувствие 1–10 за сегодня по tz |
| `GET /api/gym-program?day=` | `workouts.py` | программа зала на день для подстановки доски → `{found:false}` или `{found:true, board_text, blocks, form, …}` |
| `GET /api/goals/items`, `POST /api/goals/items` `{kind, discipline, target}` | `goals.py` | список активных целей / новая цель. `GET /api/goals` остаётся за старым Mini App |
| `POST /api/goals/items/{id}/archive`, `…/complete`, `DELETE /api/goals/items/{id}` (= архив) | `goals.py` | чужая цель — 404 |
| `POST /api/pm` `{discipline, value, reps?}` | `goals.py` | ручной ввод ПМ |

Коды: 400 неверный id/источник, 401 нет входа, 403 нельзя править (зальная доска, запись с часов), 404 нет или чужое,
422 данные не прошли проверку. Регистрация — одной строкой на роутер в `ALL_ROUTERS`.

Заметки: на HEIC `board.parse` передаёт `media_type=image/heic` во vision как есть (Claude-vision его не примет, сработает
фолбэк на Gemini); EXIF не вычищается; чистка файлов мягко удалённых загрузок не написана; `?as=` (просмотр от админа)
для новых роутов не поддержан. Экраны PWA — на стороне фронта.
