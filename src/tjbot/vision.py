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


def parse_stages(image_bytes: bytes, media_type: str = "image/jpeg") -> list | None:
    raw = llm.vision(image_bytes, _STAGES_PROMPT, media_type=media_type)
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


def parse_results(image_bytes: bytes, athlete_hint: str, media_type: str = "image/jpeg") -> dict | None:
    raw = llm.vision(image_bytes, _RESULTS_PROMPT.format(athlete=athlete_hint), media_type=media_type)
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


def parse_board(image_bytes: bytes, media_type: str = "image/jpeg") -> dict | None:
    raw = llm.vision(image_bytes, _PROMPT, media_type=media_type)
    if not raw:
        return None
    data = _extract_json(raw)
    if not data:
        return None
    data["raw_text"] = _as_text(data.get("raw_text"))
    movements = data.get("movements") or []
    data["movements_canon"] = [c for c in (resolve(m) for m in movements) if c]
    return data
