"""Движок программ: шаблоны, валидатор, резолвер опорных весов, разворачивание формул в кг.

Чистая логика. С БД работает только `resolve_reference` (читает результаты атлета и профиль);
остальное — функции над словарями, чтобы тестироваться без sqlite.
Сервис с записью в БД (каталог, запись на программу, подходы, финиш) — `programs.py`.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from tj import ontology
from tj.analysis import standards

PROGRAMS_DIR = Path(__file__).resolve().parents[1] / "data" / "programs"
_NS = uuid.UUID("6f1b7a52-3d1e-4c58-9a7e-0f9d2b8e4c11")   # для детерминированных id подходов/сессий

ROUNDING = 2.5                 # шаг округления весов в плане
FRESH_DAYS = 60                # макс старше этого — stale
STARTER_FACTOR = 0.9           # стартовый уровень = порог × вес тела × 0.9
LEVELS = ("careful", "normal", "experienced")   # = пороги standards[0] / [1] / [2]
BAR_KG = {"m": 20.0, "f": 15.0}
MISS_DROP_KG = 5.0

# Оценки связей между лифтами: лифт -> [(источник, коэффициент)]. kg(лифт) ≈ kg(источник) × коэф.
# ОЦЕНКИ, уточняются тест-сессией: после теста опорные берутся из фактического максимума.
DERIVE: dict[str, list[tuple[str, float]]] = {
    "squat_snatch":   [("clean_and_jerk", 0.80), ("power_snatch", 1.25)],
    "power_snatch":   [("squat_snatch", 0.80)],
    "front_squat":    [("back_squat", 0.85)],
    "back_squat":     [("front_squat", 1.25)],
    "clean_floor":    [("clean_and_jerk", 0.90)],
    "jerk":           [("clean_and_jerk", 1.0)],
    "clean_and_jerk": [("squat_snatch", 1.25), ("clean_floor", 1.10), ("jerk", 1.0)],
    "power_clean":    [("clean_floor", 0.90)],
    "hang_clean":     [("clean_floor", 0.90)],
}

WEEK_TYPES = ("volume", "medium", "high", "deload", "test")
SESSION_KINDS = ("normal", "test", "deload")
ON_MISS_RULES = ("drop_5kg_continue",)


def default_rest_sec(kind: str, pct: float) -> int:
    """Отдых между подходами, если шаблон не задал rest_sec: тяжелее — дольше."""
    if kind == "attempt":
        return 240
    if kind == "day_max":
        return 180
    return 60 if pct < 70 else 90 if pct < 80 else 120 if pct < 90 else 150


class ProgramError(ValueError):
    """База ошибок сервиса программ. `code` -> HTTP-код в роутах (следующий шаг)."""
    code = "invalid"


class NotFound(ProgramError):
    code = "not_found"


class Conflict(ProgramError):
    code = "conflict"


class Unavailable(ProgramError):
    code = "unavailable"


class SessionClosed(ProgramError):
    code = "closed"


class NeedsInput(ProgramError):
    """Не хватает опорных весов: нужно спросить атлета (или выбрать level)."""
    code = "needs_input"

    def __init__(self, items: dict[str, dict]):
        super().__init__("needs_input: " + ", ".join(items))
        self.items = items     # lift -> ответ resolve_reference


class TemplateError(ProgramError):
    code = "template"

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors[:5]) + (f" (+{len(errors) - 5})" if len(errors) > 5 else ""))
        self.errors = errors


# --------------------------------------------------------------------------- округление

def round_kg(x: float, step: float = ROUNDING) -> float:
    """Округление к ближайшему шагу (половина — вверх)."""
    n = int(x / step + 0.5)
    v = n * step
    return int(v) if float(v).is_integer() else round(v, 2)


def _day(d) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        return date.fromisoformat(d[:10])
    return date.today()


# --------------------------------------------------------------------------- шаблоны

@lru_cache(maxsize=32)
def _load_template_cached(slug: str) -> str:
    p = PROGRAMS_DIR / f"{slug}.json"
    return p.read_text(encoding="utf-8")


def load_template(slug: str) -> dict:
    """Шаблон программы по слагу (свежая копия; проверен валидатором)."""
    if not slug or "/" in slug or slug in ("catalog", "template.schema"):
        raise NotFound(f"template {slug!r}")
    try:
        raw = _load_template_cached(slug)
    except FileNotFoundError:
        raise NotFound(f"template {slug!r}") from None
    tpl = json.loads(raw)
    validate_template(tpl)
    if tpl.get("slug") != slug:
        raise TemplateError([f"slug {tpl.get('slug')!r} != имя файла {slug!r}"])
    return tpl


def template_slugs() -> list[str]:
    return sorted(p.stem for p in PROGRAMS_DIR.glob("*.json") if p.stem not in ("catalog", "template.schema"))


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _bi(obj, path, errs):
    if not (isinstance(obj, dict) and all(isinstance(obj.get(k), str) and obj[k].strip() for k in ("ru", "en"))):
        errs.append(f"{path}: нужен объект с непустыми ru и en")


def template_errors(tpl: dict) -> list[str]:
    """Полная проверка шаблона; список сообщений (пустой = валиден)."""
    errs: list[str] = []
    if not isinstance(tpl, dict):
        return ["шаблон не объект"]
    if tpl.get("schema") != 1:
        errs.append("schema: ожидается 1")
    if not isinstance(tpl.get("slug"), str) or not tpl["slug"]:
        errs.append("slug: обязательная строка")
    if not (isinstance(tpl.get("version"), int) and tpl["version"] >= 1):
        errs.append("version: целое >= 1")
    _bi(tpl.get("title"), "title", errs)
    _bi(tpl.get("summary"), "summary", errs)
    if not isinstance(tpl.get("params"), dict):
        errs.append("params: объект")
    about = tpl.get("about")
    if about is not None:
        if not isinstance(about, list):
            errs.append("about: список блоков")
        else:
            for i, b in enumerate(about, 1):
                if not (isinstance(b, dict) and isinstance(b.get("id"), str)):
                    errs.append(f"about[{i}]: нужен объект с id")
                    continue
                _bi(b.get("title"), f"about[{i}].title", errs)
                _bi(b.get("text"), f"about[{i}].text", errs)
    wt = tpl.get("week_types")
    if wt is not None:
        if not isinstance(wt, dict) or any(k not in WEEK_TYPES for k in wt):
            errs.append(f"week_types: объект с ключами из {WEEK_TYPES}")
        else:
            for k, v in wt.items():
                _bi((v or {}).get("title"), f"week_types.{k}.title", errs)
                _bi((v or {}).get("text"), f"week_types.{k}.text", errs)
    lifts_decl: set[str] = set()
    for key, required in (("required_lifts", True), ("optional_lifts", False)):
        v = tpl.get(key, [] if not required else None)
        if not isinstance(v, list) or (required and not v):
            errs.append(f"{key}: список лифтов" + (" (непустой)" if required else ""))
            continue
        for lift in v:
            if lift not in ontology.MOVEMENTS or not ontology.is_weighted(lift):
                errs.append(f"{key}: {lift!r} не весовое движение онтологии")
            lifts_decl.add(lift)
    rules = tpl.get("rules")
    if not isinstance(rules, dict):
        errs.append("rules: объект")
    else:
        if rules.get("on_miss") not in ON_MISS_RULES:
            errs.append(f"rules.on_miss: одно из {ON_MISS_RULES}")
        dp = rules.get("deload_pct", 70)
        if not (_is_num(dp) and 40 <= dp <= 90):
            errs.append("rules.deload_pct: число 40..90")
        ip = rules.get("illness_drop_pct", 10)
        if not (_is_num(ip) and 0 <= ip <= 30):
            errs.append("rules.illness_drop_pct: число 0..30")
    weeks = tpl.get("weeks")
    if not isinstance(weeks, list) or not weeks:
        errs.append("weeks: непустой список")
        return errs
    for wi, w in enumerate(weeks, 1):
        wp = f"weeks[{wi}]"
        if not isinstance(w, dict):
            errs.append(f"{wp}: объект")
            continue
        if w.get("week") != wi:
            errs.append(f"{wp}.week: ожидается {wi} (нумерация подряд с 1)")
        if w.get("type") not in WEEK_TYPES:
            errs.append(f"{wp}.type: одно из {WEEK_TYPES}")
        _bi(w.get("title"), f"{wp}.title", errs)
        sess = w.get("sessions")
        if not isinstance(sess, list) or not sess:
            errs.append(f"{wp}.sessions: непустой список")
            continue
        last_dow = -1
        for si, s in enumerate(sess, 1):
            sp = f"{wp}.sessions[{si}]"
            if not isinstance(s, dict):
                errs.append(f"{sp}: объект")
                continue
            if s.get("idx") != si:
                errs.append(f"{sp}.idx: ожидается {si}")
            dow = s.get("dow")
            if not (isinstance(dow, int) and 0 <= dow <= 6):
                errs.append(f"{sp}.dow: 0..6 (0 = понедельник)")
            elif dow <= last_dow:
                errs.append(f"{sp}.dow: дни недели по возрастанию без повторов")
            else:
                last_dow = dow
            if s.get("kind", "normal") not in SESSION_KINDS:
                errs.append(f"{sp}.kind: одно из {SESSION_KINDS}")
            mn = s.get("minutes")
            if not (isinstance(mn, int) and 10 <= mn <= 120):
                errs.append(f"{sp}.minutes: целое 10..120")
            _bi(s.get("title"), f"{sp}.title", errs)
            if s.get("purpose") is not None:
                _bi(s["purpose"], f"{sp}.purpose", errs)
            blocks = s.get("blocks")
            if not isinstance(blocks, list) or not blocks:
                errs.append(f"{sp}.blocks: непустой список")
                continue
            seen_ex: set[str] = set()
            for bi, b in enumerate(blocks, 1):
                bp = f"{sp}.blocks[{bi}]"
                if not isinstance(b, dict):
                    errs.append(f"{bp}: объект")
                    continue
                _bi(b.get("title"), f"{bp}.title", errs)
                exs = b.get("exercises")
                if not isinstance(exs, list) or not exs:
                    errs.append(f"{bp}.exercises: непустой список")
                    continue
                for ei, ex in enumerate(exs, 1):
                    _check_exercise(ex, f"{bp}.exercises[{ei}]", lifts_decl, seen_ex, errs)
    return errs


def _check_pct(v, path, errs):
    if not (_is_num(v) and 10 <= v <= 110):
        errs.append(f"{path}: процент 10..110")


def _check_exercise(ex, p, lifts_decl, seen, errs):
    if not isinstance(ex, dict):
        errs.append(f"{p}: объект")
        return
    exid = ex.get("id")
    if not isinstance(exid, str) or not exid:
        errs.append(f"{p}.id: непустая строка")
    elif exid in seen:
        errs.append(f"{p}.id: {exid!r} повторяется в сессии")
    else:
        seen.add(exid)
    lift = ex.get("lift")
    if lift not in lifts_decl:
        errs.append(f"{p}.lift: {lift!r} не объявлен в required_lifts/optional_lifts")
    _bi(ex.get("name"), f"{p}.name", errs)
    steps = ex.get("steps")
    if not isinstance(steps, list) or not steps:
        errs.append(f"{p}.steps: непустой список")
        return
    for i, st in enumerate(steps, 1):
        sp = f"{p}.steps[{i}]"
        if not isinstance(st, dict):
            errs.append(f"{sp}: объект")
            continue
        kinds = [k for k in ("ladder", "sets", "day_max", "attempts") if k in st]
        if len(kinds) != 1:
            errs.append(f"{sp}: ровно один из ladder / sets / day_max / attempts")
            continue
        k = kinds[0]
        rs = st.get("rest_sec")
        if rs is not None:
            vals = rs if isinstance(rs, list) else [rs]
            if not all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 900 for x in vals):
                errs.append(f"{sp}.rest_sec: целое 0..900 секунд (для ladder можно список)")
            elif isinstance(rs, list) and (k != "ladder" or len(rs) != len(st["ladder"])):
                errs.append(f"{sp}.rest_sec: список только для ladder и по числу ступеней")
        if k == "ladder":
            lad = st["ladder"]
            if not isinstance(lad, list) or not lad:
                errs.append(f"{sp}.ladder: непустой список")
            else:
                for j, it in enumerate(lad):
                    if isinstance(it, dict):
                        _check_pct(it.get("pct"), f"{sp}.ladder[{j}].pct", errs)
                        r = it.get("reps", 1)
                        if not (isinstance(r, int) and 1 <= r <= 30):
                            errs.append(f"{sp}.ladder[{j}].reps: целое 1..30")
                    else:
                        _check_pct(it, f"{sp}.ladder[{j}]", errs)
            r = st.get("reps", 1)
            if not (isinstance(r, int) and 1 <= r <= 30):
                errs.append(f"{sp}.reps: целое 1..30")
        elif k == "sets":
            if not (isinstance(st["sets"], int) and 1 <= st["sets"] <= 20):
                errs.append(f"{sp}.sets: целое 1..20")
            r = st.get("reps")
            if not (isinstance(r, int) and 1 <= r <= 30):
                errs.append(f"{sp}.reps: целое 1..30")
            if "load" in st:
                ld = st["load"]
                if not isinstance(ld, dict):
                    errs.append(f"{sp}.load: объект {{lift, pct, rounding}}")
                else:
                    if ld.get("lift", lift) not in lifts_decl:
                        errs.append(f"{sp}.load.lift: не объявлен")
                    _check_pct(ld.get("pct"), f"{sp}.load.pct", errs)
                    if ld.get("rounding", ROUNDING) not in (1, 2.5, 5):
                        errs.append(f"{sp}.load.rounding: 1, 2.5 или 5")
            else:
                _check_pct(st.get("pct"), f"{sp}.pct", errs)
        elif k == "day_max":
            dm = st["day_max"]
            if not isinstance(dm, dict):
                errs.append(f"{sp}.day_max: объект {{pct, tries}}")
            else:
                _check_pct(dm.get("pct"), f"{sp}.day_max.pct", errs)
                if not (isinstance(dm.get("tries"), int) and 1 <= dm["tries"] <= 6):
                    errs.append(f"{sp}.day_max.tries: целое 1..6")
        else:
            at = st["attempts"]
            if not isinstance(at, list) or not at:
                errs.append(f"{sp}.attempts: непустой список процентов")
            else:
                for j, v in enumerate(at):
                    _check_pct(v, f"{sp}.attempts[{j}]", errs)


def validate_template(tpl: dict) -> dict:
    """Проверка шаблона; при ошибках TemplateError со всем списком. Возвращает шаблон."""
    errs = template_errors(tpl)
    if errs:
        raise TemplateError(errs)
    return tpl


# --------------------------------------------------------------------------- резолвер опорных весов

def athlete_profile(con: sqlite3.Connection, uid: int, now=None) -> dict:
    """{sex: 'm'|'f'|None, bodyweight: float|None} из профиля (вес: users, затем последний из daily)."""
    row = con.execute('SELECT "sex","weight_kg" FROM users WHERE "tg_id"=?', (int(uid),)).fetchone()
    sex = row["sex"] if row and row["sex"] in ("m", "f") else None
    bw = row["weight_kg"] if row and row["weight_kg"] else None
    if not bw:
        r = con.execute('SELECT "weight_kg" FROM daily WHERE "tg_id"=? AND "weight_kg" IS NOT NULL '
                        'ORDER BY "day" DESC LIMIT 1', (int(uid),)).fetchone()
        bw = r["weight_kg"] if r else None
    return {"sex": sex, "bodyweight": float(bw) if bw else None}


def starter_options(lift: str, sex: str | None, bodyweight: float | None) -> dict[str, int] | None:
    """{careful, normal, experienced} = пороги[0]/[1]/[2] × вес тела × 0.9, целые кг.
    Пример: мужчина 80 кг, squat_snatch (.47/.67/.92) -> 34/48/66."""
    meta = standards.disciplines().get(lift)
    if not meta or meta.get("kind") != "lift" or sex not in ("m", "f") or not bodyweight:
        return None
    thr = meta["thresholds"][sex]
    return {lv: int(thr[i] * bodyweight * STARTER_FACTOR + 0.5) for i, lv in enumerate(LEVELS)}


def _best_map(con: sqlite3.Connection, uid: int, now: date) -> dict[str, dict]:
    """lift -> {kg, day, stale}. Реальный вес (best_results), не Эпли. Если лучший старше FRESH_DAYS,
    но есть более свежий результат в окне — берём свежий (не stale)."""
    from tjbot.db import best_results
    out: dict[str, dict] = {}
    cutoff = (now - timedelta(days=FRESH_DAYS)).isoformat()
    for did, r in best_results(con, uid).items():
        meta = standards.disciplines().get(did)
        if not meta or meta["kind"] != "lift" or r.get("value") is None:
            continue
        kg, day = float(r["value"]), r.get("day")
        stale = not day or str(day)[:10] < cutoff
        if stale:
            fr = con.execute(
                'SELECT "value","day" FROM discipline_results WHERE "tg_id"=? AND "discipline"=? '
                'AND "value" IS NOT NULL AND "day">=? ORDER BY "value" DESC LIMIT 1',
                (int(uid), did, cutoff)).fetchone()
            if fr:
                kg, day, stale = float(fr["value"]), fr["day"], False
        out[did] = {"kg": kg, "day": day, "stale": stale}
    return out


def _derive(lift: str, bests: dict, visited: frozenset = frozenset()):
    """(kg, stale, path) по цепочке коэффициентов; сначала прямые от реальных максов, затем через промежуточный лифт."""
    cands = DERIVE.get(lift, [])
    for src, k in cands:
        if src in bests:
            b = bests[src]
            return b["kg"] * k, b["stale"], [src]
    for src, k in cands:
        if src in visited:
            continue
        sub = _derive(src, bests, visited | {lift})
        if sub:
            return sub[0] * k, sub[1], sub[2] + [src]
    return None


def resolve_reference(con: sqlite3.Connection, uid: int, lift: str, now=None, level: str | None = None,
                      *, _bests: dict | None = None) -> dict:
    """Опорный вес атлета по лифту. Цепочка:
      1. best    — лучший реальный результат (свежесть <= 60 дней, иначе stale=True);
      2. derived — от родственного лифта по коэффициентам DERIVE;
      3. needs_input — вопрос атлету (+ варианты стартового уровня в `options`, если известны пол и вес);
      4. starter — если задан level (careful|normal|experienced): порог × вес × 0.9.
    -> {lift, kg, source, stale, note, note_en, ...}."""
    now_d = _day(now)
    bests = _bests if _bests is not None else _best_map(con, uid, now_d)
    name_ru = (standards.disciplines().get(lift) or {}).get("name_ru") or ontology.base_ru(lift) or lift
    if lift in bests:
        b = bests[lift]
        note = f"Твой лучший результат: {_fmt(b['kg'])} кг ({b['day']})."
        note_en = f"Your best result: {_fmt(b['kg'])} kg ({b['day']})."
        if b["stale"]:
            note += f" Результату больше {FRESH_DAYS} дней: лучше обновить тестом."
            note_en += f" The result is older than {FRESH_DAYS} days: better refresh with a test."
        return {"lift": lift, "kg": b["kg"], "source": "best", "stale": b["stale"], "day": b["day"],
                "note": note, "note_en": note_en}
    d = _derive(lift, bests)
    if d:
        kg, stale, path = d
        chain = " → ".join(path)
        return {"lift": lift, "kg": round_kg(kg), "source": "derived", "stale": stale, "from": path,
                "note": f"Оценка по {chain} (коэффициенты примерные, уточнятся тест-сессией).",
                "note_en": f"Estimated from {chain} (rough coefficients, refined by a test session)."}
    prof = athlete_profile(con, uid, now_d)
    opts = starter_options(lift, prof["sex"], prof["bodyweight"])
    if level is not None:
        if level not in LEVELS:
            raise ProgramError(f"level: одно из {LEVELS}")
        if opts:
            return {"lift": lift, "kg": opts[level], "source": "starter", "stale": False, "level": level,
                    "note": f"Стартовый уровень «{_LEVEL_RU[level]}» по нормативам: {opts[level]} кг. Уточнится тест-сессией.",
                    "note_en": f"Starter level '{level}' from standards: {opts[level]} kg. Refined by a test session."}
    return {"lift": lift, "kg": None, "source": "needs_input", "stale": False, "options": opts,
            "question": {"ru": f"Твой максимум: {name_ru.lower()}?", "en": f"Your max for {lift.replace('_', ' ')}?"},
            "note": "Нет данных. Введи максимум или выбери стартовый уровень." if opts
                    else "Нет данных. Введи максимум (для стартового уровня нужны пол и вес тела в профиле).",
            "note_en": "No data. Enter your max or pick a starter level." if opts
                       else "No data. Enter your max (a starter level needs sex and bodyweight in the profile)."}


_LEVEL_RU = {"careful": "осторожный", "normal": "обычный", "experienced": "опытный"}


def _fmt(kg) -> str:
    return str(int(kg)) if float(kg).is_integer() else str(round(float(kg), 1))


# --------------------------------------------------------------------------- чек-ин

def checkin_adjust(checkin: dict | None, rules: dict | None = None, kind: str = "normal") -> dict:
    """Детерминированная поправка нагрузки по чек-ину готовности.
    Поля: energy 1..5 (1 — нет сил), tired, sleepy (плохой сон), joint (болит сустав), ill (после болезни).
    Правила (проценты — пункты от максимума: 75% → 70%):
      • устал И (плохо спал ИЛИ energy <= 2), либо три и больше сигналов -> «неделя 70%»: веса не выше deload_pct;
      • иначе после болезни -> −illness_drop_pct (по умолчанию −10);
      • иначе любой сигнал (устал / болит сустав / плохой сон / energy <= 2) -> −5.
    Тест-сессию не снижаем, только советуем перенести. -> {level, delta_pct, cap_pct, why, why_en, ...}"""
    rules = rules or {}
    c = checkin or {}
    energy = c.get("energy")
    low = isinstance(energy, (int, float)) and not isinstance(energy, bool) and energy <= 2
    sig = []   # (ключ, ru, en)
    if c.get("tired"):
        sig.append(("tired", "устал", "tired"))
    if c.get("sleepy"):
        sig.append(("sleepy", "плохо спал", "slept badly"))
    if c.get("joint"):
        sig.append(("joint", "болит сустав", "joint pain"))
    if c.get("ill"):
        sig.append(("ill", "после болезни", "after illness"))
    if low:
        sig.append(("energy", "мало сил", "low energy"))
    out = {"level": "none", "delta_pct": 0, "cap_pct": None, "why": None, "why_en": None,
           "signals": [k for k, _, _ in sig], "postpone_advised": False}
    if not sig:
        return out
    ru = ", ".join(r for _, r, _ in sig)
    en = ", ".join(e for _, _, e in sig)
    keys = {k for k, _, _ in sig}
    deload = float(rules.get("deload_pct", 70))
    if ("tired" in keys and ("sleepy" in keys or "energy" in keys)) or len(sig) >= 3:
        out.update(level="cap", cap_pct=deload,
                   why=f"Чек-ин: {ru}. Лёгкий день: веса не выше {_fmt(deload)}% от максимума.",
                   why_en=f"Check-in: {en}. Light day: weights capped at {_fmt(deload)}% of max.")
    elif "ill" in keys:
        d = float(rules.get("illness_drop_pct", 10))
        out.update(level="illness", delta_pct=-d,
                   why=f"Чек-ин: {ru}. Веса ниже на {_fmt(d)} пунктов процента от максимума.",
                   why_en=f"Check-in: {en}. Weights lowered by {_fmt(d)} percentage points of max.")
    else:
        out.update(level="minus5", delta_pct=-5.0,
                   why=f"Чек-ин: {ru}. Веса ниже на 5 пунктов процента от максимума.",
                   why_en=f"Check-in: {en}. Weights lowered by 5 percentage points of max.")
    if kind == "test":
        out.update(level="none", delta_pct=0, cap_pct=None, postpone_advised=True,
                   why=f"Чек-ин: {ru}. Тест максимума лучше перенести на день с хорошей готовностью; веса теста не меняем.",
                   why_en=f"Check-in: {en}. Better postpone the max test to a well-rested day; test weights unchanged.")
    return out


# --------------------------------------------------------------------------- разворачивание сессии

def set_id(session_id: str, ex_id: str, n: int) -> str:
    return str(uuid.uuid5(_NS, f"{session_id}:{ex_id}:{n}"))


def expand_session(spec: dict, base_maxes: dict, session_id: str, *, adjust: dict | None = None,
                   misses: list[dict] | None = None, bar_kg: float = 20.0) -> list[dict]:
    """Формулы сессии -> плоский список подходов.
    spec: {blocks:[{exercises:[{id,lift,name,steps}]}]}; base_maxes: {lift: {kg,...}};
    adjust: результат checkin_adjust; misses: [{lift, after_seq, drop_kg}] — правило on_miss.
    Подход: {id, exercise, lift, name, seq, n, kind, pct, planned_kg, reps, rounding}.
    Без базы по лифту planned_kg = None."""
    adjust = adjust or {}
    delta = float(adjust.get("delta_pct") or 0)
    cap = adjust.get("cap_pct")
    misses = misses or []
    out: list[dict] = []

    def add(ex, kind, pct, reps, lift, rounding, n_by, rest=None):
        seq = len(out)
        n = n_by[ex["id"]] = n_by.get(ex["id"], -1) + 1
        eff = pct + delta
        if cap is not None:
            eff = min(eff, float(cap))
        eff = max(eff, 0.0)
        base = (base_maxes.get(lift) or {}).get("kg")
        kg = None
        if base:
            raw = float(base) * eff / 100.0
            raw -= sum(m["drop_kg"] for m in misses if m["lift"] == lift and seq > m["after_seq"])
            kg = max(bar_kg, round_kg(max(raw, 0), rounding))
        out.append({"id": set_id(session_id, ex["id"], n), "exercise": ex["id"], "lift": lift,
                    "name": ex["name"], "seq": seq, "n": n, "kind": kind, "pct": pct,
                    "eff_pct": round(eff, 2), "planned_kg": kg, "reps": reps, "rounding": rounding,
                    "rest_sec": rest if rest is not None else default_rest_sec(kind, pct)})

    n_by: dict[str, int] = {}
    for b in spec.get("blocks", []):
        for ex in b.get("exercises", []):
            lift = ex["lift"]
            for st in ex["steps"]:
                if "ladder" in st:
                    rs = st.get("rest_sec")
                    for i, it in enumerate(st["ladder"]):
                        pct, reps = (it["pct"], it.get("reps", 1)) if isinstance(it, dict) else (it, st.get("reps", 1))
                        add(ex, "ladder", pct, reps, lift, ROUNDING, n_by, rs[i] if isinstance(rs, list) else rs)
                elif "sets" in st:
                    ld = st.get("load") or {"pct": st.get("pct"), "lift": lift}
                    for _ in range(st["sets"]):
                        add(ex, "work", ld["pct"], st["reps"], ld.get("lift", lift),
                            ld.get("rounding", st.get("rounding", ROUNDING)), n_by, st.get("rest_sec"))
                elif "day_max" in st:
                    for _ in range(st["day_max"]["tries"]):
                        add(ex, "day_max", st["day_max"]["pct"], 1, lift, ROUNDING, n_by, st.get("rest_sec"))
                elif "attempts" in st:
                    prev = None
                    for pct in st["attempts"]:
                        add(ex, "attempt", pct, 1, lift, ROUNDING, n_by, st.get("rest_sec"))
                        s = out[-1]
                        if prev is not None and s["planned_kg"] is not None and s["planned_kg"] < prev + ROUNDING:
                            s["planned_kg"] = prev + ROUNDING   # каждая попытка минимум на шаг тяжелее
                        prev = s["planned_kg"]
    return out


def apply_miss(resolved: list[dict], failed: dict, drop_kg: float = MISS_DROP_KG, bar_kg: float = 20.0) -> list[str]:
    """Правило on_miss «не вышло −> −5 кг и продолжай»: все ещё не отмеченные подходы этого лифта
    ниже по сессии становятся на drop_kg легче. `failed` — подход из resolved. Возвращает id изменённых.
    (Постоянное состояние — список misses в плане; это для мгновенного пересчёта.)"""
    changed = []
    for s in resolved:
        if s["lift"] == failed["lift"] and s["seq"] > failed["seq"] and s.get("planned_kg") is not None:
            new = max(bar_kg, s["planned_kg"] - drop_kg)
            if new != s["planned_kg"]:
                s["planned_kg"] = new
                changed.append(s["id"])
    return changed


def build_test_spec(lifts: list[str]) -> dict:
    """Тест-сессия «день 0»: по каждому лифту лесенка 50→95% от оценки и три попытки на «максимум дня»."""
    exs = []
    for lift in lifts:
        nm = {"ru": (standards.disciplines().get(lift) or {}).get("name_ru") or ontology.base_ru(lift) or lift,
              "en": (standards.disciplines().get(lift) or {}).get("name_en") or lift.replace("_", " ").title()}
        exs.append({"id": lift, "lift": lift, "name": nm,
                    "steps": [{"ladder": [50, 60, 70, 80, 85, 90, 95], "reps": 1,
                               "rest_sec": [60, 60, 90, 120, 150, 150, 180]},
                              {"attempts": [100, 103, 106], "rest_sec": 240}]})
    return {"kind": "test", "minutes": 60,
            "title": {"ru": "Тест-сессия: максимум дня", "en": "Test session: max of the day"},
            "blocks": [{"title": {"ru": "Лесенка до максимума", "en": "Ladder to a max"}, "exercises": exs}]}
