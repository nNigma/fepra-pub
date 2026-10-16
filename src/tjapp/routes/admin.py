"""Админка PWA: пользователи и роли, залы, тренеры, статистика, «Разбор полётов».
Инвайты — в routes/auth.py. Всё под require_admin."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from tj import llm
from tj.services import admin as svc
from tj.services import jobs as jobs_svc
from tjapp.deps import require_admin
from tjbot import db as botdb

from ._common import get_con

router = APIRouter()


def _raise(e: svc.AdminError):
    raise HTTPException(status_code=e.status, detail=e.detail)


@router.get("/api/admin/users")
def users(q: str | None = Query(default=None, max_length=100),
          admin: dict = Depends(require_admin), con=Depends(get_con)):
    return svc.list_users(con, q)


@router.put("/api/admin/users/{uid}/roles")
def put_roles(uid: int, body: dict, admin: dict = Depends(require_admin), con=Depends(get_con)):
    """Тело: любое подмножество {allowlist, pro, admin: bool, coach: "<зал>"|["<зал>", …]|null}."""
    try:
        return {"id": uid, "roles": svc.set_roles(con, uid, body)}
    except svc.AdminError as e:
        _raise(e)


@router.delete("/api/admin/users/{uid}")
def delete_user_access(uid: int, admin: dict = Depends(require_admin), con=Depends(get_con)):
    try:
        svc.remove_access(con, uid)
    except svc.AdminError as e:
        _raise(e)
    return {"ok": True}


class GymIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.get("/api/admin/gyms")
def gyms(admin: dict = Depends(require_admin), con=Depends(get_con)):
    return svc.list_gyms(con)


@router.post("/api/admin/gyms", status_code=201)
def add_gym(body: GymIn, admin: dict = Depends(require_admin), con=Depends(get_con)):
    try:
        return svc.add_gym(con, body.name)
    except svc.AdminError as e:
        _raise(e)


class CoachIn(BaseModel):
    user_id: int
    gym: str = Field(min_length=1, max_length=200)


@router.get("/api/admin/coaches")
def coaches(admin: dict = Depends(require_admin), con=Depends(get_con)):
    return svc.list_coaches(con)


@router.post("/api/admin/coaches")
def assign_coach(body: CoachIn, admin: dict = Depends(require_admin), con=Depends(get_con)):
    try:
        return svc.assign_coach(con, body.user_id, body.gym)
    except svc.AdminError as e:
        _raise(e)


@router.delete("/api/admin/coaches/{uid}")
def revoke_coach(uid: int, gym: str | None = Query(default=None), admin: dict = Depends(require_admin),
                 con=Depends(get_con)):
    try:
        svc.revoke_coach(con, uid, gym)
    except svc.AdminError as e:
        _raise(e)
    return {"ok": True}


@router.get("/api/admin/stats")
def stats(days: int | None = Query(default=None, ge=0, le=svc.STATS_MAX_DAYS),
          admin: dict = Depends(require_admin), con=Depends(get_con)):
    """days=7|30|… ; без параметра или 0 — за всё время."""
    try:
        return svc.stats(con, days)
    except svc.AdminError as e:
        _raise(e)


@router.post("/api/admin/review")
def start_review(admin: dict = Depends(require_admin), con=Depends(get_con)):
    """«Разбор полётов»: прогон авторазборов по всем Pro задачей. Уже идёт — вернём его job_id."""
    running = svc.review_running_job(con)
    if running:
        return {"job_id": running, "already_running": True}
    if not llm.has_text_llm():
        raise HTTPException(status_code=503, detail="LLM недоступен (нет agent/claude/gemini)")
    db_path = botdb.default_db_path()
    jid = jobs_svc.create_job(con, svc.REVIEW_KIND, admin["id"])
    jobs_svc.run_in_background(jid, lambda: svc.run_review(db_path))
    return {"job_id": jid, "already_running": False}
