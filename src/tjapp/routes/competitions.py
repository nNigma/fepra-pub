"""Соревнования: старты, участие, этапы, результаты, итог, размер поля.

Отчётные GET /api/competitions и /api/competition/{id} живут в api.py. Здесь — запись.
Распознавание фото (этапы, таблица результатов) — jobs: POST .../parse -> {job_id}, результат
в GET /api/jobs/{id}, сохранение — отдельным confirm-запросом. Контекст «заполнения» бота
(user_data["fill"]) — явные event_id / division_id / athlete в запросе.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tj.services import competitions as svc
from tj.services import jobs as jobs_svc
from tj.services.errors import ServiceError
from tjapp.deps import require_user
from tjbot import db as botdb

router = APIRouter()


def _con():
    con = botdb.connect(botdb.default_db_path())
    try:
        yield con
    finally:
        con.close()


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ServiceError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


def _job(con, uid: int, kind: str, fn, payload=None) -> dict:
    jid = jobs_svc.create_job(con, kind, uid, payload)

    def run():
        c = botdb.connect(botdb.default_db_path())
        try:
            return fn(c)
        finally:
            c.close()
    jobs_svc.run_in_background(jid, run)
    return {"job_id": jid}


def _lang(user: dict) -> str:
    con = botdb.connect(botdb.default_db_path())
    try:
        return botdb.user_lang(con, user["id"])
    except Exception:
        return "ru"
    finally:
        con.close()


class EventIn(BaseModel):
    name: str = Field(max_length=200)
    date: str = Field(max_length=20)
    city: str = Field(max_length=120)
    category: str | None = Field(default=None, max_length=20)
    division: str | None = Field(default=None, max_length=80)
    force_new: bool = False


class JoinIn(BaseModel):
    division_id: int | None = None


class StageTextIn(BaseModel):
    text: str = Field(max_length=4000)
    division_id: int | None = None


class ParsePhotoIn(BaseModel):
    upload_id: str
    division_id: int | None = None
    athlete: str = svc.ME
    note: str | None = Field(default=None, max_length=600)


class StagesConfirmIn(BaseModel):
    event_id: int
    stages: list[dict] = Field(max_length=svc.MAX_STAGES)
    division_id: int | None = None


class ResultTextIn(BaseModel):
    text: str = Field(max_length=200)
    athlete: str = Field(default=svc.ME, max_length=80)
    division_id: int | None = None
    stage_idx: int | None = None


class ResultsConfirmIn(BaseModel):
    event_id: int
    rows: list[dict] = Field(max_length=svc.MAX_ROWS)
    athlete: str = Field(default=svc.ME, max_length=80)
    division_id: int | None = None


class TotalIn(BaseModel):
    total_points: float | None = None
    final_place: int | None = None
    athlete: str = Field(default=svc.ME, max_length=80)
    division_id: int | None = None


class FieldSizeIn(BaseModel):
    field_size: int


@router.get("/api/comp/list")
def comp_list(user: dict = Depends(require_user), con=Depends(_con)):
    return svc.list_events(con, user["id"])


@router.get("/api/comp/events/{event_id}")
def comp_event(event_id: int, user: dict = Depends(require_user), con=Depends(_con)):
    return _call(svc.get_event, con, user["id"], event_id)


@router.post("/api/comp/events")
def comp_create(body: EventIn, user: dict = Depends(require_user), con=Depends(_con)):
    return _call(svc.create_event, con, user["id"], lang=_lang(user), **body.model_dump())


@router.post("/api/comp/events/{event_id}/join")
def comp_join(event_id: int, body: JoinIn | None = None, user: dict = Depends(require_user),
              con=Depends(_con)):
    return _call(svc.join, con, user["id"], event_id, body.division_id if body else None)


@router.post("/api/comp/events/{event_id}/stages")
def comp_stage_text(event_id: int, body: StageTextIn, user: dict = Depends(require_user),
                    con=Depends(_con)):
    return _call(svc.add_stage_text, con, user["id"], event_id, body.text, body.division_id)


@router.post("/api/comp/events/{event_id}/stages/parse")
def comp_stages_parse(event_id: int, body: ParsePhotoIn, user: dict = Depends(require_user),
                      con=Depends(_con)):
    uid = user["id"]
    _call(svc.context, con, uid, event_id, body.division_id)         # права/404 сразу
    from tj.services import uploads
    _call(uploads.get, con, uid, body.upload_id)
    return _job(con, uid, "comp_stages_parse",
                lambda c: svc.parse_stages(c, uid, event_id, body.upload_id, body.division_id,
                                                  note=body.note),
                {"event_id": event_id})


@router.post("/api/comp/stages/confirm")
def comp_stages_confirm(body: StagesConfirmIn, user: dict = Depends(require_user),
                        con=Depends(_con)):
    return _call(svc.confirm_stages, con, user["id"], body.event_id, body.stages,
                 body.division_id)


@router.post("/api/comp/events/{event_id}/results")
def comp_result_text(event_id: int, body: ResultTextIn, user: dict = Depends(require_user),
                     con=Depends(_con)):
    return _call(svc.add_result_text, con, user["id"], event_id, body.text,
                 athlete=body.athlete, division_id=body.division_id, stage_idx=body.stage_idx)


@router.post("/api/comp/events/{event_id}/results/parse")
def comp_results_parse(event_id: int, body: ParsePhotoIn, user: dict = Depends(require_user),
                       con=Depends(_con)):
    uid = user["id"]
    _call(svc.context, con, uid, event_id, body.division_id)
    from tj.services import uploads
    _call(uploads.get, con, uid, body.upload_id)
    return _job(con, uid, "comp_results_parse",
                lambda c: svc.parse_results(c, uid, event_id, body.upload_id,
                                            athlete=body.athlete, division_id=body.division_id,
                                            note=body.note),
                {"event_id": event_id})


@router.post("/api/comp/results/confirm")
def comp_results_confirm(body: ResultsConfirmIn, user: dict = Depends(require_user),
                         con=Depends(_con)):
    return _call(svc.confirm_results, con, user["id"], body.event_id, body.rows,
                 athlete=body.athlete, division_id=body.division_id)


@router.get("/api/comp/events/{event_id}/total")
def comp_total_suggest(event_id: int, athlete: str = svc.ME, division_id: int | None = None,
                       user: dict = Depends(require_user), con=Depends(_con)):
    return _call(svc.total_suggestion, con, user["id"], event_id, athlete=athlete,
                 division_id=division_id)


@router.put("/api/comp/events/{event_id}/total")
def comp_total(event_id: int, body: TotalIn, user: dict = Depends(require_user),
               con=Depends(_con)):
    return _call(svc.set_total, con, user["id"], event_id, total_points=body.total_points,
                 final_place=body.final_place, athlete=body.athlete,
                 division_id=body.division_id)


@router.put("/api/comp/divisions/{division_id}/field_size")
def comp_field_size(division_id: int, body: FieldSizeIn, user: dict = Depends(require_user),
                    con=Depends(_con)):
    return _call(svc.set_field_size, con, user["id"], division_id, body.field_size)
