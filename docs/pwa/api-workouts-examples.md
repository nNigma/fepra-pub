# Запись тренировки: примеры запросов и ответов для фронта

Реальные ответы, снятые с работающих роутов (Vision замокан; `blocks` в PUT — это ровно то, что вернул job, ниже
сокращено до `[...]`). Аутентификация — cookie `fepra_session` (или `X-Init-Data` в Mini App); все пути same-origin.
Ошибки — `{"detail": "текст"}`. Сценарий целиком: **загрузка → parse (job) → форма → PUT → вопросы по лифтам → resolve**.

## 1. Загрузка фото доски
`POST /api/uploads`, `multipart/form-data`: поле `file` (jpeg/png/webp/heic, ≤ 10 МБ), поле `kind` = `board|meal|other`.
```json
{"id": "450afa76-58a8-4f60-b5bd-b58cc876b64d", "url": "/api/uploads/450afa76-58a8-4f60-b5bd-b58cc876b64d",
 "mime": "image/jpeg", "size": 68, "kind": "board"}
```
Ошибки 422: `файл больше 10 МБ`, `поддерживаются jpeg, png, webp, heic` (тип определяет сервер по содержимому, а не по
`Content-Type`), `пустой файл`. Показать картинку: `<img src="/api/uploads/{id}">` (только владельцу и админу).

## 2. Разбор доски (job)
`POST /api/board/parse` — тело: `{"upload_id": "…"}` **или** `{"text": "…"}`, плюс `sport` (crossfit|weightlifting|hyrox),
`engine` (`fast` — Gemini, `slow` — Claude), `verbatim` (true — текст уже поправлен человеком, без ИИ и квоты).
```json
{"text": "2 ТА.\n- Е2МОМх3х3х80%\nрывок\n\n3 WOD\n3 сета:\n- 20 бёрпи", "sport": "weightlifting", "engine": "fast"}
```
→ `{"job_id": "b6caf2d3-6303-46f0-b74f-561bc142e082"}`. Опрашивать `GET /api/jobs/{job_id}` (`status`: pending|running|done|error):
```json
{"id": "b6caf2d3-…", "status": "done", "error": null, "result": {
  "recognized": true, "reason": null,
  "board_text": "2 ТА.\n- Е2МОМх3х3х80%\nрывок\n\n3 WOD\n3 сета:\n- 20 бёрпи",
  "format": "other", "engine_used": null, "sport": "weightlifting",
  "blocks": [{"header": "ТА", "format": "emom_strength", "rounds": 3, "reps": 3, "has_cap": false,
              "movements": [{"name": "рывок", "canon": "snatch", "canons": ["snatch"], "weighted": true}],
              "benchmark": null, "scheme": null, "work_min": null, "rest_min": null},
             {"header": "WOD 1", "format": "for_time", "rounds": 3, "has_cap": false,
              "movements": [{"name": "бёрпи", "canon": "burpee", "canons": ["burpee"], "weighted": false}], "…": "…"}],
  "blocks_verified": false,
  "form": {"version": 1, "blocks": [
    {"index": 0, "title": "рывок", "format": "emom_strength", "kind": "strength", "has_cap": false,
     "fields": [
       {"key": "0.0", "label": "раунд 1 (вес×повторы)", "type": "weight_reps", "unit": "кг×повт",
        "section": "рывок", "group": null, "movement": "рывок"},
       {"key": "0.1", "label": "раунд 2 (вес×повторы)", "type": "weight_reps", "unit": "кг×повт", "section": "рывок", "group": null, "movement": "рывок"},
       {"key": "0.2", "label": "раунд 3 (вес×повторы)", "type": "weight_reps", "unit": "кг×повт", "section": "рывок", "group": null, "movement": "рывок"}]},
    {"index": 1, "title": "WOD 1", "format": "for_time", "kind": "metcon", "has_cap": false,
     "fields": [{"key": "1.0", "label": "время (мм:сс)", "type": "time", "unit": "мм:сс",
                 "section": "WOD 1", "group": null, "movement": null}]}]},
  "template_text": "рывок:\n  раунд 1 (вес×повторы):\n  …\nWOD 1:\n  время (мм:сс):",
  "annotated": "2 ТА.\n- Е2МОМх3х3х80% (3 раунда по 3 повторения)\nрывок\n\n3 WOD\n3 сета: (3 раунда)\n- 20 бёрпи"}}
```
- `annotated` — текст доски с пометками раундов для экрана «проверьте распознавание»; правку текста снова отправляем в parse с
  `verbatim: true`.
- Фото не разобралось / нет ИИ / кончилась квота: `status: done`, но `result.recognized = false` и
  `reason` = `not_recognized` | `no_vision` | `quota` (тогда предложить ввести текст доски).
- Рисуем форму по `form.blocks[].fields[]`: `type` → виджет (`weight_reps` — вес и повторы, `time` — мм:сс, `weight` — кг,
  `int` — число, `rounds_reps` — круги и повторы, `text`), `group` — подзаголовок внутри блока, `unit` — подпись.
- Программа зала: `GET /api/gym-program?day=2026-09-01` → `{"found": false, "day": "…"}` или
  `{"found": true, "day", "gym", "board_text", "blocks", "blocks_verified", "form", "template_text"}` — та же форма.

## 3. Запись: `PUT /api/workouts/{uuid}` (uuid генерирует клиент; повтор безопасен)
```json
{"day": "2026-09-01", "sport": "weightlifting", "start_time": "09:00", "duration_min": 75,
 "rpe": 8, "scaling": "rx", "bodyweight": 80,
 "board": {"text": "<board_text из job>", "source": "own", "blocks": [ "<blocks из job без изменений>" ]},
 "form_result": {"0.0": "70x3", "0.2": "80x3", "1.0": "6:00"}}
```
`form_result` — `{key: значение}` по `form`: `weight_reps` `"70x3"` (или `70`, `[70,3]`, `{"weight":70,"reps":3}`),
`time` `"6:00"` или секунды, `rounds_reps` `"5+3"`, `int` число. Пустые поля просто не присылаем. `start_time` нужен для
слияния с записью часов по времени; несколько тренировок в день — просто разные uuid. Для зальной программы:
`"board": {"source": "gym"}` (текст и блоки сервер берёт из программы дня). Бег/вело/плавание:
`{"day", "sport": "run", "start_time", "duration_min": 30, "distance_km": 5, "rpe": 6}`. Свободный текст вместо формы:
`"form_result": "Присед 100x3\nRPE 8 scaled"`.
```json
{"activity_id": "febf8145-c78d-4c44-a7ff-d2eaba2f1053", "created": true, "day": "2026-09-01", "sport": "weightlifting",
 "score": "6:00", "rpe": 8, "scaling": "rx", "board_source": "own", "metcon_lines": ["WOD 1 — время: 6:00"],
 "credited": [],
 "ambiguous": [{"movement": "рывок", "family": "snatch", "weight": 80.0, "reps": 3,
                "variants": [{"id": "squat_snatch", "label": "В сед"}, {"id": "power_snatch", "label": "В стойку"}]}],
 "proposed_maxes": null, "lifts_skipped_quota": false, "bodyweight": 80.0}
```
- `credited` — максы, уже записанные в уровни (`{discipline, name, weight, reps, est_1rm}`).
- `ambiguous` — вопросы «какой рывок/какое взятие»: показать `variants`, ответ — шаг 4.
- `proposed_maxes` (только для свободного текста): `{maxes: [{movement, weight_kg, reps}], credited: [...], ambiguous: [...]}` —
  показать на подтверждение, затем `POST /maxes`.
- Ошибки: 400 id не UUID; 403 нельзя перезаписать запись с часов / зальную доску сделать «своей»; 422 `sport`, `day`,
  `rpe`, поле формы (`поле 1.0 (время (мм:сс)): ожидается мм:сс`), `на эту дату нет программы зала`.

## 4. Ответ на вопрос по лифту
`POST /api/workouts/{uuid}/lifts/resolve`
```json
{"movement": "рывок", "variant": "power_snatch", "weight": 80.0, "reps": 3}
```
→ `{"discipline": "power_snatch", "name": "Рывок в стойку", "weight": 80.0, "reps": 3, "est_1rm": 88.0}`.
Выбор запоминается: повторный PUT не переспрашивает.

## 5. Максы вручную/по подтверждению
`POST /api/workouts/{uuid}/maxes` — `{"maxes": [{"movement": "становая тяга", "weight_kg": 150, "reps": 3}]}` или
`{"text": "Рывок 60x2\nПрисед 100x3"}` →
`{"credited": [{"discipline": "deadlift", "name": "Становая", "weight": 150.0, "reps": 3, "est_1rm": 165.0}],
"ambiguous": [], "skipped_quota": false}`.

## 6. Чтение, правка, удаление
- `GET /api/workouts/recent?limit=10` → `[{id, day, sport, source, wod_format, score, scaling, rpe, duration_min, distance_km,
  start_time, board_source, updated_at}]`.
- `GET /api/workouts/{uuid}` → те же поля + `board_text`, `blocks`, `form`, `form_values` (то, что вводили),
  `result_text`, `metcon`, `maxes`, `bodyweight`, `editable`, `board_editable` (false у зальной доски — кнопку правки доски
  не показывать).
- `PATCH /api/workouts/{uuid}` — любые из `rpe`, `scaling` (`rx|scaled|null`), `form_result`, `board: {text}`, `maxes`,
  `maxes_text`, `bodyweight` → `{workout, metcon_lines, credited, ambiguous}`. `board` для зальной записи — 403.
- `DELETE /api/workouts/{uuid}` → `{"id": "…", "deleted_at": "2026-09-28T21:00:46Z"}`; отмена — `POST …/restore` (вернёт тренировку целиком).
- Чужая/несуществующая запись: 404 `{"detail": "тренировка не найдена"}`.

## 7. Цели, ПМ, вес тела, самочувствие
- `POST /api/goals/items` `{"kind": "numeric", "discipline": "back_squat", "target": "140"}` →
  `{"id": 1, "tg_id": 301, "kind": "numeric", "title": "Присед -> 140", "exercise": "back_squat", "target_value": "140.0",
  "metric": "kg", "status": "active", "created_at": "…"}`. Цель уровня: `{"kind": "level", "discipline", "target": "<название уровня>"}`.
  Числовая цель по бенчмарку: `"4:30"` (время) или число кругов.
- `GET /api/goals/items` — активные; `POST /api/goals/items/{id}/archive` (или `DELETE …/{id}`), `POST …/{id}/complete` →
  цель с новым `status` (`archived|done`). Экран уровней и прогресса по-прежнему `GET /api/goals`.
- `POST /api/pm` `{"discipline": "back_squat", "value": "100x3"}` (или `value: 100, reps: 3`) →
  `{"discipline": "back_squat", "name": "Присед", "value": 100.0, "reps": 3, "est_1rm": 110.0, "day": "2026-09-28", "tier": null}`
  (`tier` — текущий уровень, если известен вес/пол профиля).
- `POST /api/bodyweight` `{"kg": 79.5, "day": "2026-09-01"}` (день необязателен) → `{"day": "2026-09-01", "kg": 79.5}`; 20–500 кг.
- `POST /api/feel` `{"score": 8}` → `{"day": "2026-09-28", "score": 8}` (день — сегодня по часовому поясу пользователя).
