"""Доска тренировки: фото/текст -> блоки -> ФОРМА результата (данные, не текст).

Поверх tjbot.vision (распознавание, ИИ) и детерминированного tj.analysis.wod_program.
Форма строится из тех же строк, что и текстовый шаблон бота («заполни ___»): каждое
поле = одна строка шаблона. Поэтому заполненную форму можно превратить обратно в
текст (fill_template) и отдать существующим детерминированным разборщикам
(summarize_filled, extract_maxes) без правок.

Формат формы (form):
    {"version": 1,
     "blocks": [{"index": 0, "title": "AMRAP", "format": "amrap", "kind": "metcon"|"strength",
                 "fields": [{"key": "0.0", "label": "вес «гиря»", "type": "weight", "unit": "кг",
                             "section": "AMRAP", "group": None, "movement": "гиря"|None}, ...]}]}
Ключ поля "<блок>.<номер>" стабилен для одних и тех же блоков; форма результата от
клиента = {ключ: значение}. Типы: weight_reps (вес×повторы), weight (кг), time (мм:сс),
int (число), rounds_reps («5+3»: круги+повторы), text, а также:
  cardio          — ккал, метры ИЛИ время в секундах/минутах (единицу выбирает атлет; default_unit
                    в поле); значение {"unit": "kcal"|"m"|"sec"|"min", "value": число}
                    (для совместимости принимается и "time": «мм:сс»);
  weight_distance — сани и т.п.: {"weight": кг, "meters": м, "time": число, "time_unit": "sec"|"min"}
                    (хотя бы одно из трёх);
  reps_load       — повторы + вес по желанию: {"reps": n, "weight": кг|None}.
"""
from __future__ import annotations

import re

from tj.analysis import wod_program

from .errors import BadRequest, Forbidden, Invalid, NotFound

FORM_VERSION = 1

_ENGINES = {"fast": "gemini", "gemini": "gemini", "slow": "claude", "claude": "claude",
            "agent": "agent"}
NOT_RECOGNIZED = "[фото доски — не распознано]"


# --- форма результата --------------------------------------------------------------

_LADDER_CARDIO = re.compile(r"^раунд\s+\d+\s*-\s*\d+\s*ккал$", re.IGNORECASE)
_CARDIO_UNITS = {"kcal": "ккал", "m": "м", "sec": "сек", "min": "мин", "time": None}
_LADDER_WEIGHT = re.compile(r"^раунд\s+\d+\s*-\s*(\d+)\s*повт,\s*вес$", re.IGNORECASE)


def _field_type(label: str) -> tuple[str, str | None]:
    low = label.strip().lower()
    if "(вес×повторы)" in low:
        return "weight_reps", "кг×повт"
    if _LADDER_WEIGHT.match(low):
        # вес в лесенке: повторов по схеме подставляем, но атлет может сделать другое число
        return "weight_reps", "кг×повт"
    if low.startswith("удержание"):
        return "int", "сек"
    if low.startswith("метров"):
        return "int", "м"
    if low.startswith("кардио"):
        return "cardio", None
    if _LADDER_CARDIO.match(low):
        return "cardio", None
    if low.startswith("вес и дистанция"):
        return "weight_distance", "кг+м"
    if low.startswith("повторы, вес"):
        return "reps_load", "повт"
    if low.startswith("время"):
        return "time", "мм:сс"
    if low.startswith("круги, амрап"):
        return "rounds_reps", "круги+повторы"
    if low.startswith("кругов"):
        return "int", "кругов"
    if "ккал" in low:
        return "int", "ккал"
    if low.startswith("вес") or low.endswith(", вес"):
        return "weight", "кг"
    if low.startswith("дошёл до минуты"):
        return "int", "минута"
    if "повтор" in low or "повт" in low or low.startswith("выполнено") or "минут" in low:
        return "int", None
    return "text", None


_MOVE_IN_LABEL = re.compile(r"«([^»]+)»")


def result_form(blocks) -> dict:
    """Блоки -> форма результата (см. модульный docstring)."""
    out_blocks = []
    idx = 0
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        lines = wod_program.render_block(b)
        fmt = b.get("format") or b.get("kind")
        fields: list[dict] = []
        section = None
        first_section = None
        for line in lines:
            if not line.startswith((" ", "\t")) and line.rstrip().endswith(":"):
                section = line.strip()[:-1].strip()
                if first_section is None:
                    first_section = section
                continue
            if section is None or ":" not in line:
                continue
            # значение шаблона всегда ___: метка = строка без хвоста «: ___»
            label = re.sub(r":\s*_+\s*$", "", line.strip()).strip()
            ftype, unit = _field_type(label)
            mv = _MOVE_IN_LABEL.search(label)
            field = {
                "key": f"{idx}.{len(fields)}", "label": label, "type": ftype, "unit": unit,
                "section": section, "group": None if section == first_section else section,
                "movement": mv.group(1) if mv else (
                    b["movements"][0]["name"] if fmt in ("strength", "emom_strength")
                    and b.get("movements") else (
                        section if fmt == "stations" and section != first_section else None)),
            }
            if ftype == "weight" and label.strip().lower().startswith("вес «"):
                # вес упражнения в for-time/AMRAP: вес × повторы, повторы по желанию
                # (общее число повторов задано самим WOD, но подходы могут отличаться)
                field["type"] = ftype = "weight_reps"
                field["unit"] = "кг×повт"
                field["reps_optional"] = True
            if ftype == "cardio":
                field["default_unit"] = "m" if re.search(r",\s*м$", label.strip().lower()) else "kcal"
            if ftype == "weight_reps":
                lm = _LADDER_WEIGHT.match(label.strip())
                rd = int(lm.group(1)) if lm else (
                    b.get("reps") if fmt in ("strength", "emom_strength") else None)
                if rd:
                    field["reps_default"] = int(rd)
            fields.append(field)
        out_blocks.append({
            "index": idx, "title": first_section or b.get("header") or "Блок",
            "format": fmt,
            "kind": "strength" if fmt in ("strength", "emom_strength") else "metcon",
            "has_cap": bool(b.get("has_cap")), "fields": fields,
            "_first": first_section})
        idx += 1
    for ob in out_blocks:
        ob.pop("_first", None)
    return {"version": FORM_VERSION, "blocks": out_blocks}


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _g(x: float) -> str:
    return f"{x:g}"


def _fmt_time(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


def normalize_value(field: dict, value) -> str:
    """Значение поля от клиента -> строка в формате шаблона. Пусто -> ''. Ошибка -> Invalid."""
    if value is None or value == "":
        return ""
    ftype = field["type"]
    key = field["key"]

    def bad(what):
        raise Invalid(f"поле {key} ({field['label']}): {what}", code="bad_field")

    if ftype == "weight_reps":
        if isinstance(value, dict):
            w, r = _num(value.get("weight")), _num(value.get("reps"))
            if r is None and field.get("reps_default"):
                r = float(field["reps_default"])     # повторы не тронуты — берём по схеме
            elif r is None and field.get("reps_optional") and w and w > 0:
                return _g(w)                         # только вес — как раньше
        elif isinstance(value, (list, tuple)) and len(value) == 2:
            w, r = _num(value[0]), _num(value[1])
        elif isinstance(value, str):
            from tj.analysis.wod_notation import parse_weight_reps
            if field.get("reps_optional") and _num(value) is not None:
                return _g(_num(value))               # «22.5» без повторов
            p = parse_weight_reps(value)
            if not p:
                bad("ожидается «вес×повторы», например 100x5")
            w, r = p
        else:
            w, r = _num(value), float(field.get("reps_default") or 1)
        if not w or w <= 0 or not r or r < 1:
            bad("вес и повторы должны быть положительными")
        return f"{_g(w)}x{int(r)}"
    if ftype == "cardio":
        unit, val = None, value
        if isinstance(value, dict):
            unit, val = value.get("unit"), value.get("value")
        if unit is None:
            unit = field.get("default_unit") or "kcal"
        if unit not in _CARDIO_UNITS:
            bad("единица: kcal, m или time")
        if unit == "time":
            if val is None or val == "":
                return ""
            if isinstance(val, str) and ":" in val:
                m = re.fullmatch(r"\s*(\d{1,3}):(\d{2})\s*", val)
                if not m or int(m.group(2)) >= 60:
                    bad("время: ожидается мм:сс")
                return f"{int(m.group(1))}:{m.group(2)} время"
            sec = _num(val)
            if sec is None or sec < 0:
                bad("время: мм:сс или секунды")
            return f"{_fmt_time(int(sec))} время"
        n = _num(val)
        if n is None or n < 0:
            bad("ожидается число")
        return f"{_g(n)} {_CARDIO_UNITS[unit]}"       # ккал / м / сек / мин
    if ftype == "weight_distance":
        if not isinstance(value, dict):
            bad("ожидается {weight, meters, time}")
        w, d, tm = _num(value.get("weight")), _num(value.get("meters")), _num(value.get("time"))
        tu = value.get("time_unit") or "sec"
        if tu not in ("sec", "min"):
            bad("время: секунды (sec) или минуты (min)")
        if any(x is not None and x < 0 for x in (w, d, tm)):
            bad("вес, дистанция и время не могут быть отрицательными")
        parts = ([f"{_g(w)} кг"] if w else []) + ([f"{_g(d)} м"] if d else []) + (
            [f"{_g(tm)} {_CARDIO_UNITS[tu]}"] if tm else [])
        return ", ".join(parts)
    if ftype == "reps_load":
        if isinstance(value, dict):
            r, w = _num(value.get("reps")), _num(value.get("weight"))
        elif isinstance(value, str):
            from tj.analysis.wod_notation import parse_weight_reps
            p = parse_weight_reps(value)
            if p:
                w, r = p
            else:
                r, w = _num(value), None
        else:
            r, w = _num(value), None
        if r is None or r < 1:
            bad("нужно число повторов")
        if w is not None and w < 0:
            bad("вес не может быть отрицательным")
        return f"{_g(w)}x{int(r)}" if w else str(int(r))
    if ftype == "weight":
        if isinstance(value, str) and _num(value) is None:
            return value.strip()          # «16/24» и т.п. — как написал атлет
        w = _num(value)
        if w is None or w < 0:
            bad("ожидается число килограммов")
        return _g(w)
    if ftype == "time":
        if isinstance(value, str) and ":" in value:
            m = re.fullmatch(r"\s*(\d{1,3}):(\d{2})\s*", value)
            if not m or int(m.group(2)) >= 60:
                bad("ожидается мм:сс")
            return f"{int(m.group(1))}:{m.group(2)}"
        sec = _num(value)
        if sec is None or sec < 0:
            bad("ожидается мм:сс или секунды")
        return _fmt_time(int(sec))
    if ftype == "rounds_reps":
        if isinstance(value, dict):
            r, x = _num(value.get("rounds")), _num(value.get("reps")) or 0
            if r is None:
                bad("нужно число кругов")
            return f"{int(r)}+{int(x)}" if x else str(int(r))
        if isinstance(value, str):
            if not re.fullmatch(r"\s*\d+(\s*\+\s*\d+)?\s*", value):
                bad("ожидается «круги» или «круги+повторы»")
            return re.sub(r"\s+", "", value)
        n = _num(value)
        if n is None or n < 0:
            bad("ожидается число кругов")
        return str(int(n))
    if ftype == "int":
        n = _num(value)
        if n is None or n < 0:
            bad("ожидается целое число")
        return str(int(n))
    return str(value).strip()


def fill_template(form: dict, values: dict | None) -> str:
    """Форма + значения -> текст заполненного шаблона (для summarize_filled/extract_maxes).
    Неизвестный ключ -> Invalid. Пустые поля остаются пустыми строками."""
    values = values or {}
    known = {f["key"]: f for b in form["blocks"] for f in b["fields"]}
    for k in values:
        if k not in known:
            raise Invalid(f"неизвестное поле формы: {k}", code="unknown_field")
    lines: list[str] = []
    for b in form["blocks"]:
        cur = object()
        if not b["fields"] or b["fields"][0]["section"] != b["title"]:
            lines.append(f"{b['title']}:")      # заголовок блока без своих полей (лесенка)
        for f in b["fields"]:
            if f["section"] != cur:
                lines.append(f"{f['section']}:")
                cur = f["section"]
            lines.append(f"  {f['label']}: {normalize_value(f, values.get(f['key']))}")
    return "\n".join(lines)


def check_blocks(blocks) -> list[dict]:
    """Блоки от клиента: список словарей с полем format. Иначе Invalid."""
    if not isinstance(blocks, list) or not blocks or len(blocks) > 30:
        raise Invalid("blocks: ожидается непустой список блоков", code="bad_blocks")
    for b in blocks:
        if not isinstance(b, dict) or not (b.get("format") or b.get("kind")):
            raise Invalid("blocks: у каждого блока нужен format", code="bad_blocks")
        if not isinstance(b.get("movements", []), list):
            raise Invalid("blocks: movements должен быть списком", code="bad_blocks")
    return blocks


# --- сборка блоков и формы из текста доски -------------------------------------------

def build(con, uid: int, board_text: str, *, verify: bool = True, use_llm: bool = True) -> dict:
    """Текст доски -> {blocks, blocks_verified, form, template_text, annotated}.
    Детерминированный parse_program; админ/Claude молча сверяет блоки (verify_result_blocks),
    фолбэк — как распарсилось. Как в board_confirm бота."""
    from tjbot import vision
    text = (board_text or "").strip()
    blocks: list = []
    verified = False
    if text and text != NOT_RECOGNIZED:
        aliases = vision.enrich_aliases(con, text, use_llm=use_llm)
        blocks = wod_program.parse_program(text, aliases)
        if blocks and verify and vision.engine_for(uid) == "claude" and vision.has_claude():
            blocks, verified = vision.verify_result_blocks(text, blocks, aliases)
    return {
        "blocks": blocks, "blocks_verified": verified,
        "form": result_form(blocks) if blocks else {"version": FORM_VERSION, "blocks": []},
        "template_text": wod_program.render_template(blocks) if blocks else None,
        "annotated": wod_program.annotate(text) if text else "",
    }


def parse(con, uid: int, *, upload_id: str | None = None, text: str | None = None,
          engine: str = "fast", sport: str = "crossfit", verbatim: bool = False,
          uploads_root=None, charge: bool = True) -> dict:
    """Фото доски (upload_id) или текст -> блоки и форма результата. Синхронная: для jobs.

    verbatim=True — текст уже правил человек: без ИИ и без списания квоты (как «правка
    доски» в боте). Квота ИИ — access.llm_quota_consume; на фото исчерпанная квота даёт
    recognized=False, reason="quota" (UI предложит ввести текст); на тексте — просто разбор
    без ИИ. charge=False — не списывать квоту ИИ (тренер/админ загружает программу зала для всех,
    как в боте). Возвращает:
      {recognized, reason, board_text, format, engine_used, sport,
       blocks, blocks_verified, form, template_text, annotated}
    """
    from tjbot import access, vision
    from . import uploads
    if bool(upload_id) == bool(text is not None and str(text).strip()):
        raise BadRequest("нужно одно из: upload_id или text", code="bad_source")
    eng = _ENGINES.get(str(engine or "fast").lower())
    if eng is None:
        raise BadRequest("engine: fast или slow", code="bad_engine")

    res = {"recognized": False, "reason": None, "board_text": None, "format": None,
           "engine_used": None, "sport": sport, "blocks": [], "blocks_verified": False,
           "form": {"version": FORM_VERSION, "blocks": []}, "template_text": None,
           "annotated": ""}
    draft = None
    if upload_id:
        data, mime = uploads.read_bytes(con, uid, upload_id, root=uploads_root)
        if not vision.has_vision():
            res["reason"] = "no_vision"
            return res
        if charge and not access.llm_quota_consume(uid, con):
            res["reason"] = "quota"
            return res
        try:
            draft = vision.parse_board(data, media_type=mime, engine=eng)
        except Exception:
            draft = None
        if not (draft and draft.get("raw_text")):
            res["reason"] = "not_recognized"
            return res
    else:
        t = str(text).strip()
        if verbatim:
            draft = {"raw_text": t}
        else:
            allow = vision.has_vision() and (not charge or access.llm_quota_consume(uid, con))
            draft = vision.parse_text(t, use_llm=allow)
            draft["raw_text"] = draft.get("raw_text") or t
    board_text = draft["raw_text"]
    built = build(con, uid, board_text)
    res.update(built)
    res.update({"recognized": True, "board_text": board_text,
                "format": draft.get("format"), "engine_used": draft.get("engine_used")})
    return res


# --- программа зала на день (add_result) ------------------------------------------------

def target_gym(con, uid: int) -> str:
    """Зал пользователя по умолчанию (см. club.target_gym: профиль, для тренера — его залы)."""
    from . import club
    return club.target_gym(con, uid)


def gym_program(con, uid: int, day: str, gym: str | None = None) -> dict | None:
    """Подтверждённая программа зала на день -> {found, day, gym, board_text, blocks,
    blocks_verified, form, template_text} или None. Выверенные блоки берём как есть,
    иначе детерминированный разбор текста (как add_result в боте)."""
    import json
    from tjbot import db as botdb
    from . import club
    try:
        g = club.resolve_gym(con, uid, gym)
    except club.ClubError as e:
        raise (NotFound if e.status == 404 else Forbidden)(e.detail)
    prog = botdb.get_program(con, day, g)
    if not prog:
        return None
    raw = prog["raw_text"] or ""
    stored = None
    try:
        stored = json.loads(prog["blocks"]) if prog["blocks"] else None
    except (ValueError, KeyError, TypeError):
        stored = None
    if stored:
        blocks, verified = stored, True
    else:
        from tjbot import vision
        aliases = vision.enrich_aliases(con, raw)
        blocks, verified = wod_program.parse_program(raw, aliases), False
    return {"day": day, "gym": prog["gym"], "board_text": raw, "blocks": blocks,
            "blocks_verified": verified,
            "form": result_form(blocks) if blocks else {"version": FORM_VERSION, "blocks": []},
            "template_text": wod_program.render_template(blocks) if blocks else None}
