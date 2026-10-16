"""Каталог программ, записи на программы, сессии «у помоста». Логика — tj.services.programs.

Права: только свои записи и сессии (чужие — 404), админ смотрит чужие через `?as=<id>`.
Дата «сегодня» — по часовому поясу из config.toml [user].timezone; клиент может передать `?today=YYYY-MM-DD`
(своя дата, офлайн; тесты).
Ошибки: ProgramError.code -> HTTP: not_found 404, conflict / unavailable / closed 409, needs_input 422
(+ code и items с вопросами), invalid 422, template 500. ServiceError (workouts) — по своему status.
"""
from __future__ import annotations

import functools
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from tj import ontology
from tj.services import program_engine as eng
from tj.services import programs as svc
from tj.services.errors import ServiceError
from tjapp.deps import require_user, resolve_effective_user
from tjbot import db as botdb

router = APIRouter()

_STATUS = {"not_found": 404, "conflict": 409, "unavailable": 409, "closed": 409, "needs_input": 422,
           "invalid": 422, "template": 500}


def _con():
    con = botdb.connect(botdb.default_db_path())
    try:
        yield con
    finally:
        con.close()


def _tz() -> str:
    try:
        from tj import config as cfgmod
        return cfgmod.timezone(cfgmod.load_config())
    except Exception:
        return "UTC"


def _today(today: str | None) -> date:
    if today:
        try:
            return date.fromisoformat(today)
        except ValueError:
            raise HTTPException(status_code=422, detail="today: ожидается YYYY-MM-DD")
    try:
        return datetime.now(ZoneInfo(_tz())).date()
    except Exception:
        return date.today()


def _errors(fn):
    """Сервисные исключения -> JSON {detail, code[, items]} с нужным HTTP-кодом."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except eng.NeedsInput as e:
            return JSONResponse(status_code=422, content={"detail": "нужны опорные веса", "code": "needs_input",
                                                          "items": e.items})
        except eng.ProgramError as e:
            return JSONResponse(status_code=_STATUS.get(e.code, 422), content={"detail": str(e), "code": e.code})
        except ServiceError as e:
            return JSONResponse(status_code=e.status, content={"detail": e.detail, "code": e.code})
    return wrapper


class EnrollIn(BaseModel):
    start_day: str
    base_maxes: dict[str, Any] | None = None
    level: str | None = None
    weekdays: list[int] | None = None
    id: str | None = Field(default=None, description="клиентский UUID записи (идемпотентность)")


class SetIn(BaseModel):
    done_kg: float | None = None
    reps: int | None = None
    ok: bool | None = None
    note: str | None = Field(default=None, max_length=500)
    exercise: str | None = Field(default=None, max_length=64, description="для внепланового подхода")
    ts: str | None = None


class CheckinIn(BaseModel):
    energy: int | None = None
    tired: bool | None = None
    sleepy: bool | None = None
    joint: bool | None = None
    ill: bool | None = None


class FinishIn(BaseModel):
    rpe: int | None = None
    feel: int | None = None
    activity_id: str | None = Field(default=None, description="клиентский UUID тренировки")


class RefreshIn(BaseModel):
    lifts: list[str] | None = None


# ---------------------------------------------------------------- каталог

@router.get("/api/programs/tree")
@_errors
def programs_tree(user: dict = Depends(require_user), con=Depends(_con)):
    return {"tree": svc.tree(con)}


@router.get("/api/programs/{slug}")
@_errors
def program_card(slug: str, today: str | None = Query(default=None), uid: int = Depends(resolve_effective_user),
                 con=Depends(_con)):
    return svc.get_program(con, slug, uid, _today(today))


@router.post("/api/programs/{slug}/enroll")
@_errors
def program_enroll(slug: str, body: EnrollIn, today: str | None = Query(default=None),
                   uid: int = Depends(resolve_effective_user), con=Depends(_con)):
    t = _today(today)
    try:
        start = date.fromisoformat(body.start_day)
    except ValueError:
        raise HTTPException(status_code=422, detail="start_day: ожидается YYYY-MM-DD")
    return svc.enroll(con, uid, slug, start_day=start, today=t, base_maxes=body.base_maxes, level=body.level,
                      weekdays=body.weekdays, enrollment_id=body.id)


# ---------------------------------------------------------------- записи

@router.get("/api/enrollments")
@_errors
def enrollments(status: str | None = Query(default=None), uid: int = Depends(resolve_effective_user),
                con=Depends(_con)):
    return {"enrollments": svc.list_enrollments(con, uid, status)}


@router.get("/api/enrollments/{enrollment_id}")
@_errors
def enrollment_get(enrollment_id: str, uid: int = Depends(resolve_effective_user), con=Depends(_con)):
    return svc.get_enrollment(con, uid, enrollment_id)


@router.get("/api/enrollments/{enrollment_id}/sessions")
@_errors
def enrollment_sessions(enrollment_id: str, uid: int = Depends(resolve_effective_user), con=Depends(_con)):
    return {"sessions": svc.list_sessions(con, uid, enrollment_id)}


@router.get("/api/enrollments/{enrollment_id}/today")
@_errors
def enrollment_today(enrollment_id: str, today: str | None = Query(default=None),
                     uid: int = Depends(resolve_effective_user), con=Depends(_con)):
    return svc.today_session(con, uid, enrollment_id, _today(today))


@router.post("/api/enrollments/{enrollment_id}/refresh-base")
@_errors
def enrollment_refresh(enrollment_id: str, body: RefreshIn | None = None,
                       uid: int = Depends(resolve_effective_user), con=Depends(_con)):
    return svc.refresh_base(con, uid, enrollment_id, body.lifts if body else None)


def _status_action(action: str, enrollment_id: str, uid: int, con):
    return svc.set_enrollment_status(con, uid, enrollment_id, action)


for _action in ("pause", "resume", "cancel"):
    def _make(action):
        @_errors
        def handler(enrollment_id: str, uid: int = Depends(resolve_effective_user), con=Depends(_con)):
            return _status_action(action, enrollment_id, uid, con)
        handler.__name__ = f"enrollment_{action}"
        return handler
    _h = _make(_action)
    router.post(f"/api/programs/enrollments/{{enrollment_id}}/{_action}")(_h)
    router.post(f"/api/enrollments/{{enrollment_id}}/{_action}", include_in_schema=False)(_h)


# ---------------------------------------------------------------- сессии

@router.get("/api/sessions/{session_id}")
@_errors
def session_get(session_id: str, uid: int = Depends(resolve_effective_user), con=Depends(_con)):
    return svc.get_session(con, uid, session_id)


@router.put("/api/sessions/{session_id}/sets/{set_id}")
@_errors
def session_set(session_id: str, set_id: str, body: SetIn, uid: int = Depends(resolve_effective_user),
                con=Depends(_con)):
    # model_fields_set: «не передано» (поле остаётся) отличаем от явного null (ok: null = сброс отметки)
    return svc.log_set(con, uid, session_id, set_id, done_kg=body.done_kg, reps=body.reps, ok=body.ok,
                       note=body.note, exercise=body.exercise, ts=body.ts, fields=set(body.model_fields_set))


@router.post("/api/sessions/{session_id}/checkin")
@_errors
def session_checkin(session_id: str, body: CheckinIn, uid: int = Depends(resolve_effective_user), con=Depends(_con)):
    return svc.submit_checkin(con, uid, session_id, body.model_dump(exclude_none=True))


@router.post("/api/sessions/{session_id}/finish")
@_errors
def session_finish(session_id: str, body: FinishIn | None = None, today: str | None = Query(default=None),
                   uid: int = Depends(resolve_effective_user), con=Depends(_con)):
    b = body or FinishIn()
    return svc.finish_session(con, uid, session_id, rpe=b.rpe, feel=b.feel, activity_id=b.activity_id,
                              today=_today(today), tz=_tz())


# ---------------------------------------------------------------- тренд

@router.get("/api/lifts/{lift}/trend")
@_errors
def lift_trend(lift: str, window: int = Query(default=7, ge=1, le=60), uid: int = Depends(resolve_effective_user),
               con=Depends(_con)):
    if lift not in ontology.MOVEMENTS or not ontology.is_weighted(lift):
        raise HTTPException(status_code=404, detail="лифт не найден")
    return svc.day_max_trend(con, uid, lift, window)
