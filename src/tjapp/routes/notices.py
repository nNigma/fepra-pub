"""Уведомления пользователю (баннеры PWA)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from tj.services import notices as svc
from tjapp.deps import require_user
from tjbot import db as botdb

router = APIRouter()


def _con():
    con = botdb.connect(botdb.default_db_path())
    try:
        yield con
    finally:
        con.close()


@router.get("/api/notices")
def list_notices(unread: bool = Query(default=False), limit: int = Query(default=50, ge=1, le=200),
                 user: dict = Depends(require_user), con=Depends(_con)):
    return svc.list_notices(con, user["id"], unread_only=unread, limit=limit)


@router.post("/api/notices/{notice_id}/read")
def read_notice(notice_id: str, user: dict = Depends(require_user), con=Depends(_con)):
    if not svc.mark_read(con, user["id"], notice_id):
        raise HTTPException(status_code=404, detail="уведомление не найдено")
    return {"ok": True}
