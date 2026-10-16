"""Вход и профиль: инвайты, passkey, сессии, /api/me."""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from tj.services import auth as svc
from tj.services.urls import invite_url, public_url
from tjapp.deps import SESSION_COOKIE, client_ip, require_admin, require_user
from tjapp.ratelimit import RateLimiter
from tjbot import db as botdb

router = APIRouter()

# Защита от перебора (в памяти, один воркер): на IP.
redeem_limiter = RateLimiter(limit=10, window_s=600)
login_limiter = RateLimiter(limit=20, window_s=600)


def _con():
    con = botdb.connect(botdb.default_db_path())
    try:
        yield con
    finally:
        con.close()


def _limit(limiter: RateLimiter, request: Request) -> None:
    if not limiter.allow(client_ip(request)):
        raise HTTPException(status_code=429, detail="слишком много попыток, попробуй позже")


def _fail(e: svc.AuthFailure):
    raise HTTPException(status_code=e.status, detail=e.detail)


def _secure(request: Request) -> bool:
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        return True
    host = (request.url.hostname or "")
    return public_url().startswith("https://") and host not in ("localhost", "127.0.0.1", "::1", "testserver")


def _set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, max_age=svc.SESSION_TTL_DAYS * 86400, path="/",
                        httponly=True, samesite="lax", secure=_secure(request))


class InviteIn(BaseModel):
    role: str = "user"
    gym: str | None = None
    existing_user_id: int | None = None
    ttl_hours: float = 72
    note: str | None = Field(default=None, max_length=200)


@router.post("/api/admin/invites")
def create_invite(body: InviteIn, admin: dict = Depends(require_admin), con=Depends(_con)):
    try:
        token = svc.create_invite(con, admin["id"], body.role, body.gym, body.existing_user_id,
                                  body.ttl_hours, body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"token": token, "url": invite_url(token)}


@router.get("/api/admin/invites")
def list_invites(admin: dict = Depends(require_admin), con=Depends(_con)):
    return svc.list_invites(con)


class RedeemIn(BaseModel):
    token: str
    nick: str | None = None


@router.post("/api/auth/invite-info")
def invite_info(body: RedeemIn, request: Request, con=Depends(_con)):
    _limit(redeem_limiter, request)
    return svc.invite_info(con, body.token)


@router.post("/api/auth/redeem")
def redeem(body: RedeemIn, request: Request, response: Response, con=Depends(_con)):
    _limit(redeem_limiter, request)
    try:
        uid, sess = svc.redeem_invite(con, body.token, body.nick,
                                      user_agent=request.headers.get("user-agent", ""))
    except svc.AuthFailure as e:
        _fail(e)
    _set_cookie(response, request, sess)
    return svc.get_me(con, uid)


class PasskeyVerifyIn(BaseModel):
    challenge_id: str
    credential: dict
    name: str | None = None


@router.post("/api/auth/passkey/register/options")
def passkey_register_options(user: dict = Depends(require_user), con=Depends(_con)):
    return svc.passkey_register_options(con, user["id"])


@router.post("/api/auth/passkey/register/verify")
def passkey_register_verify(body: PasskeyVerifyIn, user: dict = Depends(require_user),
                            con=Depends(_con)):
    try:
        svc.passkey_register_verify(con, user["id"], body.challenge_id, body.credential, body.name)
    except svc.AuthFailure as e:
        _fail(e)
    return {"ok": True}


@router.post("/api/auth/passkey/login/options")
def passkey_login_options(request: Request, con=Depends(_con)):
    _limit(login_limiter, request)
    return svc.passkey_login_options(con)


@router.post("/api/auth/passkey/login/verify")
def passkey_login_verify(body: PasskeyVerifyIn, request: Request, response: Response,
                         con=Depends(_con)):
    _limit(login_limiter, request)
    try:
        uid, sess = svc.passkey_login_verify(con, body.challenge_id, body.credential,
                                             user_agent=request.headers.get("user-agent", ""))
    except svc.AuthFailure as e:
        _fail(e)
    _set_cookie(response, request, sess)
    return svc.get_me(con, uid)


@router.post("/api/auth/logout")
def logout(response: Response, fepra_session: str | None = Cookie(default=None), con=Depends(_con)):
    svc.revoke_session(con, fepra_session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/api/me")
def me(user: dict = Depends(require_user), con=Depends(_con)):
    return svc.get_me(con, user["id"])
