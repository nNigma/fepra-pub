"""Питание: запись приёма по фото/тексту, правка, удаление, вода. Только Pro/admin.

Разбор — job (POST возвращает {job_id}, результат в GET /api/jobs/{id}); сохранение,
правка и удаление — обычные запросы. Отчётные GET /api/nutrition* живут в api.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from tj.services import jobs as jobs_svc
from tj.services import meals as svc
from tj.services.errors import ServiceError
from tjapp.deps import require_pro
from tjbot import db as botdb

router = APIRouter()


def _con():
    con = botdb.connect(botdb.default_db_path())
    try:
        yield con
    finally:
        con.close()


def _tz() -> str:
    from tj import config as cfgmod
    try:
        return cfgmod.timezone(cfgmod.load_config())
    except Exception:
        return "UTC"


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ServiceError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


def _job(con, uid: int, kind: str, fn, payload=None) -> dict:
    """Запустить fn(con) в фоне на своём соединении; -> {job_id}."""
    jid = jobs_svc.create_job(con, kind, uid, payload)

    def run():
        c = botdb.connect(botdb.default_db_path())
        try:
            return fn(c)
        finally:
            c.close()
    jobs_svc.run_in_background(jid, run)
    return {"job_id": jid}


class ParseIn(BaseModel):
    upload_id: str | None = None
    text: str | None = Field(default=None, max_length=2000)
    correction: str | None = Field(default=None, max_length=400)
    notes: list[str] | None = Field(default=None, max_length=20)


class CorrectionIn(BaseModel):
    correction: str = Field(max_length=400)
    notes: list[str] | None = Field(default=None, max_length=20)


class SaveIn(BaseModel):
    draft: dict
    day: str | None = None
    ts: str | None = None
    uuid: str | None = None
    upload_id: str | None = None
    text: str | None = Field(default=None, max_length=2000)


class ReplaceIn(BaseModel):
    draft: dict
    day: str | None = None
    ts: str | None = None


class WaterIn(BaseModel):
    delta_ml: int
    day: str | None = None


@router.post("/api/meals/parse")
def meals_parse(body: ParseIn, user: dict = Depends(require_pro), con=Depends(_con)):
    uid = user["id"]
    if not body.upload_id and not (body.text and body.text.strip()):
        raise HTTPException(status_code=400, detail="нужно upload_id или text")
    if body.upload_id:                      # чужой/несуществующий файл — 404 сразу
        from tj.services import uploads
        _call(uploads.get, con, uid, body.upload_id)
    kw = body.model_dump()
    return _job(con, uid, "meal_parse", lambda c: svc.parse(c, uid, **kw),
                {"kind": "photo" if body.upload_id else "text"})


@router.post("/api/meals")
def meals_save(body: SaveIn, user: dict = Depends(require_pro), con=Depends(_con)):
    return _call(svc.save, con, user["id"], tz=_tz(), **body.model_dump())


@router.get("/api/meals")
def meals_day(day: str | None = Query(default=None), user: dict = Depends(require_pro),
              con=Depends(_con)):
    return _call(svc.day_meals, con, user["id"], day, _tz())


@router.put("/api/meals/{meal_id}")
def meals_replace(meal_id: int, body: ReplaceIn, user: dict = Depends(require_pro),
                  con=Depends(_con)):
    return _call(svc.replace, con, user["id"], meal_id, tz=_tz(), **body.model_dump())


@router.post("/api/meals/{meal_id}/reparse")
def meals_reparse(meal_id: int, body: CorrectionIn, user: dict = Depends(require_pro),
                  con=Depends(_con)):
    uid = user["id"]
    _call(svc.get, con, uid, meal_id)      # чужой/нет — 404 сразу
    return _job(con, uid, "meal_reparse",
                lambda c: svc.parse_saved(c, uid, meal_id, correction=body.correction,
                                          notes=body.notes), {"meal_id": meal_id})


@router.delete("/api/meals/{meal_id}")
def meals_delete(meal_id: int, user: dict = Depends(require_pro), con=Depends(_con)):
    _call(svc.delete, con, user["id"], meal_id)
    return {"ok": True}


@router.post("/api/water")
def water_add(body: WaterIn, user: dict = Depends(require_pro), con=Depends(_con)):
    return _call(svc.add_water, con, user["id"], body.delta_ml, body.day, _tz())


@router.get("/api/water")
def water_get(day: str | None = Query(default=None), user: dict = Depends(require_pro),
              con=Depends(_con)):
    return _call(svc.water, con, user["id"], day, _tz())
