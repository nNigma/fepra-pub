"""FastAPI Mini App: статика + JSON-API сводки поверх training.db.

Данные сводки — общий summary_data() из tj.analysis.dashboard (тот же, что у
HTML-дашборда Obsidian). Доступ к API — по валидному initData (allowlist).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
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
    return FileResponse(_STATIC / "index.html")


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
        return total_report(con, eff, lang=_req_lang(user))
    finally:
        con.close()


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


def _llm_payload(con, kind: str, ref: str, tg_id: int):
    if kind not in ("workout", "summary"):
        return None
    hr_max, sex = botdb.profile_hr_sex(con, tg_id)
    if kind == "workout":
        rep = workout_report(_db(), "sqlite", hr_max, sex, ref, tg_id=tg_id)
        if rep is None:
            return None
        return llm_coach.workout_payload(rep)
    data = summary_data(_db(), "sqlite", hr_max, sex, date.today(), tg_id=tg_id)
    return llm_coach.summary_payload(data)


@app.get("/api/llm/{kind}/{ref}")
async def api_llm_get(kind: str, ref: str, user: dict = Depends(require_auth), as_user: int | None = Query(default=None, alias="as")):
    eff = resolve_effective_user(user["id"], as_user)
    available = has_llm() and is_pro(user["id"])
    con = botdb.connect(_db())
    try:
        lang = _req_lang(user)
        cached = None
        if available:
            payload = _llm_payload(con, kind, ref, eff)
            if payload is not None:
                h = llm_coach.payload_hash(payload, lang, botdb.user_astro(con, eff))
                cached = botdb.llm_cache_get(con, eff, kind, ref, h, lang)
        remaining = llm_quota_remaining(user["id"], con)
    finally:
        con.close()
    return {"available": available, "cached": cached, "remaining": remaining}


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
async def api_llm_post(kind: str, ref: str, refresh: int = Query(0), user: dict = Depends(require_auth)):
    if not is_pro(user["id"]):
        raise HTTPException(status_code=403, detail="нужен Pro")
    con = botdb.connect(_db())
    try:
        lang = _req_lang(user)
        payload = _llm_payload(con, kind, ref, user["id"])
        if payload is None:
            raise HTTPException(status_code=404, detail="нет данных")
        botdb.log_action(con, user["id"], _stats.LLM_REVIEW)
        astro = botdb.user_astro(con, user["id"])
        h = llm_coach.payload_hash(payload, lang, astro)
        if not refresh:
            cached = botdb.llm_cache_get(con, user["id"], kind, ref, h, lang)
            if cached:
                return {"text": cached, "cached": True}
        if not llm_quota_consume(user["id"], con):
            raise HTTPException(status_code=429, detail=f"Лимит ИИ на сегодня исчерпан ({LLM_DAILY_LIMIT}/день)")
        text = (llm_coach.coach_workout(payload, lang, astro) if kind == "workout"
                else llm_coach.coach_summary(payload, lang, astro))
        if not text:
            raise HTTPException(status_code=503, detail="ИИ недоступен")
        if kind == "summary":
            line = llm_coach.parse_advice_line(text, lang)
            if line:
                botdb.next_advice_put(con, user["id"], "gemini", line, lang=lang)
        elif kind == "workout":
            blocks = llm_coach.parse_workout_blocks(text, lang)
            if blocks:
                botdb.wk_narrative_put(con, user["id"], ref, "gemini", blocks, lang=lang)
                text = llm_coach.strip_workout_blocks(text, lang)
        botdb.llm_cache_put(con, user["id"], kind, ref, h, text, "gemini", lang=lang)
        return {"text": text, "cached": False}
    finally:
        con.close()


app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
