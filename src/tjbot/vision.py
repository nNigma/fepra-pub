"""Разбор фото доски WOD в черновик предписания через Gemini (llm.vision).

Auto: если есть GEMINI_API_KEY -> распознаём фото, движения через онтологию.
Фолбэк: ключа/ответа нет -> None, бот просит вписать текст руками.
"""
from __future__ import annotations

import json
import re

from tj import llm
from tj.ontology import resolve, MOVEMENTS

_PROMPT = (
    "На фото - доска с программой кроссфит-тренировки (рукописная, по-русски, с "
    "сокращениями). Распознай структуру и верни ТОЛЬКО JSON-объект с полями:\n"
    '  "raw_text": построчная расшифровка доски как есть;\n'
    '  "format": один из "for-time","amrap","emom","rounds","other";\n'
    '  "movements": массив движений простыми словами по-русски.\n'
    "Не выдумывай. Сомневаешься - оставь как есть или пометь (?)."
)


def has_vision() -> bool:
    return llm.has_llm()


def has_claude() -> bool:
    return llm.has_claude_vision()


def engine_for(tg_id: int) -> str:
    """Claude включён -> все фото в Claude CLI (Gemini — фолбэк роутера).
    Выключен -> Gemini единственный движок."""
    from tj.config import claude_enabled
    return "claude" if claude_enabled() else "gemini"


def _as_text(v) -> str:
    """Gemini иногда отдаёт построчные поля (raw_text/prescription) массивом строк
    вместо строки — приводим к строке, чтобы потребители не падали на конкатенации."""
    if isinstance(v, list):
        return "\n".join(str(x) for x in v)
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


def _extract_json(text: str) -> dict | None:
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j <= i:
        return None
    try:
        return json.loads(text[i:j + 1])
    except ValueError:
        return None


def _extract_json_array(text: str) -> list | None:
    i, j = text.find("["), text.rfind("]")
    if i == -1 or j <= i:
        return None
    try:
        data = json.loads(text[i:j + 1])
    except ValueError:
        return None
    return data if isinstance(data, list) else None


def normalize_movements(phrases, use_llm: bool = True) -> dict:
    """Неизвестные фразы движений -> {фраза: канон-id} через Gemini. Валидация по
    онтологии: чужие id отбрасываются. Пусто, если LLM off/недоступен/ничего не понял."""
    seen = []
    for p in phrases or []:
        p = (p or "").strip()
        if p and p not in seen:
            seen.append(p)
    if not seen or not use_llm:
        return {}
    hint = "; ".join(f"{cid}({MOVEMENTS[cid][-1]})" for cid in MOVEMENTS)
    system = (
        "Сопоставь названия упражнений кроссфита с каноническими id из списка. Верни "
        'СТРОГО JSON вида {"фраза": "id"} только для уверенно распознанных; неясные '
        "пропусти. id бери ТОЛЬКО из списка. Учитывай склонения, опечатки, лишние "
        "слова (вес, кг, паузы, темп, гантель/штанга)."
    )
    user = "id: " + hint + "\n\nФразы:\n" + "\n".join(f"- {p}" for p in seen)
    raw = llm.complete(system, user, max_output_tokens=600)
    obj = _extract_json(raw) if raw else None
    if not isinstance(obj, dict):
        return {}
    known = set(MOVEMENTS)
    by_low = {p.lower(): p for p in seen}
    out = {}
    for k, v in obj.items():
        if isinstance(v, str) and v in known:
            phrase = by_low.get((k or "").strip().lower())
            if phrase:
                out[phrase] = v
    return out


# --- Питание: фото еды -> блюда + КБЖУ -----------------------------------------

_MEAL_MACRO = ("grams", "kcal", "protein_g", "fat_g", "carb_g")
_MEAL_MICRO = ("fiber_g", "sugar_g", "sodium_mg", "iron_mg", "calcium_mg",
               "magnesium_mg", "potassium_mg")

_MEAL_PROMPT = (
    "На фото — еда. Определи блюда и оцени порции. Верни ТОЛЬКО JSON-объект:\n"
    '{"foods": [{"name": "название по-русски", "grams": число,\n'
    '            "kcal": число, "protein_g": число, "fat_g": число, "carb_g": число,\n'
    '            "fiber_g": число, "sugar_g": число, "sodium_mg": число,\n'
    '            "iron_mg": число, "calcium_mg": число, "magnesium_mg": число,\n'
    '            "potassium_mg": число}],\n'
    ' "confidence": "high" | "medium" | "low",\n'
    ' "question": "ОДИН короткий уточняющий вопрос, только если он сильно улучшит '
    'оценку, иначе null",\n'
    ' "quality": 1 | 2 | 3 | 4,\n'
    ' "quality_note": "коротко почему (до 60 знаков)"}\n'
    "Правила:\n"
    "- quality: 1 — цельная еда с белком; 2 — обычная сбалансированная; "
    "3 — жареное/сладкое без криминала; 4 — фастфуд/сахарная бомба. Оценивай "
    "состав блюд, не калораж;\n"
    "- grams — съедобная порция на фото; ккал/БЖУ/микронутриенты считай именно "
    "для этих граммов (типовые табличные значения продукта);\n"
    "- ШТУКИ ПЕРЕСЧИТЫВАЙ ПО ФОТО: видно 2 манта — пиши 2, не предполагай "
    "скрытые или «стандартную порцию»;\n"
    "- сомневаешься в ТИПЕ блюда (самса или лепёшка, борщ или другой красный "
    "суп, чай или пиво) — НЕ выбирай уверенно: назови нейтрально «выпечка», "
    "«красный суп на бульоне», «напиток» и задай вопрос про то сомнение, что "
    "сильнее всего меняет калораж;\n"
    "- скрытые ингредиенты (масло при жарке, соус, сахар в напитке) включай в "
    "оценку; упаковку/этикетку читай точно; не выдумывай блюда, которых на "
    "фото нет;\n"
    "- ориентиры масштаба: столовые приборы, руки, стандартная тарелка 24-26 см."
)


def _meal_num(v):
    return round(float(v), 1) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def _valid_meal(data: dict) -> dict | None:
    """Жёсткая валидация ответа + серверный пересчёт тоталов. Мусор -> None."""
    foods_in = data.get("foods")
    if not isinstance(foods_in, list) or not foods_in or len(foods_in) > 15:
        return None
    foods = []
    for f in foods_in:
        if not isinstance(f, dict):
            return None
        name = (f.get("name") or "").strip()
        vals = {k: _meal_num(f.get(k)) for k in _MEAL_MACRO + _MEAL_MICRO}
        if not name or vals["kcal"] is None:
            return None
        foods.append({"name": name[:80], **vals})
    totals = {k: round(sum(f[k] or 0 for f in foods), 1)
              for k in ("kcal", "protein_g", "fat_g", "carb_g")}
    if not (0 < totals["kcal"] <= 6000):        # один приём >6000 ккал — мусор
        return None
    q = data.get("question")
    conf = data.get("confidence")
    quality = data.get("quality")
    quality = (int(quality) if isinstance(quality, (int, float))
               and not isinstance(quality, bool) and 1 <= quality <= 4 else None)
    note = data.get("quality_note")
    note = note.strip()[:80] if isinstance(note, str) and note.strip() else None
    return {"foods": foods, "totals": totals,
            "question": q.strip()[:200] if isinstance(q, str) and q.strip() else None,
            "confidence": conf if conf in ("high", "medium", "low") else "medium",
            "quality": quality, "quality_note": note if quality else None}


def parse_meal(image_bytes: bytes, media_type: str = "image/jpeg",
               engine: str = "gemini", correction: str | None = None) -> dict | None:
    """Фото еды -> {foods, totals, question, confidence} | None.
    correction — текст-уточнение пользователя для повторного парса."""
    prompt = _MEAL_PROMPT
    if correction:
        prompt += f"\n\nУточнение пользователя (учти как факт): {correction.strip()[:400]}"
    # еда — на opus: счёт штук и классификация блюд заметно точнее, чем у sonnet
    raw = llm.vision(image_bytes, prompt, media_type=media_type, engine=engine,
                     claude_model="opus", max_output_tokens=2000)
    if not raw:
        return None
    data = _extract_json(raw)
    return _valid_meal(data) if data else None


# --- Claude-проверка шаблона результатов (после «Принять») ---------------------

_VERIFY_FORMATS = {"for_time", "amrap", "amrap_interval", "emom_strength",
                   "ladder", "tabata", "death_by", "other"}

_VERIFY_PROMPT = (
    "Ниже — текст доски кроссфит-тренировки и JSON-разбор её на блоки, сделанный "
    "детерминированным парсером. Сверь разбор с доской и верни ИСПРАВЛЕННЫЙ "
    "JSON-массив блоков той же структуры. Типовые ошибки парсера: потерянные "
    "движения или их дистанции/повторы, задвоенные движения, лишние или слитые "
    "блоки, движение не в том блоке, неверный формат/раунды, опечатки доски в "
    "именах движений.\n"
    "Поля блока: header (строка), format (один из: for_time, amrap, amrap_interval, "
    "emom_strength, ladder, tabata, death_by, other), rounds, reps, work_min, "
    "rest_min (числа или null), scheme (строка или null), has_cap (true/false), "
    "movements (массив СТРОК — имена движений по-русски как на доске, с весами и "
    "дистанциями). Разминку не включай. Не выдумывай ничего, чего нет на доске; "
    "если разбор верен — верни его без изменений. Верни ТОЛЬКО JSON-массив.\n\n"
    "ДОСКА:\n{board}\n\nРАЗБОР:\n{blocks}"
)


def _slim_blocks(blocks: list) -> list[dict]:
    return [{"header": b.get("header"), "format": b.get("format"),
             "rounds": b.get("rounds"), "reps": b.get("reps"),
             "work_min": b.get("work_min"), "rest_min": b.get("rest_min"),
             "scheme": b.get("scheme"), "has_cap": bool(b.get("has_cap")),
             "movements": [m.get("name") for m in b.get("movements") or []]}
            for b in blocks]


def _num_or_none(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def verify_result_blocks(board_text: str, blocks: list,
                         aliases: dict | None = None) -> tuple[list, bool]:
    """Claude сверяет блоки шаблона результатов с текстом доски и правит огрехи
    парсера. Ответ валидируется жёстко (схема, форматы, движения перемаппливаются
    через онтологию заново); любой сбой/сомнение -> исходные блоки, запись никогда
    не блокируется. -> (blocks, verified)."""
    if not blocks or not (board_text or "").strip() or not llm.has_claude_vision():
        return blocks, False
    if any(b.get("benchmark") for b in blocks):
        return blocks, False          # бенчмарк-блоки точны по словарю — не трогаем
    prompt = _VERIFY_PROMPT.format(
        board=board_text.strip(),
        blocks=json.dumps(_slim_blocks(blocks), ensure_ascii=False))
    raw = llm.claude_complete(prompt)
    data = _extract_json_array(raw) if raw else None
    if not data or len(data) > 12:
        return blocks, False
    from tj.analysis.wod_program import _movement
    out = []
    for b in data:
        if not isinstance(b, dict):
            return blocks, False
        fmt = b.get("format")
        movs = b.get("movements")
        if fmt not in _VERIFY_FORMATS or not isinstance(movs, list):
            return blocks, False
        names = [m.strip() for m in movs if isinstance(m, str) and m.strip()]
        if not names:
            return blocks, False
        scheme = b.get("scheme")
        out.append({"header": str(b.get("header") or "Блок")[:40],
                    "format": fmt,
                    "rounds": _num_or_none(b.get("rounds")),
                    "reps": _num_or_none(b.get("reps")),
                    "work_min": _num_or_none(b.get("work_min")),
                    "rest_min": _num_or_none(b.get("rest_min")),
                    "has_cap": bool(b.get("has_cap")),
                    "movements": [_movement(n, aliases) for n in names],
                    "benchmark": None,
                    "scheme": scheme if isinstance(scheme, str) and scheme else None})
    return out, True


_WEIGHT_TAIL = re.compile(r"[,;]?\s*\d+[\d\s\-–хx/]*\s*кг.*$", re.IGNORECASE)


def _alias_key(name: str) -> str:
    s = _WEIGHT_TAIL.sub("", name or "").strip(" ,;.-–")
    return s or (name or "")


def enrich_aliases(con, text: str, use_llm: bool = True) -> dict:
    """Догоняет movement_aliases для неизвестных движений доски через Gemini и
    возвращает свежий словарь алиасов (для parse_program). Фолбэк - как есть.
    Словарь растёт: раз распознанное движение дальше резолвится детерминированно."""
    from . import db as botdb
    from tj.analysis.wod_program import movements_of, parse_program

    aliases = botdb.load_aliases(con)
    if not use_llm or not (text or "").strip():
        return aliases
    _, unknown = movements_of(parse_program(text, aliases))
    cleaned = []
    for u in unknown:
        k = _alias_key(u)
        if k and k not in cleaned:
            cleaned.append(k)
    if not cleaned:
        return aliases
    mapping = normalize_movements(cleaned, use_llm=True)
    if not mapping:
        return aliases
    for phrase, canon in mapping.items():
        botdb.add_alias(con, phrase, canon, source="gemini")
    return botdb.load_aliases(con)


def standardize(movements, aliases: dict | None = None):
    """Список движений простыми словами -> (канон[], нераспознанные[]).
    Канон-id на входе пропускаются как есть; дубли схлопываются."""
    known = set(MOVEMENTS) | set((aliases or {}).values())
    canon, unknown = [], []
    for m in movements or []:
        c = resolve(m, aliases) or (m if m in known else None)
        if c:
            if c not in canon:
                canon.append(c)
        elif m not in unknown:
            unknown.append(m)
    return canon, unknown


def scan_movements(text: str, aliases: dict | None = None):
    """Найти канон-движения в свободном тексте (длинные алиасы - первыми, с маскированием)."""
    norm = " ".join(w.strip(" .,:;()") for w in
                    (text or "").lower().replace("+", " ").replace("-", " ").split())
    hay = f" {norm} "
    lookup = {a: c for c, al in MOVEMENTS.items() for a in al}
    if aliases:
        lookup.update(aliases)
    found = []
    for alias, canon in sorted(lookup.items(), key=lambda p: len(p[0].split()), reverse=True):
        needle = f" {alias} "
        if needle in hay:
            if canon not in found:
                found.append(canon)
            hay = hay.replace(needle, " ")
    return found


_STAGES_PROMPT = (
    "На фото - задания этапов кроссфит-старта (по-русски, возможны сокращения). "
    "Верни ТОЛЬКО JSON-массив объектов, по одному на этап, поля:\n"
    '  "name": короткое имя/номер этапа;\n'
    '  "prescription": полный текст задания как есть;\n'
    '  "format": один из "for-time","amrap","emom","rounds","other";\n'
    '  "movements": массив движений простыми словами по-русски.\n'
    "Не выдумывай."
)

_RESULTS_PROMPT = (
    "На фото - таблица результатов кроссфит-соревнования. Найди строку атлета "
    "«{athlete}» (имя может отличаться написанием). Верни ТОЛЬКО JSON-объект:\n"
    '  "athlete": как записан в таблице;\n'
    '  "rows": массив по этапам '
    '[{{"stage": номер или имя этапа, "value": результат, "place": место числом}}].\n'
    "Бери только этого атлета. Не выдумывай; не нашёл - rows: []."
)


def parse_stages(image_bytes: bytes, media_type: str = "image/jpeg",
                 engine: str = "gemini") -> list | None:
    raw = llm.vision(image_bytes, _STAGES_PROMPT, media_type=media_type, engine=engine)
    if not raw:
        return None
    data = _extract_json_array(raw)
    if not data:
        return None
    out = []
    for st in data:
        if not isinstance(st, dict):
            continue
        st["name"] = _as_text(st.get("name"))
        st["prescription"] = _as_text(st.get("prescription"))
        movs = st.get("movements") or []
        st["movements_canon"] = [c for c in (resolve(m) for m in movs) if c]
        out.append(st)
    return out or None


def parse_results(image_bytes: bytes, athlete_hint: str, media_type: str = "image/jpeg",
                  engine: str = "gemini") -> dict | None:
    raw = llm.vision(image_bytes, _RESULTS_PROMPT.format(athlete=athlete_hint),
                     media_type=media_type, engine=engine)
    if not raw:
        return None
    return _extract_json(raw)


_TEXT_PROMPT = (
    "Ниже - текст программы кроссфит-тренировки (по-русски, возможны сокращения). "
    "Верни ТОЛЬКО JSON-объект с полями:\n"
    '  "raw_text": построчный текст программы как есть;\n'
    '  "format": один из "for-time","amrap","emom","rounds","other";\n'
    '  "movements": массив движений простыми словами по-русски.\n'
    "Не выдумывай.\n\nТЕКСТ:\n{text}"
)


def _text_fallback(text: str) -> dict:
    return {"raw_text": text.strip(), "format": "other", "movements": scan_movements(text)}


def parse_text(text: str, use_llm: bool = True) -> dict:
    """Текст программы -> черновик {raw_text, format, movements}. Без LLM/при сбое/
    при use_llm=False (лимит ИИ) - фолбэк: исходный текст + онтология-скан движений."""
    if not use_llm or not llm.has_llm():
        return _text_fallback(text)
    raw = llm.complete("Ты разбираешь программы тренировок.",
                       _TEXT_PROMPT.format(text=text), max_output_tokens=600)
    data = _extract_json(raw) if raw else None
    if not data:
        return _text_fallback(text)
    data["raw_text"] = _as_text(data.get("raw_text")) or text.strip()
    data.setdefault("format", "other")
    data.setdefault("movements", [])
    return data


_LIFTS_PROMPT = (
    "Ниже - текст с результатом силовой/кроссфит-тренировки (по-русски). "
    "Найди силовые подъёмы со штангой и для каждого верни ВЕРХНИЙ рабочий подход. "
    "Верни ТОЛЬКО JSON-массив объектов с полями: "
    '"movement" (движение простыми словами по-русски), '
    '"weight_kg" (число - вес верхнего подхода в кг), '
    '"reps" (число повторов в нём; не указано - 1). '
    "Только подъёмы со штангой/весом; кардио и гимнастику без веса не включай. "
    "Силовых нет - верни []. Не выдумывай вес.\n\nТЕКСТ:\n{text}"
)


def parse_lifts(text: str, use_llm: bool = True) -> list | None:
    """Текст результата -> список силовых подъёмов [{movement, weight_kg, reps}].
    Без ключа/при сбое/мусоре/при use_llm=False (лимит ИИ) -> None."""
    if not use_llm or not llm.has_llm():
        return None
    raw = llm.complete("Ты разбираешь силовые результаты.",
                       _LIFTS_PROMPT.format(text=text), max_output_tokens=400)
    if not raw:
        return None
    data = _extract_json_array(raw)
    return data if isinstance(data, list) else None


def parse_board(image_bytes: bytes, media_type: str = "image/jpeg",
                engine: str = "gemini") -> dict | None:
    """Доска: порядок движков по выбору юзера. engine="gemini" (быстро) — сначала
    Gemini, Claude запасным; engine="claude" (медленно, точнее) — сначала Claude,
    Gemini запасным. В ответе engine_used — фактически сработавший (для уведомления
    о фолбэке, если выбранный движок не ответил)."""
    order = ["claude", "gemini"] if engine == "claude" else ["gemini", "claude"]
    raw = None
    used = None
    for eng in order:
        if eng == "claude":
            if not llm.has_claude_vision():
                continue
            raw = llm.claude_vision(image_bytes, _PROMPT, media_type=media_type)
        else:
            raw = llm.vision(image_bytes, _PROMPT, media_type=media_type, engine="gemini")
        if raw:
            used = eng
            break
    if not raw:
        return None
    data = _extract_json(raw)
    if not data:
        return None
    data["raw_text"] = _as_text(data.get("raw_text"))
    movements = data.get("movements") or []
    data["movements_canon"] = [c for c in (resolve(m) for m in movements) if c]
    data["engine_used"] = used
    return data
