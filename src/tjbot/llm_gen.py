"""Генерация ИИ-разборов в llm_cache — общий код бота и приложения.

Раньше жил в tjapp.api и был недоступен бот-процессу (flight-review), из-за
чего «Разбор полётов» не наполнял Сводку/питание. Здесь — чистые (без FastAPI)
строители payload + генератор «собрать→coach()→положить в кэш»; зовут и
api.py (кнопка «Разобрать ИИ»), и claude_review.py (flight-review/крон).
"""
from __future__ import annotations

import json
import traceback
from datetime import date, timedelta

from tj.analysis import llm_coach
from tj.analysis import nutrition as _nutr
from tj.analysis import nutrition_goals as ng
from tj.analysis.competitions import total_report
from tj.analysis.dashboard import summary_data
from tj.analysis.workouts import workout_report

from . import db as botdb


def user_targets(con, tg_id: int, upto_day: str | None = None):
    """Профиль+цель → (goal, вес на дату, нормы КБЖУ | None). Единая точка расчёта."""
    u = botdb.get_user(con, tg_id)
    goal = botdb.user_goal(con, tg_id)
    weight = botdb.latest_weight(con, tg_id, upto_day)
    tgt = ng.targets(u["sex"] if u else "m", u["age"] if u else None,
                     u["height_cm"] if u else None,
                     weight or (u["weight_kg"] if u else None), goal)
    return goal, weight, tgt


def nutrition_day_block(con, tg_id: int, day: str) -> dict | None:
    meals = botdb.meals_for_day(con, tg_id, day)
    if not meals:
        return None
    t = _nutr.day_totals(meals)
    t["water_l"] = botdb.water_for_day(con, tg_id, day)
    t["meals"] = len(meals)
    return t


def build_payload(con, db_path, kind: str, ref: str, tg_id: int):
    if kind not in ("workout", "summary", "competitions", "nutr_day", "nutr_week"):
        return None
    if kind in ("nutr_day", "nutr_week"):
        return nutr_payload(con, tg_id, ref, week=(kind == "nutr_week"))
    if kind == "competitions":
        tr = total_report(con, tg_id)
        if not tr or not tr.get("starts"):
            return None
        # radars — данные графика, narrative — наш же шаблонный текст: ИИ не нужны
        return {k: v for k, v in tr.items() if k not in ("radars", "narrative")}
    hr_max, sex = botdb.profile_hr_sex(con, tg_id)
    if kind == "workout":
        rep = workout_report(db_path, "sqlite", hr_max, sex, ref, tg_id=tg_id)
        if rep is None:
            return None
        payload = llm_coach.workout_payload(rep)
        payload["bodyweight_kg"] = botdb.latest_weight(con, tg_id, ref)
        payload["nutrition"] = nutrition_day_block(con, tg_id, ref)
        return payload
    data = summary_data(db_path, "sqlite", hr_max, sex, date.today(), tg_id=tg_id)
    # Нет дней в daily/activities → range (None, None), n_days=0: нечего разбирать
    # (симметрично competitions без стартов).
    if not (data.get("m") or {}).get("n_days"):
        return None
    payload = llm_coach.summary_payload(data)
    payload["weight_kg"] = botdb.latest_weight(con, tg_id)
    ns = _nutr.period_summary(botdb.nutrition_days(con, tg_id, days=7),
                              botdb.water_days(con, tg_id), payload["weight_kg"])
    payload["nutrition7"] = ns if ns.get("days") else None
    return payload


def nutr_payload(con, tg_id: int, ref: str, week: bool):
    """Payload ИИ-разбора питания: день (ref) или неделя до ref включительно.
    Три батч-запроса на весь диапазон (meals/water/activities), без per-day циклов."""
    goal, weight, tgt = user_targets(con, tg_id, ref)
    try:
        end = date.fromisoformat(ref)
    except ValueError:
        return None
    first = (end - timedelta(days=6 if week else 0)).isoformat()
    meals_by_day: dict[str, list[dict]] = {}
    for r in con.execute(
            'SELECT "day","foods","kcal","protein_g","fat_g","carb_g","quality" '
            'FROM meals WHERE "tg_id"=? AND "day">=? AND "day"<=? ORDER BY "ts"',
            (tg_id, first, ref)):
        m = dict(r)
        try:
            m["foods"] = json.loads(m["foods"]) if m["foods"] else []
        except ValueError:
            m["foods"] = []
        meals_by_day.setdefault(m["day"], []).append(m)
    if not meals_by_day:
        return None
    water = {r["day"]: r["liters"] for r in con.execute(
        'SELECT "day","liters" FROM water_log WHERE "tg_id"=? AND "day">=? AND "day"<=?',
        (tg_id, first, ref))}
    # ручная WOD-запись и garmin-биометрия одной сессии (день+спорт, разный source)
    # — это ОДНА тренировка; сливаем, иначе в промпт уходят «две тренировки».
    sessions: list[dict] = []
    for r in con.execute(
            'SELECT "day","sport","calories","source","extra" FROM activities '
            'WHERE "tg_id"=? AND "day">=? AND "day"<=?', (tg_id, first, ref)):
        cal = int(r["calories"] or 0)
        try:
            sweat = int((json.loads(r["extra"] or "{}")).get("sweat_loss_ml") or 0)
        except (ValueError, TypeError):
            sweat = 0
        src = r["source"]
        same = next((s for s in sessions if s["day"] == r["day"]
                     and s["sport"] == r["sport"] and src not in s["sources"]), None)
        if same is not None:
            same["calories"] = max(same["calories"], cal)
            same["sweat"] = max(same["sweat"], sweat)
            same["sources"].add(src)
        else:
            sessions.append({"day": r["day"], "sport": r["sport"], "calories": cal,
                             "sweat": sweat, "sources": {src}})
    workouts = [{"day": s["day"], "sport": s["sport"], "calories": s["calories"] or None}
                for s in sessions]
    burned_by_day: dict[str, int] = {}
    sweat_by_day: dict[str, int] = {}
    for s in sessions:
        burned_by_day[s["day"]] = burned_by_day.get(s["day"], 0) + s["calories"]
        sweat_by_day[s["day"]] = sweat_by_day.get(s["day"], 0) + s["sweat"]
    day_blocks = [
        {"day": d, "totals": _nutr.day_totals(meals_by_day[d]),
         "verdict": _nutr.day_verdict(meals_by_day[d]),
         "water_l": round(water.get(d) or 0, 2),
         "water_target_l": ng.water_target_l(sweat_by_day.get(d, 0)),
         "burned": burned_by_day.get(d, 0)}
        for d in sorted(meals_by_day)]
    return {"period": "week" if week else "day", "goal": goal,
            "city": botdb.user_city(con, tg_id), "weight_kg": weight,
            "targets": tgt, "days": day_blocks, "workouts": workouts,
            "logged_days": len(day_blocks)}


def finalize(con, tg_id: int, kind: str, ref: str, text: str, engine: str,
            lang: str) -> str:
    """Побочные артефакты разбора (совет в Сводке, компакт-блоки тренировки).
    Возвращает текст для показа (у workout срезаются служебные блоки)."""
    if kind == "summary":
        line = llm_coach.parse_advice_line(text, lang)
        if line:
            botdb.next_advice_put(con, tg_id, engine, line, lang=lang)
    elif kind == "workout":
        blocks = llm_coach.parse_workout_blocks(text, lang)
        if blocks:
            botdb.wk_narrative_put(con, tg_id, ref, engine, blocks, lang=lang)
            text = llm_coach.strip_workout_blocks(text, lang)
    return text


def generate_one(con, db_path, tg_id: int, kind: str, ref: str, lang: str,
                 *, force: bool = False, refresh_stale: bool = False) -> bool:
    """Собрать payload → coach() → finalize → положить в llm_cache.
    force=False и разбор уже в кэше → пропуск; refresh_stale=True — кэш есть,
    но payload_hash изменился → перегенерация (критерий stale как в GET
    /api/llm). Возвращает True, если записал."""
    stored = None
    if not force:
        stored = botdb.llm_cache_get_latest(con, tg_id, kind, ref, lang)
        if stored and not refresh_stale:
            return False
    payload = build_payload(con, db_path, kind, ref, tg_id)
    if payload is None:
        return False
    astro = botdb.user_astro(con, tg_id)
    h = llm_coach.payload_hash(payload, lang, astro)
    if stored and stored["data_hash"] == h:
        return False
    text, engine = llm_coach.coach(kind, payload, lang, astro)
    if not text:
        return False
    if force:
        botdb.llm_cache_delete(con, tg_id, kind, ref)
    text = finalize(con, tg_id, kind, ref, text, engine, lang)
    botdb.llm_cache_put(con, tg_id, kind, ref, h, text, engine, lang=lang)
    return True


def sweep_targets(con, tg_id: int, window_days: int = 6) -> list[tuple[str, str]]:
    """Цели разбора за окно: summary, соревнования, тренировки, дни питания,
    недельный свод питания.

    Текущий день в питание не берём: он ещё не прожит, ужина в нём нет, и разбор
    получается по половине дня. Недельный свод тоже привязан к последнему
    завершённому дню."""
    since = (date.today() - timedelta(days=window_days)).isoformat()
    today = date.today().isoformat()
    targets: list[tuple[str, str]] = [("summary", "30d"), ("competitions", "total")]
    for r in con.execute('SELECT DISTINCT "day" AS d FROM activities '
                         'WHERE "tg_id"=? AND "day">=? ORDER BY "day"', (tg_id, since)):
        targets.append(("workout", r["d"]))
    nutr_days = [r["d"] for r in con.execute(
        'SELECT DISTINCT "day" AS d FROM meals WHERE "tg_id"=? AND "day">=? AND "day"<? '
        'ORDER BY "day"', (tg_id, since, today))]
    for d in nutr_days:
        targets.append(("nutr_day", d))
    if nutr_days:
        targets.append(("nutr_week", nutr_days[-1]))
    return targets


def sweep(con, db_path, tg_id: int, lang: str, *, force: bool = False,
          refresh_stale: bool = False, kinds: set | None = None,
          skip: tuple | None = None, window_days: int = 6) -> list[dict]:
    """Прогон целей sweep_targets через generate_one. kinds — ограничить набор
    (напр. {'summary','nutr_day','nutr_week','competitions'}). skip — (kind,ref)
    пропустить. Ошибки — лог + список, прогон продолжается."""
    errors: list[dict] = []
    for k, ref in sweep_targets(con, tg_id, window_days):
        if kinds is not None and k not in kinds:
            continue
        if skip is not None and (k, ref) == skip:
            continue
        try:
            generate_one(con, db_path, tg_id, k, ref, lang, force=force,
                         refresh_stale=refresh_stale)
        except Exception as e:
            print(f"[llm] sweep {k}/{ref} для {tg_id}: {e!r}", flush=True)
            traceback.print_exc()
            errors.append({"kind": k, "ref": ref, "error": f"{type(e).__name__}: {e}"})
    return errors
