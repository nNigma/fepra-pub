"""FastAPI Mini App: статика + JSON-API сводки поверх training.db.

Данные сводки — общий summary_data() из tj.analysis.dashboard (тот же, что у
HTML-дашборда Obsidian). Доступ к API — по валидному initData (allowlist).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tj import config as cfgmod
from tj import llm as _llm
from tj.analysis.competitions import event_report, total_report
from tj.analysis.dashboard import summary_data
from tj.analysis.levels import goals_screen_data
from tj.analysis.workouts import recent_workouts, workout_report
from tj.analysis import llm_coach
from tj.analysis import activity_stats as _stats
from tj.analysis import watch_advice as _watch
from tj.analysis import nutrition as _nutr
from tj.analysis import nutrition_goals as ng
from tjbot import db as botdb
from tjbot.access import LLM_DAILY_LIMIT, is_admin, is_pro, llm_quota_consume, llm_quota_remaining
from .auth import AuthError, authorized_user, resolve_effective_user

has_llm = _llm.has_llm

_STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Кузница — Mini App")


def _athlete() -> tuple[int, str]:
    try:
        cfg = cfgmod.load_config()
    except FileNotFoundError:
        cfg = {}
    return cfgmod.athlete(cfg)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html", headers={"Cache-Control": "no-cache"})


def require_auth(x_init_data: str = Header(default="")) -> dict:
    try:
        return authorized_user(x_init_data)
    except AuthError as e:
        from urllib.parse import parse_qsl

        keys = [k for k, _ in parse_qsl(x_init_data)]
        print(f"[auth] 401: {e} | поля initData: {keys}", flush=True)
        raise HTTPException(status_code=401, detail=str(e))


def _db() -> str:
    return str(botdb.default_db_path())


def _req_lang(user: dict) -> str:
    con = botdb.connect(_db())
    try:
        return botdb.user_lang(con, user["id"])
    finally:
        con.close()


class LangIn(BaseModel):
    lang: str


@app.post("/api/lang")
async def api_set_lang(body: LangIn, user: dict = Depends(require_auth)):
    if body.lang not in ("ru", "en"):
        raise HTTPException(status_code=400, detail="bad lang")
    con = botdb.connect(_db())
    botdb.set_lang(con, user["id"], body.lang)
    con.close()
    return {"lang": body.lang}


def _recent_days(con, tg_id: int, lookback: int = 14) -> list[dict]:
    """Последние дни daily для «Тюнинга часов» (колонки + extra)."""
    rows = con.execute(
        'SELECT "readiness","hrv","stress_avg","sleep_h","extra" FROM daily '
        'WHERE "tg_id"=? ORDER BY "day" DESC LIMIT ?', (tg_id, lookback)).fetchall()
    out = []
    for r in rows:
        try:
            ex = json.loads(r["extra"]) if r["extra"] else {}
        except ValueError:
            ex = {}
        out.append({"readiness": r["readiness"], "hrv": r["hrv"],
                    "stress_avg": r["stress_avg"], "sleep_h": r["sleep_h"],
                    "extra": ex})
    return out


def _require_pro(user: dict) -> None:
    if not (is_admin(user["id"]) or is_pro(user["id"])):
        raise HTTPException(status_code=403, detail="нужен Pro")


def _user_targets(con, tg_id: int, upto_day: str | None = None):
    """Профиль+цель → (goal, вес на дату, нормы КБЖУ | None). Единая точка расчёта."""
    u = botdb.get_user(con, tg_id)
    goal = botdb.user_goal(con, tg_id)
    weight = botdb.latest_weight(con, tg_id, upto_day)
    tgt = ng.targets(u["sex"] if u else "m", u["age"] if u else None,
                     u["height_cm"] if u else None,
                     weight or (u["weight_kg"] if u else None), goal)
    return goal, weight, tgt


@app.get("/api/nutrition")
async def api_nutrition(user: dict = Depends(require_auth),
                        day: str | None = Query(default=None),
                        as_user: int | None = Query(default=None, alias="as")):
    _require_pro(user)
    eff = resolve_effective_user(user["id"], as_user)
    lang = _req_lang(user)
    d = day or date.today().isoformat()
    con = botdb.connect(_db())
    try:
        meals = botdb.meals_for_day(con, eff, d)
        water = botdb.water_for_day(con, eff, d)
        goal, weight, tgt = _user_targets(con, eff, d)
        burned = ng.burned(con, eff, d)
        water_target = ng.water_target_l(ng.sweat_ml(con, eff, d))
    finally:
        con.close()
    totals = _nutr.day_totals(meals)
    ppk = round(totals["protein_g"] / weight, 2) if weight and totals["protein_g"] else None
    return {"day": d, "meals": meals, "totals": totals, "water_l": water,
            "weight_kg": weight, "protein_per_kg": ppk,
            "advice": _nutr.day_advice(totals, water, weight, lang),
            "targets": tgt, "burned": burned, "water_target_l": water_target,
            "goal": goal, "day_verdict": _nutr.day_verdict(meals),
            "pro": is_pro(user["id"])}


@app.get("/api/nutrition/days")
async def api_nutrition_days(user: dict = Depends(require_auth),
                             as_user: int | None = Query(default=None, alias="as")):
    _require_pro(user)
    eff = resolve_effective_user(user["id"], as_user)
    con = botdb.connect(_db())
    try:
        days = botdb.nutrition_days(con, eff, days=30)
        qualities = botdb.meal_qualities_by_day(con, eff)
        goal, weight, tgt = _user_targets(con, eff)
    finally:
        con.close()
    for row in days:
        row["verdict"] = _nutr.day_verdict(qualities.get(row["day"]))
    return {"days": days, "weight_kg": weight, "targets": tgt, "goal": goal}


@app.get("/api/summary")
async def api_summary(user: dict = Depends(require_auth), as_user: int | None = Query(default=None, alias="as")):
    eff = resolve_effective_user(user["id"], as_user)
    lang = _req_lang(user)
    con = botdb.connect(_db())
    try:
        hr_max, sex = botdb.profile_hr_sex(con, eff)
        data = summary_data(_db(), "sqlite", hr_max, sex, date.today(), tg_id=eff, lang=lang)
        data["pro"] = is_pro(user["id"])
        data["is_admin"] = is_admin(user["id"])
        data["viewing"] = eff
        data["lang"] = lang
        ai = botdb.next_advice_get(con, eff, lang)
        dv = botdb.data_version(con)
        data["watch_tuning"] = _watch.evaluate(
            botdb.load_devices(con, eff), _recent_days(con, eff))
        _, w7, tgt7 = _user_targets(con, eff)
        days7 = botdb.nutrition_days(con, eff, days=7)
        ns = _nutr.period_summary(days7, botdb.water_days(con, eff), w7, targets=tgt7)
        ns["micro_flags"] = _nutr.micro_week_flags(days7)
        qual_by_day = botdb.meal_qualities_by_day(con, eff)
        verdicts = []
        for vd in sorted(qual_by_day)[-7:]:
            v = _nutr.day_verdict(qual_by_day[vd])
            if v is not None:
                verdicts.append({"day": vd, "v": v})
        ns["verdicts"] = verdicts
        data["nutrition7"] = ({**ns, "advice": _nutr.period_advice(ns, lang)}
                              if ns.get("days") else None)
    finally:
        con.close()
    if ai and ai.get("text"):
        base = data.get("advice") or {}
        created = ai.get("created_at")
        data["advice"] = {"level": base.get("level", "green"),
                          "title": base.get("title", "Совет"),
                          "text": ai["text"], "source": ai["source"],
                          "date": created,
                          "stale": bool(dv and created and dv > created)}
    if isinstance(data.get("advice"), dict):
        data["advice"].setdefault("date", date.today().isoformat())
        data["advice"].setdefault("stale", False)
    return data


@app.get("/api/users")
async def api_users(user: dict = Depends(require_auth)):
    if not is_admin(user["id"]):
        raise HTTPException(status_code=403, detail="только админ")
    con = botdb.connect(_db())
    try:
        return botdb.all_users(con)
    finally:
        con.close()


@app.get("/api/workouts")
async def api_workouts(user: dict = Depends(require_auth), limit: int = 30, as_user: int | None = Query(default=None, alias="as")):
    eff = resolve_effective_user(user["id"], as_user)
    return recent_workouts(_db(), "sqlite", limit, tg_id=eff, lang=_req_lang(user))


@app.get("/api/workout/{day}")
async def api_workout(day: str, user: dict = Depends(require_auth), as_user: int | None = Query(default=None, alias="as")):
    eff = resolve_effective_user(user["id"], as_user)
    lang = _req_lang(user)
    con = botdb.connect(_db())
    try:
        hr_max, sex = botdb.profile_hr_sex(con, eff)
        rep = workout_report(_db(), "sqlite", hr_max, sex, day, tg_id=eff, lang=lang)
        if rep is None:
            raise HTTPException(status_code=404, detail="нет тренировки на эту дату")
        rep["pro"] = is_pro(user["id"])
        ai = botdb.wk_narrative_get(con, eff, day, lang)
    finally:
        con.close()
    if ai and ai.get("blocks") and rep.get("sessions"):
        rep["sessions"][0]["narrative"] = ai["blocks"]
        rep["narrative_source"] = ai["source"]
    return rep


@app.get("/api/competitions")
async def api_competitions(user: dict = Depends(require_auth), as_user: int | None = Query(default=None, alias="as")):
    eff = resolve_effective_user(user["id"], as_user)
    con = botdb.connect(_db())
    try:
        data = total_report(con, eff, lang=_req_lang(user))
    finally:
        con.close()
    data["pro"] = is_pro(user["id"])
    return data


@app.get("/api/competition/{event_id}")
async def api_competition(event_id: int, user: dict = Depends(require_auth), as_user: int | None = Query(default=None, alias="as")):
    eff = resolve_effective_user(user["id"], as_user)
    con = botdb.connect(_db())
    try:
        rep = event_report(con, event_id, eff, lang=_req_lang(user))
        if not rep:
            raise HTTPException(404, "не найдено")
        return rep
    finally:
        con.close()


@app.get("/api/goals")
async def api_goals(user: dict = Depends(require_auth), as_user: int | None = Query(default=None, alias="as")):
    eff = resolve_effective_user(user["id"], as_user)
    con = botdb.connect(_db())
    try:
        u = dict(botdb.get_user(con, eff) or {})
        sex = u.get("sex") or "m"
        bw = u.get("weight_kg")
        return goals_screen_data(con, eff, sex, bw, lang=_req_lang(user))
    finally:
        con.close()


@app.get("/api/leaderboard")
async def api_leaderboard(user: dict = Depends(require_auth),
                          metric: str = Query("overall"),
                          as_user: int | None = Query(default=None, alias="as")):
    from tj.analysis.leaderboard import leaderboard, _disc_list
    eff = resolve_effective_user(user["id"], as_user)
    con = botdb.connect(_db())
    try:
        u = botdb.get_user(con, eff)
        gym = (dict(u).get("gym") if u else None)
        if not gym:
            return {"metric": metric, "rows": [], "disciplines": _disc_list(), "no_gym": True}
        return leaderboard(con, gym, metric, eff, lang=_req_lang(user))
    finally:
        con.close()


def _nutrition_day_block(con, tg_id: int, day: str) -> dict | None:
    meals = botdb.meals_for_day(con, tg_id, day)
    if not meals:
        return None
    t = _nutr.day_totals(meals)
    t["water_l"] = botdb.water_for_day(con, tg_id, day)
    t["meals"] = len(meals)
    return t


def _llm_payload(con, kind: str, ref: str, tg_id: int):
    if kind not in ("workout", "summary", "competitions", "nutr_day", "nutr_week"):
        return None
    if kind in ("nutr_day", "nutr_week"):
        return _nutr_llm_payload(con, tg_id, ref, week=(kind == "nutr_week"))
    if kind == "competitions":
        tr = total_report(con, tg_id)
        if not tr or not tr.get("starts"):
            return None
        # radars — данные графика, narrative — наш же шаблонный текст: ИИ не нужны
        return {k: v for k, v in tr.items() if k not in ("radars", "narrative")}
    hr_max, sex = botdb.profile_hr_sex(con, tg_id)
    if kind == "workout":
        rep = workout_report(_db(), "sqlite", hr_max, sex, ref, tg_id=tg_id)
        if rep is None:
            return None
        payload = llm_coach.workout_payload(rep)
        payload["bodyweight_kg"] = botdb.latest_weight(con, tg_id, ref)
        payload["nutrition"] = _nutrition_day_block(con, tg_id, ref)
        return payload
    data = summary_data(_db(), "sqlite", hr_max, sex, date.today(), tg_id=tg_id)
    payload = llm_coach.summary_payload(data)
    payload["weight_kg"] = botdb.latest_weight(con, tg_id)
    ns = _nutr.period_summary(botdb.nutrition_days(con, tg_id, days=7),
                              botdb.water_days(con, tg_id), payload["weight_kg"])
    payload["nutrition7"] = ns if ns.get("days") else None
    return payload


def _nutr_llm_payload(con, tg_id: int, ref: str, week: bool):
    """Payload ИИ-разбора питания: день (ref) или неделя до ref включительно.
    Три батч-запроса на весь диапазон (meals/water/activities), без per-day циклов."""
    goal, weight, tgt = _user_targets(con, tg_id, ref)
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
    burned_by_day: dict[str, int] = {}
    sweat_by_day: dict[str, int] = {}
    workouts = []
    for r in con.execute(
            'SELECT "day","sport","calories","extra" FROM activities '
            'WHERE "tg_id"=? AND "day">=? AND "day"<=?', (tg_id, first, ref)):
        workouts.append({"day": r["day"], "sport": r["sport"], "calories": r["calories"]})
        burned_by_day[r["day"]] = burned_by_day.get(r["day"], 0) + int(r["calories"] or 0)
        try:
            sweat_by_day[r["day"]] = sweat_by_day.get(r["day"], 0) + int(
                (json.loads(r["extra"] or "{}")).get("sweat_loss_ml") or 0)
        except (ValueError, TypeError):
            pass
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


def _finalize_llm(con, tg_id: int, kind: str, ref: str, text: str, engine: str,
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


def _sweep_unreviewed(tg_id: int, lang: str, skip_kind: str | None = None,
                      skip_ref: str | None = None) -> None:
    """Фон после тапа «Разбор ИИ»: разобрать все НЕразобранные позиции за
    последние 7 дней (summary, тренировки, дни питания, недельный свод,
    соревнования). «Разобрано» = есть строка в кэше (даже устаревшая) → пропуск,
    заново не гоним. Квоту НЕ тратит; ошибки — молча дальше."""
    con = botdb.connect(_db())
    try:
        since = (date.today() - timedelta(days=6)).isoformat()
        targets: list[tuple[str, str]] = [("summary", "30d"), ("competitions", "total")]
        for r in con.execute('SELECT DISTINCT "day" AS d FROM activities WHERE "tg_id"=? AND "day">=? ORDER BY "day"',
                             (tg_id, since)):
            targets.append(("workout", r["d"]))
        nutr_days = [r["d"] for r in con.execute(
            'SELECT DISTINCT "day" AS d FROM meals WHERE "tg_id"=? AND "day">=? ORDER BY "day"',
            (tg_id, since))]
        for d in nutr_days:
            targets.append(("nutr_day", d))
        if nutr_days:
            targets.append(("nutr_week", nutr_days[-1]))
        astro = botdb.user_astro(con, tg_id)
        for k, ref in targets:
            if k == skip_kind and ref == skip_ref:
                continue
            try:
                if botdb.llm_cache_get_latest(con, tg_id, k, ref, lang):
                    continue
                payload = _llm_payload(con, k, ref, tg_id)
                if payload is None:
                    continue
                h = llm_coach.payload_hash(payload, lang, astro)
                text, engine = llm_coach.coach(k, payload, lang, astro)
                if not text:
                    continue
                text = _finalize_llm(con, tg_id, k, ref, text, engine, lang)
                botdb.llm_cache_put(con, tg_id, k, ref, h, text, engine, lang=lang)
            except Exception as e:
                print(f"[llm] sweep {k}/{ref} для {tg_id}: {type(e).__name__}", flush=True)
    finally:
        con.close()


@app.get("/api/llm/{kind}/{ref}")
async def api_llm_get(kind: str, ref: str, user: dict = Depends(require_auth), as_user: int | None = Query(default=None, alias="as")):
    eff = resolve_effective_user(user["id"], as_user)
    available = has_llm() and is_pro(user["id"])
    con = botdb.connect(_db())
    try:
        lang = _req_lang(user)
        cached = None
        stale = False
        if available:
            stored = botdb.llm_cache_get_latest(con, eff, kind, ref, lang)
            if stored:
                cached = {"text": stored["text"], "engine": stored["engine"]}
                payload = _llm_payload(con, kind, ref, eff)
                if payload is not None:
                    h = llm_coach.payload_hash(payload, lang, botdb.user_astro(con, eff))
                    stale = (h != stored["data_hash"])
        remaining = llm_quota_remaining(user["id"], con)
    finally:
        con.close()
    return {"available": available, "cached": cached, "stale": stale, "remaining": remaining}


@app.get("/api/claude/{day}")
async def api_claude_get(day: str, user: dict = Depends(require_auth), as_user: int | None = Query(default=None, alias="as")):
    eff = resolve_effective_user(user["id"], as_user)
    available = is_pro(user["id"])
    text = None
    if available:
        lang = _req_lang(user)
        con = botdb.connect(_db())
        try:
            text = botdb.claude_review_get(con, eff, day, lang)
        finally:
            con.close()
    return {"available": available, "text": text}


@app.post("/api/llm/{kind}/{ref}")
def api_llm_post(kind: str, ref: str, background: BackgroundTasks,   # sync: Claude думает до минуты, не держим event loop
                       refresh: int = Query(0), user: dict = Depends(require_auth)):
    if not is_pro(user["id"]):
        raise HTTPException(status_code=403, detail="нужен Pro")
    con = botdb.connect(_db())
    try:
        lang = _req_lang(user)
        payload = _llm_payload(con, kind, ref, user["id"])
        if payload is None:
            raise HTTPException(status_code=404, detail="нет данных")
        botdb.log_action(con, user["id"], _stats.LLM_REVIEW)
        if not refresh:
            stored = botdb.llm_cache_get_latest(con, user["id"], kind, ref, lang)
            if stored:
                background.add_task(_sweep_unreviewed, user["id"], lang, kind, ref)
                return {"text": stored["text"], "engine": stored["engine"], "cached": True}
        if not llm_quota_consume(user["id"], con):
            raise HTTPException(status_code=429, detail=f"Лимит ИИ на сегодня исчерпан ({LLM_DAILY_LIMIT}/день)")
        # refresh: чистим старый кэш, иначе поллинг фронта натыкается на прошлый
        # разбор (генерация идёт секунды) и показывает его вместо свежего.
        botdb.llm_cache_delete(con, user["id"], kind, ref)
        # Клод пишет до 2-3 минут, а туннель режет запрос по таймауту ~100с —
        # поэтому генерим В ФОНЕ, а фронт поллит GET, пока кэш не наполнится.
        background.add_task(_generate_llm, user["id"], kind, ref, lang)
        return {"pending": True}
    finally:
        con.close()


def _generate_llm(tg_id: int, kind: str, ref: str, lang: str) -> None:
    """Фоновая генерация нажатого разбора (Claude первым, Gemini запасным),
    затем цепочкой — разборы остальных сущностей."""
    con = botdb.connect(_db())
    try:
        payload = _llm_payload(con, kind, ref, tg_id)
        if payload is None:
            return
        astro = botdb.user_astro(con, tg_id)
        h = llm_coach.payload_hash(payload, lang, astro)
        text, engine = llm_coach.coach(kind, payload, lang, astro)
        if not text:
            return
        text = _finalize_llm(con, tg_id, kind, ref, text, engine, lang)
        botdb.llm_cache_put(con, tg_id, kind, ref, h, text, engine, lang=lang)
    except Exception as e:
        print(f"[llm] generate {kind}/{ref} для {tg_id}: {type(e).__name__}", flush=True)
    finally:
        con.close()
    _sweep_unreviewed(tg_id, lang, kind, ref)   # одна кнопка разбирает всё неразобранное


app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
