"""Загрузки файлов: POST /api/uploads (multipart) и GET /api/uploads/{id} (владелец или админ)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response
from starlette.formparsers import MultiPartException, MultiPartParser

from tj.services import uploads as svc
from tjapp.deps import require_user
from tjbot import access

from ._common import call, db_con, open_con

router = APIRouter()

_CHUNK = 64 * 1024
_ENVELOPE = 64 * 1024        # запас Content-Length на multipart-обвязку


async def _read_limited(file: UploadFile) -> bytes:
    """Читаем кусками и обрываем на MAX+1: файл больше лимита не собираем в памяти целиком."""
    buf = bytearray()
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        buf += chunk
        if len(buf) > svc.MAX_BYTES:
            raise HTTPException(status_code=422, detail="файл больше 10 МБ")
    return bytes(buf)


async def _limited_stream(request: Request):
    """Тело запроса кусками; больше лимита (+обвязка) — обрываем, не дочитывая."""
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > svc.MAX_BYTES + _ENVELOPE:
            raise HTTPException(status_code=422, detail="файл больше 10 МБ")
        yield chunk


@router.post("/api/uploads")
async def upload(request: Request, user: dict = Depends(require_user)):
    """multipart: поле file (обязательно) и kind (board|meal|other). Разбираем тело сами, чтобы
    лимит сработал ДО того, как фреймворк примет гигантский файл целиком."""
    if not (request.headers.get("content-type") or "").lower().startswith("multipart/form-data"):
        raise HTTPException(status_code=422, detail="ожидается multipart/form-data")
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > svc.MAX_BYTES + _ENVELOPE:
        raise HTTPException(status_code=422, detail="файл больше 10 МБ")     # до чтения тела
    try:
        form = await MultiPartParser(request.headers, _limited_stream(request),
                                     max_files=1, max_fields=5).parse()
    except MultiPartException as e:
        raise HTTPException(status_code=400, detail=str(e.message))
    file = form.get("file")
    if file is None or not hasattr(file, "read"):
        raise HTTPException(status_code=422, detail="нужен файл в поле file")
    kind = form.get("kind") or "other"
    if not isinstance(kind, str):
        raise HTTPException(status_code=422, detail="kind: строка")
    try:
        data = await _read_limited(file)
    finally:
        await form.close()
    # content-type от клиента лишь подсказка; тип решает сигнатура байтов (в сервисе)
    con = open_con()      # соединение создаём в потоке самого async-обработчика
    try:
        r = call(svc.save, con, user["id"], data, kind=kind, declared_mime=file.content_type)
    finally:
        con.close()
    return {"id": r["id"], "url": r["url"], "mime": r["mime"], "size": r["size"], "kind": r["kind"]}


@router.get("/api/uploads/{upload_id}")
def download(upload_id: str, user: dict = Depends(require_user), con=Depends(db_con)):
    if access.is_admin(user["id"]):
        rec = call(svc.get_any, con, upload_id)
    else:
        rec = call(svc.get, con, user["id"], upload_id)      # чужая = 404
    data, mime = call(svc.read_record, rec)
    return Response(content=data, media_type=mime, headers={
        "Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline"})
