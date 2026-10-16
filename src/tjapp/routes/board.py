"""POST /api/board/parse: фото/текст доски -> job; результат job = блоки + форма результата."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tj.models import BOARD_SPORTS, Sport
from tj.services import board as svc
from tj.services import jobs as jobs_svc
from tj.services import uploads
from tjapp.deps import require_user
from tjbot import db as botdb

from ._common import call, db_con, open_con

router = APIRouter()

SportName = Literal[tuple(s.value for s in Sport)]   # type: ignore[valid-type]


class ParseIn(BaseModel):
    upload_id: str | None = None
    text: str | None = None
    sport: SportName = "crossfit"
    engine: Literal["fast", "slow", "gemini", "claude"] = "fast"
    verbatim: bool = False          # текст уже правил человек: без ИИ и без квоты


@router.post("/api/board/parse")
def board_parse(body: ParseIn, user: dict = Depends(require_user), con=Depends(db_con)):
    uid = user["id"]
    if Sport(body.sport) not in BOARD_SPORTS:
        raise HTTPException(status_code=422, detail="у этого вида спорта нет доски")
    if bool(body.upload_id) == bool((body.text or "").strip()):
        raise HTTPException(status_code=400, detail="нужно одно из: upload_id или text")
    if body.upload_id:
        call(uploads.get, con, uid, body.upload_id)          # чужая/несуществующая — 404 сразу
    upload_id, text, engine, sport, verbatim = (
        body.upload_id, body.text, body.engine, body.sport, body.verbatim)

    def _run():
        c = open_con()
        try:
            return svc.parse(c, uid, upload_id=upload_id, text=text, engine=engine,
                             sport=sport, verbatim=verbatim)
        finally:
            c.close()

    jid = jobs_svc.create_job(con, "board_parse", uid, {"sport": sport, "engine": engine})
    jobs_svc.run_in_background(jid, _run, botdb.default_db_path())
    return {"job_id": jid}
