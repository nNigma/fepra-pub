"""Программа зала: просмотр, ожидающие черновики, правка текстом, словарь движений, статистика, атлеты."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from tj.services import clock
from tj.services import club as svc
from tj.services import jobs as jobs_svc
from tj.services import uploads as uploads_svc
from tjapp.deps import require_user
from tjbot import db as botdb

from ._common import call, get_con

router = APIRouter()


def _raise(e: svc.ClubError):
    raise HTTPException(status_code=e.status, detail=e.detail)


@router.get("/api/club/gyms")
def my_gyms(user: dict = Depends(require_user), con=Depends(get_con)):
    """Залы для выбора: админу все, тренеру его залы (и зал из профиля), атлету только свой.
    current — зал по умолчанию, can_manage у каждого зала — можно ли в нём менять программу."""
    return svc.gyms_for(con, user["id"])


@router.get("/api/club/program")
def get_program(day: str | None = Query(default=None), gym: str | None = Query(default=None),
                user: dict = Depends(require_user), con=Depends(get_con)):
    try:
        d = svc.parse_day(day, clock.today())
        return svc.program_for_day(con, user["id"], d, gym)
    except svc.ClubError as e:
        _raise(e)


class ProgramIn(BaseModel):
    day: str
    raw_text: str = Field(max_length=svc.MAX_TEXT * 2)
    gym: str | None = None


@router.put("/api/club/program")
def put_program(body: ProgramIn, user: dict = Depends(require_user), con=Depends(get_con)):
    """Заменить программу зала на день текстом. Ответ: {program, unknown, job_id}: unknown — фразы
    без канона (словарь: POST /api/club/movements/resolve), job_id — фоновая выверка блоков или null."""
    uid = user["id"]
    try:
        day = svc.parse_day(body.day, clock.today())
        prog = svc.save_program(con, uid, day, body.raw_text, body.gym)
    except svc.ClubError as e:
        _raise(e)
    unknown = prog.pop("unknown")
    try:                                    # атлеты зала узнают, что программа появилась
        svc.notify_members(con, uid, prog["gym"], day, clock.today())
    except Exception as e:  # noqa: BLE001
        print(f"[club] notify skipped: {type(e).__name__}", flush=True)
    job_id = None
    if svc.should_verify(uid, con, prog["raw_text"]):
        db_path, pid = botdb.default_db_path(), prog["id"]
        job_id = jobs_svc.create_job(con, "club_verify", uid, {"program_id": pid})
        jobs_svc.run_in_background(job_id, lambda: svc.verify_blocks(db_path, pid))
    return {"program": prog, "unknown": unknown, "job_id": job_id}


class PreviewIn(BaseModel):
    raw_text: str = Field(max_length=svc.MAX_TEXT * 2)
    gym: str | None = None


@router.post("/api/club/program/preview")
def preview(body: PreviewIn, user: dict = Depends(require_user), con=Depends(get_con)):
    """Разбор текста без сохранения: формат, движения, нераспознанное (экран подтверждения)."""
    try:
        return svc.preview(con, user["id"], body.raw_text, body.gym)
    except svc.ClubError as e:
        _raise(e)


@router.get("/api/club/pending")
def pending(gym: str | None = Query(default=None), user: dict = Depends(require_user),
            con=Depends(get_con)):
    try:
        return svc.pending(con, user["id"], gym)
    except svc.ClubError as e:
        _raise(e)


class ConfirmIn(BaseModel):
    raw_text: str | None = Field(default=None, max_length=svc.MAX_TEXT * 2)


@router.post("/api/club/pending/{prog_id}/confirm")
def confirm(prog_id: int, body: ConfirmIn | None = None, user: dict = Depends(require_user),
            con=Depends(get_con)):
    try:
        return svc.confirm(con, user["id"], prog_id, body.raw_text if body else None)
    except svc.ClubError as e:
        _raise(e)


@router.delete("/api/club/pending/{prog_id}")
def reject(prog_id: int, user: dict = Depends(require_user), con=Depends(get_con)):
    try:
        svc.reject(con, user["id"], prog_id)
    except svc.ClubError as e:
        _raise(e)
    return {"ok": True}


@router.get("/api/club/stats")
def stats(gym: str | None = Query(default=None), user: dict = Depends(require_user),
          con=Depends(get_con)):
    try:
        return svc.movement_stats(con, user["id"], gym, botdb.user_lang(con, user["id"]))
    except svc.ClubError as e:
        _raise(e)


@router.get("/api/club/athletes")
def athletes(days: int = Query(default=30, ge=1, le=svc.MAX_ATHLETE_DAYS),
             gym: str | None = Query(default=None), user: dict = Depends(require_user),
             con=Depends(get_con)):
    try:
        return svc.athletes(con, user["id"], clock.today(), days, gym)
    except svc.ClubError as e:
        _raise(e)


@router.get("/api/club/dictionary")
def dictionary(user: dict = Depends(require_user), con=Depends(get_con)):
    try:
        svc.require_manage(con, user["id"])
    except svc.ClubError as e:
        _raise(e)
    return svc.dictionary(con)


class AliasPair(BaseModel):
    alias: str = Field(max_length=200)
    canon: str = Field(max_length=200)


class AliasesIn(BaseModel):
    pairs: list[AliasPair] = Field(min_length=1, max_length=100)


@router.post("/api/club/aliases")
def add_aliases(body: AliasesIn, user: dict = Depends(require_user), con=Depends(get_con)):
    try:
        svc.require_manage(con, user["id"])
    except svc.ClubError as e:
        _raise(e)
    return {"added": svc.add_aliases(con, [(p.alias, p.canon) for p in body.pairs])}


class ResolveIn(BaseModel):
    phrase: str = Field(max_length=200)
    name: str | None = Field(default=None, max_length=200)


@router.post("/api/club/movements/resolve")
def resolve_movement(body: ResolveIn, user: dict = Depends(require_user), con=Depends(get_con)):
    """Сопоставить нераспознанную фразу: без name — новое движение «как есть», с name — существующее."""
    try:
        svc.require_manage(con, user["id"])
        return svc.resolve_movement(con, body.phrase, body.name)
    except svc.ClubError as e:
        _raise(e)


class ParsePhotoIn(BaseModel):
    upload_id: str
    engine: str = "fast"
    gym: str | None = None


@router.post("/api/club/program/parse")
def parse_photo(body: ParsePhotoIn, user: dict = Depends(require_user), con=Depends(get_con)):
    """Фото доски -> текст для редактора программы зала (задача). Только админ/тренер зала;
    квота ИИ не списывается. Результат job: {recognized, reason, board_text, ...}."""
    uid = user["id"]
    try:
        svc.require_manage(con, uid, body.gym)
    except svc.ClubError as e:
        _raise(e)
    call(uploads_svc.get, con, uid, body.upload_id)          # чужая или несуществующая загрузка -> 404
    db_path = botdb.default_db_path()
    job_id = jobs_svc.create_job(con, "club_parse", uid, {"upload_id": body.upload_id})
    jobs_svc.run_in_background(
        job_id, lambda: svc.parse_board_photo(db_path, uid, body.upload_id, body.engine))
    return {"job_id": job_id}
