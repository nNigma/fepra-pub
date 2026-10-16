"""ИИ-тренер (только Pro): вопрос задачей + последние обращения."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from tj.services import clock
from tj.services import coach as svc
from tj.services import jobs as jobs_svc
from tjapp.deps import require_pro
from tjbot import db as botdb

from ._common import get_con

router = APIRouter()


class AskIn(BaseModel):
    q: str = Field(min_length=1, max_length=svc.MAX_QUESTION)


@router.post("/api/coach/ask")
def coach_ask(body: AskIn, user: dict = Depends(require_pro), con=Depends(get_con)):
    uid = user["id"]
    q = body.q.strip()
    if not q:
        raise HTTPException(status_code=422, detail="вопрос пустой")
    busy = con.execute('SELECT "id" FROM jobs WHERE "uid"=? AND "kind"=\'coach_ask\' '
                       'AND "status" IN (\'pending\',\'running\') LIMIT 1', (uid,)).fetchone()
    if busy:                      # предыдущий вопрос ещё думает: квоту второй раз не жжём
        return {"job_id": busy["id"]}
    try:
        svc.check_and_consume(con, uid, clock.today().isoformat())
    except svc.CoachError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    lang = botdb.user_lang(con, uid)
    db_path = botdb.default_db_path()
    jid = jobs_svc.create_job(con, "coach_ask", uid, {"q": q})
    jobs_svc.run_in_background(jid, lambda: svc.ask_and_store(db_path, uid, q, lang))
    return {"job_id": jid}


@router.get("/api/coach/recent")
def coach_recent(limit: int = Query(default=5, ge=1, le=svc.RECENT_LIMIT),
                 user: dict = Depends(require_pro), con=Depends(get_con)):
    return svc.recent(con, user["id"], limit)
