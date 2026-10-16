"""Подключение Garmin: вход с MFA, статус, синк и история (jobs), отключение.

login/mfa блокируют до ответа Garmin (до 60 с), поэтому обычные `def`:
FastAPI гонит их в threadpool. Пароль нигде не логируется и не возвращается.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tj.services import garmin as svc
from tj.services import jobs as jobs_svc
from tjapp.deps import require_user
from tjapp.ratelimit import RateLimiter
from tjbot import db as botdb

router = APIRouter()

# Перебор паролей/кодов и долбёжка Garmin с одного IP — лимит на пользователя.
login_limiter = RateLimiter(limit=5, window_s=600)
mfa_limiter = RateLimiter(limit=10, window_s=600)

_JOB_KINDS = ("garmin_sync", "garmin_history")


def _con():
    con = botdb.connect(botdb.default_db_path())
    try:
        yield con
    finally:
        con.close()


def _limit(limiter: RateLimiter, uid: int) -> None:
    if not limiter.allow(str(uid)):
        raise HTTPException(status_code=429, detail="слишком много попыток, попробуйте позже")


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(repr=False)


class MfaIn(BaseModel):
    code: str = Field(max_length=32)


class HistoryIn(BaseModel):
    days: int = Field(default=60, ge=1, le=365)


def _result(r: dict) -> dict:
    return {"status": r["state"], "message": r["message"]}


@router.get("/api/garmin/status")
def garmin_status(user: dict = Depends(require_user), con=Depends(_con)):
    return svc.status(con, user["id"])


@router.post("/api/garmin/login")
def garmin_login(body: LoginIn, user: dict = Depends(require_user), con=Depends(_con)):
    _limit(login_limiter, user["id"])
    return _result(svc.start_login(con, user["id"], body.email, body.password))


@router.post("/api/garmin/mfa")
def garmin_mfa(body: MfaIn, user: dict = Depends(require_user), con=Depends(_con)):
    _limit(mfa_limiter, user["id"])
    return _result(svc.submit_mfa(con, user["id"], body.code))


def _start_job(con, uid: int, kind: str, fn, payload=None) -> dict:
    if botdb.garmin_account_get(con, uid) is None:
        raise HTTPException(status_code=409, detail="Garmin не подключён")
    busy = con.execute('SELECT "id" FROM jobs WHERE "uid"=? AND "kind" IN (?,?) '
                       'AND "status" IN (\'pending\',\'running\') ORDER BY "created_at" DESC LIMIT 1',
                       (uid, *_JOB_KINDS)).fetchone()
    if busy:            # синк уже идёт — не запускаем второй, отдаём тот же job
        return {"job_id": busy["id"]}
    jid = jobs_svc.create_job(con, kind, uid, payload)
    jobs_svc.run_in_background(jid, fn)
    return {"job_id": jid}


@router.post("/api/garmin/sync")
def garmin_sync(user: dict = Depends(require_user), con=Depends(_con)):
    uid = user["id"]
    return _start_job(con, uid, "garmin_sync", lambda: svc.sync_recent(uid))


@router.post("/api/garmin/history")
def garmin_history(body: HistoryIn, user: dict = Depends(require_user), con=Depends(_con)):
    uid, days = user["id"], body.days
    return _start_job(con, uid, "garmin_history", lambda: svc.sync_history(uid, days), {"days": days})


@router.post("/api/garmin/disconnect")
def garmin_disconnect(user: dict = Depends(require_user), con=Depends(_con)):
    svc.disconnect(con, user["id"])
    return {"ok": True}
