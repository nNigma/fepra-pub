# Примеры JSON: питание и соревнования

Все запросы с cookie-сессией. Ошибки — `{"detail": "..."}` (400/401/403/404/422). Разбор фото и текста — job:
`POST` возвращает `{"job_id": "…"}`, дальше опрашивать `GET /api/jobs/{id}` до `status: done|error`.

## Питание (нужен Pro или admin, иначе 403 «нужен Pro»)

### Разбор по фото / тексту
```
POST /api/meals/parse   {"upload_id": "3f2b…"}          # или {"text": "стандартный овощной суп"}
-> {"job_id": "a1b2…"}
GET /api/jobs/a1b2…
-> {"status": "done", "error": null, "result": {
     "recognized": true, "reason": null,
     "draft": {"foods": [{"name": "овощной суп", "grams": 300, "kcal": 150, "protein_g": 5, "fat_g": 5,
                          "carb_g": 20, "fiber_g": null, "sugar_g": null, "sodium_mg": null, "iron_mg": null,
                          "calcium_mg": null, "magnesium_mg": null, "potassium_mg": null}],
               "totals": {"kcal": 150, "protein_g": 5, "fat_g": 5, "carb_g": 20},
               "question": "на бульоне или со сливками?", "confidence": "medium",
               "quality": 2, "quality_note": "лёгкий суп"},
     "notes": [],
     "source": {"kind": "photo", "upload_id": "3f2b…", "url": "/api/uploads/3f2b…", "text": null}}}
```
`reason` при `recognized=false`: `quota` (суточный лимит ИИ), `no_vision` (фото без ИИ), `not_recognized`.

### Уточнение (копится на клиенте)
```
POST /api/meals/parse   {"upload_id": "3f2b…", "correction": "без сливок", "notes": []}
-> result.notes == ["без сливок"]
POST /api/meals/parse   {"upload_id": "3f2b…", "correction": "порция 400 г", "notes": ["без сливок"]}
-> result.notes == ["без сливок", "порция 400 г"]
```
Для текста передавайте тот же `text`.

### Сохранение (идемпотентно по uuid)
```
POST /api/meals
{"draft": <draft из разбора, можно с правками>, "day": "2026-07-11", "ts": null,
 "uuid": "5b1f0e5e-0000-4000-8000-000000000001", "upload_id": "3f2b…", "text": null}
-> {"created": true, "meal": {"id": 41, "uuid": "5b1f…", "day": "2026-07-11", "ts": "2026-07-11T12:00:00",
      "foods": [...], "kcal": 150, "protein_g": 5, "fat_g": 5, "carb_g": 20, "note": null,
      "photo_url": "/api/uploads/3f2b…", "quality": 2, "quality_note": "лёгкий суп", "engine": "claude"}}
```
Повтор с тем же `uuid` -> `created: false` и тот же `meal`. `day` не указан — сегодня; `ts` не указан — сейчас (сегодня) или 12:00.
Для текстового приёма передайте `text` (станет `note`, по нему работает перепарс).

### День, правка, перепарс, удаление
```
GET /api/meals?day=2026-07-11
-> {"day": "2026-07-11", "meals": [<meal>], "totals": {"kcal": 150, "protein_g": 5, "fat_g": 5, "carb_g": 20,
     "fiber_g": 0, "sugar_g": 0, "sodium_mg": 0, ...}, "water_l": 0.75, "water_ml": 750}

POST /api/meals/41/reparse   {"correction": "порция больше", "notes": []}      -> {"job_id": "…"}
  job.result — как у /parse, source.kind = "photo"|"text", source.meal_id = 41
  нет ни файла, ни описания -> status "error", error «…нечего перепарсить…»
PUT /api/meals/41            {"draft": <новый draft>, "day": "2026-07-11"}      -> <meal> (тот же id)
DELETE /api/meals/41         -> {"ok": true}
```

### Вода
```
POST /api/water  {"delta_ml": 250, "day": "2026-07-11"}  -> {"day": "2026-07-11", "water_l": 0.25, "water_ml": 250}
POST /api/water  {"delta_ml": -250}                       # откат, итог не ниже 0
GET  /api/water?day=2026-07-11                             -> {"day": "...", "water_l": 0.25, "water_ml": 250}
```

## Соревнования (любой вошедший)

### Список и просмотр
```
GET /api/comp/list
-> {"mine":   [{"id": 7, "name": "Кубок Тулы", "city": "Тула", "date_start": "2026-04-12", "date_end": "2026-04-12",
                "division_id": 12,
                "divisions": [{"id": 12, "name": "RX", "field_size": 40, "participant_id": 31}]}],
    "others": [{"id": 9, "name": "Чужое", ..., "divisions": [{"id": 15, "name": "PRO", "field_size": null,
                "participant_id": null}]}]}
GET /api/comp/events/9
-> {..., "divisions": [{"id": 15, "name": "PRO", "field_size": null, "participant_id": null,
      "stages": [{"id": 88, "idx": 1, "name": "Fran", "prescription": "21-15-9", "movements": [], "format": "text"}]}]}
```
Поле `results` у этапа есть только в дивизионах, где вы участник.

### Создание старта и дубль
```
POST /api/comp/events {"name": "Кубок Тулы", "date": "12.04.2026", "city": "Тула", "category": "rx"}
-> {"created": true, "duplicate": false, "event_id": 7, "division_id": 12, "participant_id": 31}
```
`category`: `newbie | pro | int | rx`, либо своё название: `{"division": "Мастера 40+"}` (вместо `category`).
Дубль (тот же город без регистра и дата):
```
-> {"created": false, "duplicate": true,
    "candidates": [{"id": 7, "name": "Кубок Тулы", "city": "Тула", "date_start": "2026-04-12", "date_end": "...",
                    "divisions": [{"id": 12, "name": "RX", "field_size": 40, "participant_id": null}]}]}
```
Дальше: `POST /api/comp/events/7/join` (или с `{"division_id": 12}`, если дивизионов несколько) -> `{"event_id": 7,
"division_id": 12, "participant_id": 32, "created": true}`; либо тот же запрос с `"force_new": true`.

### Этапы
```
POST /api/comp/events/7/stages {"text": "Fran\n21-15-9 трастеры и подтягивания"}   -> {"stage_id": 88, "idx": 1, "division_id": 12}

POST /api/comp/events/7/stages/parse {"upload_id": "…", "division_id": null}      -> {"job_id": "…"}
  job.result: {"recognized": true, "reason": null, "division_id": 12,
     "stages": [{"idx": 1, "name": "Fran", "prescription": "21-15-9", "format": "for_time",
                 "movements": ["трастер"], "source_ref": "upload:<id>#1"}],
     "preview": ["1. Fran: 21-15-9"]}
POST /api/comp/stages/confirm {"event_id": 7, "stages": <result.stages, можно править>, "division_id": null}
  -> {"saved": 1, "skipped": 0, "division_id": 12}        # повтор -> saved 0, skipped 1
```

### Результаты
```
POST /api/comp/events/7/results {"text": "5:30, 12, 40"}
-> {"result_id": 5, "stage_id": 90, "stage_idx": 3, "value": "5:30", "place": 12, "field_size": 40}
# формат «значение, место[, размер поля]»; этап подбирается сам (последний без вашего результата),
# явный: {"text": "5:30, 12", "stage_idx": 2} — заменяет результат на этапе. Чужое имя: "athlete": "Иван".

POST /api/comp/events/7/results/parse {"upload_id": "…", "athlete": "Я"}          -> {"job_id": "…"}
  job.result: {"recognized": true, "reason": null, "athlete": "Я", "division_id": 12,
     "rows": [{"stage": 2, "value": "4:10", "place": 5, "stage_id": 89, "stage_idx": 2, "stage_name": "Grace"}]}
POST /api/comp/results/confirm {"event_id": 7, "rows": <result.rows, можно править stage_id>, "athlete": "Я"}
  -> {"saved": 3, "skipped": 0, "division_id": 12}
```

### Итог и размер поля
```
GET /api/comp/events/7/total
-> {"total_points": 5.0, "final_place": 2, "field_size": 22, "place_str": "2/22", "division_id": 12, "participant_id": 31}
PUT /api/comp/events/7/total {}                                      # принять предложение
-> {"participant_id": 31, "total_points": 5.0, "final_place": 2, "source": "suggested"}
PUT /api/comp/events/7/total {"total_points": 4.5, "final_place": 1} # вручную
PUT /api/comp/divisions/12/field_size {"field_size": 55}             -> {"division_id": 12, "field_size": 55}
```
Ошибки: 403 «вы не участник…», 422 «укажите division_id» (участвуете в нескольких дивизионах), 422 «нет результатов для
подсчёта итога», 404 (нет старта/дивизиона/этапа/загрузки).
