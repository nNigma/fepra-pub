"""Запись тренировки: PUT/GET/PATCH/DELETE /api/workouts, максы, вес тела, самочувствие,
программа зала на день. Логика — tj.services.workouts / board; тут валидация и права."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from tj.services import board as board_svc
from tj.services import workouts as svc
from tjapp.deps import require_user

from ._common import call, db_con, lang_of, user_tz

router = APIRouter()


class ResolveIn(BaseModel):
    movement: str
    variant: str
    weight: float
    reps: int = 1


class MaxesIn(BaseModel):
    maxes: list[dict[str, Any]] | None = None
    text: str | None = None


class BodyweightIn(BaseModel):
    kg: float | str
    day: str | None = None


class FeelIn(BaseModel):
    score: int


@router.get("/api/workouts/recent")
def recent(limit: int = Query(default=10, ge=1, le=100), user: dict = Depends(require_user),
           con=Depends(db_con)):
    return svc.recent(con, user["id"], limit)


@router.put("/api/workouts/{activity_id}")
def put_workout(activity_id: str, payload: dict = Body(...), user: dict = Depends(require_user),
                con=Depends(db_con)):
    """Идемпотентно по UUID: доска + результат формы + scaling + RPE + вес тела."""
    return call(svc.save_result, con, user["id"], activity_id, payload, tz=user_tz(),
                lang=lang_of(con, user["id"]))


@router.get("/api/workouts/{activity_id}")
def get_workout(activity_id: str, user: dict = Depends(require_user), con=Depends(db_con)):
    return call(svc.get, con, user["id"], activity_id, lang=lang_of(con, user["id"]))


@router.patch("/api/workouts/{activity_id}")
def patch_workout(activity_id: str, changes: dict = Body(...), user: dict = Depends(require_user),
                  con=Depends(db_con)):
    return call(svc.update, con, user["id"], activity_id, changes, lang=lang_of(con, user["id"]))


@router.delete("/api/workouts/{activity_id}")
def delete_workout(activity_id: str, user: dict = Depends(require_user), con=Depends(db_con)):
    return call(svc.delete, con, user["id"], activity_id)


@router.post("/api/workouts/{activity_id}/restore")
def restore_workout(activity_id: str, user: dict = Depends(require_user), con=Depends(db_con)):
    return call(svc.restore, con, user["id"], activity_id)


@router.post("/api/workouts/{activity_id}/lifts/resolve")
def resolve_lift(activity_id: str, body: ResolveIn, user: dict = Depends(require_user),
                 con=Depends(db_con)):
    return call(svc.resolve_lift, con, user["id"], activity_id, body.movement, body.variant,
                body.weight, body.reps, lang=lang_of(con, user["id"]))


@router.post("/api/workouts/{activity_id}/maxes")
def confirm_maxes(activity_id: str, body: MaxesIn, user: dict = Depends(require_user),
                  con=Depends(db_con)):
    return call(svc.confirm_maxes, con, user["id"], activity_id, body.maxes, text=body.text,
                lang=lang_of(con, user["id"]))


@router.post("/api/bodyweight")
def post_bodyweight(body: BodyweightIn, user: dict = Depends(require_user), con=Depends(db_con)):
    return call(svc.set_bodyweight, con, user["id"], body.kg, body.day, tz=user_tz())


@router.post("/api/feel")
def post_feel(body: FeelIn, user: dict = Depends(require_user), con=Depends(db_con)):
    return call(svc.set_feel, con, user["id"], body.score, tz=user_tz())


@router.get("/api/gym-program")
def gym_program(day: str | None = Query(default=None), gym: str | None = Query(default=None),
                user: dict = Depends(require_user), con=Depends(db_con)):
    """Программа зала на день (для подстановки доски). Зал по умолчанию — из профиля; другой зал
    (?gym=) — админу любой, тренеру из его залов. Нет программы -> {found:false}."""
    if day is None:
        d = svc.today_in(user_tz())
    else:
        try:
            d = date.fromisoformat(day)
        except ValueError:
            raise HTTPException(status_code=422, detail="day: ожидается ГГГГ-ММ-ДД")
    prog = call(board_svc.gym_program, con, user["id"], d.isoformat(), gym)
    if not prog:
        return {"found": False, "day": d.isoformat()}
    return {"found": True, **prog}
