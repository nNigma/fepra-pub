"""Web Push: публичный VAPID-ключ, подписка и отписка."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from tj.services import push as svc
from tjapp.deps import require_user
from tjbot import db as botdb

router = APIRouter()


def _con():
    con = botdb.connect(botdb.default_db_path())
    try:
        yield con
    finally:
        con.close()


class Keys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=512)
    auth: str = Field(min_length=1, max_length=512)


class SubscribeIn(BaseModel):
    """Формат PushSubscription.toJSON() из браузера."""
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: Keys


class UnsubscribeIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2048)


@router.get("/api/push/key")
def push_key(user: dict = Depends(require_user)):
    key = svc.public_key()
    if not key:
        raise HTTPException(status_code=503, detail="push не настроен на сервере")
    return {"public_key": key}


@router.post("/api/push/subscribe")
def push_subscribe(body: SubscribeIn, request: Request, user: dict = Depends(require_user),
                   con=Depends(_con)):
    if not body.endpoint.startswith("https://"):
        raise HTTPException(status_code=422, detail="endpoint должен быть https")
    sid = svc.subscribe(con, user["id"], body.endpoint, body.keys.p256dh, body.keys.auth,
                        ua=(request.headers.get("user-agent") or "")[:300])
    return {"id": sid}


@router.post("/api/push/unsubscribe")
def push_unsubscribe(body: UnsubscribeIn, user: dict = Depends(require_user), con=Depends(_con)):
    return {"ok": svc.unsubscribe(con, user["id"], body.endpoint)}
