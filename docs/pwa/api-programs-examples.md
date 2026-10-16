# API программ: примеры для фронтенда

Ответы ниже сняты с реального `TestClient` (обрезаны, где длинно). Все пути под сессией `fepra_session`
(или `X-Init-Data`), только свои данные, чужое — 404; админ подставляет `?as=<id>`.
Дата «сегодня» считается на сервере по `config.toml [user].timezone`; клиент может передать свою: `?today=YYYY-MM-DD`
(рекомендуется отправлять локальную дату устройства). Логика и правила — `docs/pwa/programs.md`.

## Эндпоинты

| Метод и путь | Что |
|---|---|
| `GET /api/programs/tree` | дерево каталога, `planned` → `soon: true` |
| `GET /api/programs/{slug}` | карточка: шаблон, недели, `requirements` (опорные веса по лифтам), `enrollment_id` (активная запись или `null`) |
| `POST /api/programs/{slug}/enroll` | `{start_day, base_maxes?, level?, weekdays?, id?}` → запись и расписание |
| `GET /api/enrollments[?status=]` | `{enrollments: [...]}` |
| `GET /api/enrollments/{id}` | запись: `base_maxes`, счётчики сессий, `next_session`, `refresh` (предложения «обновить опорные?») |
| `GET /api/enrollments/{id}/sessions` | список сессий записи для календаря |
| `GET /api/enrollments/{id}/today` | `{state, session}`, state: `today` / `in_progress` / `upcoming` / `overdue` / `none` / `paused` / `cancelled` / `done` |
| `POST /api/enrollments/{id}/refresh-base` | `{lifts?}` (тело можно не слать) применить предложение «обновить опорные?»; без списка — все из `refresh` |
| `POST /api/programs/enrollments/{id}/pause` / `resume` / `cancel` | смена статуса (короткий алиас: `/api/enrollments/{id}/pause…`) |
| `GET /api/sessions/{id}` | сессия «у помоста» |
| `PUT /api/sessions/{id}/sets/{set_id}` | `{done_kg, reps, ok, note, exercise?, ts?}` идемпотентно |
| `POST /api/sessions/{id}/checkin` | `{energy 1..5, tired, sleepy, joint, ill}` |
| `POST /api/sessions/{id}/finish` | `{rpe 1..10, feel, activity_id?}` (`activity_id` — клиентский UUID) |
| `GET /api/lifts/{lift}/trend?window=7` | тренд «максимум дня» по лифту |

Ошибки всегда JSON `{"detail", "code"}`:
`not_found` 404, `conflict` 409 (уже есть активная запись, неверный переход статуса), `unavailable` 409 (программа «скоро»),
`closed` 409 (сессия завершена, запись на паузе или отменена), `needs_input` 422 (+ `items`), `invalid` 422, `template` 500
(битый шаблон). Ошибки записи тренировки (например `bad_id` 400 при `activity_id`, не UUID) приходят с тем же форматом.

## 1. Дерево

```json
GET /api/programs/tree
{"tree": [
  {"slug": "crossfit", "kind": "sport", "title_ru": "Кроссфит", "title_en": "CrossFit", "status": "planned",
   "soon": true, "sort": 10, "template_slug": null, "parent": null,
   "children": [{"slug": "crossfit-strength-531", "kind": "program", "title_ru": "Силовой цикл (5/3/1-стиль)",
                 "soon": true, "children": [], "...": "..."}]},
  {"slug": "weightlifting", "title_ru": "ТА", "status": "active", "soon": false,
   "children": [{"slug": "bulgarian", "kind": "system", "title_ru": "Болгарская система", "children": [
      {"slug": "bulgarian-adaptation", "kind": "program", "template_slug": "bulgarian-adaptation", "soon": false},
      {"slug": "bulgarian-peak-8w", "kind": "program", "template_slug": "bulgarian-peak-8w", "soon": false}]}]},
  {"slug": "running", "title_ru": "Бег", "soon": true, "children": ["… 5 программ planned"]}
]}
```
Узел с `soon: true` рисуем серым с подписью «скоро», записываться нельзя (`enroll` → 409 `unavailable`).

## 2. Карточка программы и опорные веса

```json
GET /api/programs/bulgarian-peak-8w?today=2026-09-28
{"slug": "bulgarian-peak-8w", "title_ru": "Цикл до теста максимума (8 недель)", "soon": false,
 "template": {"version": 1,
   "title": {"ru": "Болгарская система: 8 недель до теста максимума", "en": "…"},
   "summary": {"ru": "8 недель: 1 объёмная, 5 средних, 2 высокие. …", "en": "…"},
   "params": {"weeks": 8, "session_minutes": [30, 60], "days_per_week": [4, 5]},
   "required_lifts": ["squat_snatch", "clean_and_jerk", "back_squat"], "optional_lifts": ["front_squat"],
   "rules": {"on_miss": "drop_5kg_continue", "deload_pct": 70, "illness_drop_pct": 10},
   "weeks": [{"week": 1, "type": "volume", "title": {"ru": "Неделя 1: объёмная", "en": "Week 1: volume"},
              "note": {"ru": "…", "en": "…"}, "sessions": 4}, "… 8 недель"]},
 "requirements": {
   "lifts": [
     {"lift": "squat_snatch", "name": {"ru": "Рывок в сед", "en": "Squat snatch"}, "required": true,
      "reference": {"lift": "squat_snatch", "kg": null, "source": "needs_input", "stale": false,
                    "options": {"careful": 34, "normal": 48, "experienced": 66},
                    "question": {"ru": "Твой максимум: рывок в сед?", "en": "Your max for squat snatch?"},
                    "note": "Нет данных. Введи максимум или выбери стартовый уровень."}}],
   "needs_input": ["squat_snatch", "clean_and_jerk", "back_squat", "front_squat"],
   "needs_test": ["squat_snatch", "clean_and_jerk", "back_squat"]},
 "enrollment_id": null}
```

`reference.source`:

- `best`: лучший реальный результат (`kg`, `day`, `stale` если старше 60 дней).
- `derived`: оценка по родственному лифту (`from: ["clean_and_jerk"]`).
- `needs_input`: `kg: null`, спросить `question`, предложить `options` (три кнопки: осторожный / обычный / опытный; `options` нет, если в профиле не заполнены пол и вес).

Экран записи: если `needs_input` пуст, кнопка «Записаться» сразу. Иначе форма «Твой максимум?» по каждому лифту из `needs_input` с полем кг и тремя кнопками из `options`.
`needs_test` непустой: показать «Первая тренировка будет тестом максимума».

## 2а. Календарь записи

```json
GET /api/enrollments/{id}/sessions
{"sessions": [
  {"id": "e927f447-…", "planned_day": "2026-09-28", "week": 1, "idx": 1, "kind": "normal", "status": "done",
   "activity_id": "1e28e646-…", "title": {"ru": "Рывок + присед", "en": "Snatch + squat"}, "week_type": "volume",
   "sets_done": 9, "sets_total": 9},
  {"id": "bf36b9…", "planned_day": "2026-09-29", "week": 1, "idx": 2, "kind": "normal", "status": "planned",
   "activity_id": null, "sets_done": 0, "sets_total": 8}]}
```
Порядок по дате. `week: 0` — тест-сессия «день 0». `sets_done` — плановые подходы с внесённым весом, промахи (`ok: false`) не считаются.

## 2б. Запись и предложение обновить опорные

`GET /api/enrollments/{id}` кроме полей записи отдаёт `refresh`. Он не зависит от ответа `finish`, кнопку «Обновить опорные?» рисуем по нему:

```json
{"id": "…", "status": "active", "base_maxes": {"back_squat": {"kg": 140, "source": "best"}},
 "refresh": [{"lift": "back_squat", "base_kg": 140, "new_kg": 145, "delta_kg": 5,
              "ru": "Новый максимум по «Присед»: 145 кг (база 140). Обновить опорные?", "en": "…"}]}
```
Пустой список: предлагать нечего (макс выше базы меньше чем на 2.5 кг). В `GET /api/enrollments` (список) `refresh` не считается.
`POST /api/enrollments/{id}/refresh-base` без тела или с `{"lifts": ["back_squat"]}` возвращает запись с `refreshed` и уже пустым (или оставшимся) `refresh`.

## 3. Запись

```json
POST /api/programs/bulgarian-peak-8w/enroll?today=2026-09-28
{"start_day": "2026-09-28", "level": "normal", "id": "<клиентский UUID записи>"}
```
Вместо `level` можно `"base_maxes": {"squat_snatch": 80, "clean_and_jerk": 100}` (кг, остальное выведется). `weekdays: [0,2,4,5]` — свои дни недели (0 = пн).
Повтор с тем же `id` безопасен (`existing: true`). Ответ:

```json
{"id": "a3e70469-…", "program_slug": "bulgarian-peak-8w", "template_version": 1, "start_day": "2026-09-28",
 "status": "active", "level": "normal",
 "base_maxes": {"squat_snatch": {"kg": 48, "source": "starter", "stale": false, "level": "normal",
                                  "note": "Стартовый уровень «обычный» по нормативам: 48 кг. Уточнится тест-сессией."},
                "clean_and_jerk": {"kg": 60, "source": "starter", "…": "…"}},
 "sessions": {"total": 39, "planned": 39},
 "next_session": {"id": "2b3aa256-…", "planned_day": "2026-09-28", "week": 0, "idx": 0, "kind": "test"},
 "test_lifts": ["squat_snatch", "clean_and_jerk", "back_squat"], "existing": false}
```

Без максов и без `level`:

```json
422 {"detail": "нужны опорные веса", "code": "needs_input",
     "items": {"squat_snatch": {"kg": null, "source": "needs_input",
                                "options": {"careful": 34, "normal": 48, "experienced": 66},
                                "question": {"ru": "Твой максимум: рывок в сед?", "en": "Your max for squat snatch?"}},
               "clean_and_jerk": {"…": "…"}}}
```

## 4. «Сегодня» и экран у помоста

```json
GET /api/enrollments/{id}/today?today=2026-10-12
{"state": "today", "enrollment_id": "…", "date": "2026-10-12",
 "session": {"id": "429dff7c-…", "planned_day": "2026-10-12", "week": 3, "idx": 1, "kind": "normal", "status": "planned",
   "week_type": "medium", "week_title": {"ru": "Неделя 3: средняя", "en": "Week 3: medium"},
   "title": {"ru": "Рывок (тяжёлый) + присед", "en": "Snatch (heavy) + squat"}, "minutes": 30,
   "checkin": null,
   "adjust": {"level": "none", "delta_pct": 0, "cap_pct": null, "signals": [], "postpone_advised": false},
   "why": null, "why_en": null, "activity_id": null, "extra_sets": [], "misses": [],
   "blocks": [{"title": {"ru": "Основная часть", "en": "Main work"}, "exercises": [
     {"id": "snatch", "lift": "squat_snatch", "name": {"ru": "Рывок в сед", "en": "Squat snatch"}, "sets": [
       {"id": "1c5464ed-…", "n": 0, "kind": "ladder", "pct": 50, "planned_kg": 40,   "rest_sec": 60,
        "reps": 1, "done_kg": null, "ok": null, "note": null, "ts": null},
       {"id": "3ae25323-…", "n": 1, "kind": "ladder", "pct": 60, "planned_kg": 47.5, "rest_sec": 60, "reps": 1, "…": "…"},
       {"id": "b312005f-…", "n": 2, "kind": "ladder", "pct": 70, "planned_kg": 55,   "rest_sec": 90, "reps": 1, "…": "…"}]},
     {"id": "squat", "lift": "back_squat", "name": {"ru": "Присед на спине", "en": "Back squat"}, "sets": ["…"]}]}]}}
```

Что рисуем:

- Заголовок: `title`, `week_title`, `minutes`; для `kind: "test"` бейдж «Тест максимума».
- По упражнению карточка, внутри строки подходов. Подход: `planned_kg × reps`, `pct` мелко; `kind`: `ladder` (лесенка), `work` (рабочий), `day_max` («максимум дня»), `attempt` (попытка теста).
- Отметка подхода: кнопки «вышло» (`ok: true`, `done_kg` = `planned_kg` по умолчанию) / «не вышло» (`ok: false`) и правка веса.
- Таймер отдыха: после отметки подхода запускается отсчёт `rest_sec` (секунды из шаблона, у следующего подхода стоит свой отдых; если в шаблоне не задан — сервер подставил по умолчанию, поле всегда есть). Клиент показывает обратный отсчёт и вибрирует по нулю.
- `why` / `why_en` (если не `null`): плашка над списком, например «Чек-ин: устал, плохо спал. Лёгкий день: веса не выше 70% от максимума.»
- `week_note` (может быть пустой строкой): подсказка недели.
- `extra_sets`: подходы, добавленные вручную (упражнение вне плана), показываются отдельным блоком «Дополнительно».
- Внеплановый подход: `PUT` с новым клиентским UUID и `exercise` (канонический лифт, например `"back_squat"`).

## 5. Подход

```json
PUT /api/sessions/{sid}/sets/1c5464ed-…
{"done_kg": 40, "reps": 1, "ok": true}
→ {"set": {"id": "1c5464ed-…", "exercise": "squat_snatch", "planned_kg": 40.0, "done_kg": 40.0, "reps": 1, "ok": true,
           "note": null, "ts": "2026-10-12T17:20:11Z"},
   "changed": [], "why": null, "session_status": "in_progress"}
```

Промах, правило on_miss («не вышло → −5 кг и продолжай»):

```json
PUT /api/sessions/{sid}/sets/b18c42d5-…   {"done_kg": 60, "reps": 1, "ok": false}
→ {"set": {"id": "b18c42d5-…", "planned_kg": 60.0, "done_kg": 60.0, "ok": false, "…": "…"},
   "changed": ["b9a502f3-…", "a3449f28-…"],
   "why": {"ru": "Не вышло: остальные подходы по «Рывок в сед» на 5 кг легче.",
           "en": "Missed: the remaining squat snatch sets are 5 kg lighter."},
   "session_status": "in_progress"}
```
`changed`: id подходов, у которых сервер пересчитал `planned_kg` (обновить их в списке, `why` показать тостом). Другие лифты и уже отмеченные подходы не меняются.
Повтор того же `PUT` ничего не ломает, исправление на `ok: true` возвращает вес. В тест-сессии правило не действует.
`PUT` в завершённую сессию или запись на паузе/отмене → 409 `closed`.

**Частичное обновление и сброс.** Поля, которых нет в теле, остаются как были: `{"note": "легко"}` не трогает вес и отметку,
`{"done_kg": 42.5}` не сбрасывает `ok`. Явный `"ok": null` без `done_kg` сбрасывает отметку: подход снова неотмеченный
(`ok: null`, `done_kg: null`, `ts: null`), промах снимается, вес остальных подходов пересчитывается заново от базы (id в `changed`).
`{"ok": null, "done_kg": 60}` — не сброс (вес внесён без отметки). Сброс внепланового подхода (`extra_sets`) удаляет его.
Кнопка «отменить отметку» = `PUT` с `{"ok": null}`.

## 6. Чек-ин

```json
POST /api/sessions/{sid}/checkin   {"tired": true, "sleepy": true}
→ полный вид сессии (как GET) с пересчитанными `planned_kg` и:
  "why": "Чек-ин: устал, плохо спал. Лёгкий день: веса не выше 70% от максимума.",
  "adjust": {"level": "cap", "delta_pct": 0, "cap_pct": 70.0, "signals": ["tired", "sleepy"], "postpone_advised": false},
  "checkin": {"tired": true, "sleepy": true}
```
Уровни `adjust.level`: `none`, `minus5` (−5 пунктов процента), `illness` (−10), `cap` (потолок 70%). Пустой `{}` снимает поправку.
У тест-сессии веса не меняются, а `postpone_advised: true` (показать «лучше перенести тест»).
Отмеченные подходы не пересчитываются. `energy` вне 1..5 → 422.

## 7. Финиш

```json
POST /api/sessions/{sid}/finish?today=2026-10-12   {"rpe": 7, "feel": 4, "activity_id": "<UUID тренировки>"}
→ {"session_id": "…", "status": "done", "already": false, "activity_id": "…",
   "maxes": [{"lift": "squat_snatch", "kg": 60.0, "reps": 1}],
   "refresh": [{"lift": "squat_snatch", "base_kg": 60, "new_kg": 65, "delta_kg": 5,
                "ru": "Новый максимум по «Рывок в сед»: 65 кг (база 60). Обновить опорные?", "en": "…"}],
   "base_updated": [], "enrollment_done": false}
```

- `maxes`: лучшие удавшиеся подходы, они уже попали в уровни (`discipline_results`, source `auto`). Тренировка (тип «ТА») лежит в обычной ленте, `activity_id` тот же.
- `refresh`: предложение «обновить опорные?». Показать баннер с кнопкой, которая вызывает `POST /api/enrollments/{id}/refresh-base` (тело `{}` или `{"lifts": ["squat_snatch"]}`). Сами опорные не меняются.
- `base_updated`: у тест-сессии лифты, ставшие новой базой.
- Повторный `finish` возвращает `already: true` и тот же `activity_id`.

## 8. Тренд «максимум дня»

```json
GET /api/lifts/squat_snatch/trend?window=7
{"lift": "squat_snatch", "points": [{"day": "2026-10-05", "kg": 60.0, "session_id": "…"},
                                    {"day": "2026-10-12", "kg": 65.0, "session_id": "…"}],
 "delta_kg": 5.0, "trend": "up", "best": 65.0}
```
`trend`: `up` / `flat` / `down` / `none` (меньше двух точек). Это последние `window` тренировок с данными, только удавшиеся подходы.

## 9. Пауза и отмена

```json
POST /api/programs/enrollments/{id}/pause   → {"id": "…", "status": "paused", …}
POST /api/programs/enrollments/{id}/resume  → {"status": "active", …}
POST /api/programs/enrollments/{id}/cancel  → {"status": "cancelled", …}
409 {"detail": "из статуса 'active' нельзя: resume", "code": "conflict"}
```
`today` на паузе: `{"state": "paused", "session": null}`. Отмена не удаляет историю: сессии читаются. После отмены можно записаться снова.
