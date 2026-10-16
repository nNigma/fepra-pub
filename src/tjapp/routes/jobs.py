"""GET /api/jobs/{id}: статус и результат фоновой задачи (только владелец)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from tj.services import jobs as jobs_svc
from tjapp.deps import require_user
from tjbot import db as botdb

router = APIRouter()


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, user: dict = Depends(require_user)):
    con = botdb.connect(botdb.default_db_path())
    try:
        job = jobs_svc.get_job(con, job_id, user["id"])
    finally:
        con.close()
    if job is None:
        raise HTTPException(status_code=404, detail="задача не найдена")
    return {"id": job["id"], "status": job["status"], "result": job["result"], "error": job["error"]}
