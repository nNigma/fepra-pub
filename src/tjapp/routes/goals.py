"""Цели (CRUD) и ввод ПМ. GET /api/goals занят экраном Mini App, поэтому CRUD — /api/goals/items."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tj.services import goals as svc
from tjapp.deps import require_user

from ._common import call, db_con, lang_of, user_tz

router = APIRouter()


class GoalIn(BaseModel):
    kind: Literal["numeric", "level"]
    discipline: str
    target: Any


class PmIn(BaseModel):
    discipline: str
    value: Any
    reps: int | None = None


@router.get("/api/goals/items")
def list_items(user: dict = Depends(require_user), con=Depends(db_con)):
    return svc.list_goals(con, user["id"])


@router.post("/api/goals/items")
def add_item(body: GoalIn, user: dict = Depends(require_user), con=Depends(db_con)):
    return call(svc.add, con, user["id"], body.kind, body.discipline, body.target,
                lang=lang_of(con, user["id"]))


@router.post("/api/goals/items/{goal_id}/archive")
def archive_item(goal_id: int, user: dict = Depends(require_user), con=Depends(db_con)):
    return call(svc.archive, con, user["id"], goal_id)


@router.delete("/api/goals/items/{goal_id}")
def delete_item(goal_id: int, user: dict = Depends(require_user), con=Depends(db_con)):
    return call(svc.archive, con, user["id"], goal_id)


@router.post("/api/goals/items/{goal_id}/complete")
def complete_item(goal_id: int, user: dict = Depends(require_user), con=Depends(db_con)):
    return call(svc.complete, con, user["id"], goal_id)


@router.post("/api/pm")
def enter_pm(body: PmIn, user: dict = Depends(require_user), con=Depends(db_con)):
    return call(svc.enter_pm, con, user["id"], body.discipline, body.value, body.reps,
                lang=lang_of(con, user["id"]), tz=user_tz())
