"""Зависимости FastAPI: кто делает запрос и какие у него права.

require_user — cookie `fepra_session` (PWA) ИЛИ заголовок X-Init-Data (старый Mini App).
Возвращает dict с ключом "id" (как раньше возвращал require_auth).
"""
from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException, Query, Request

from tj.services import auth as auth_svc
from tjbot import access
from tjbot import db as botdb

from . import auth as tg_auth

SESSION_COOKIE = "fepra_session"


def _user_from_session(raw: str | None) -> dict | None:
    if not raw:
        return None
    con = botdb.connect(botdb.default_db_path())
    try:
        uid = auth_svc.validate_session(con, raw)
    except Exception:  # БД без миграций и т.п. — как «нет сессии»
        return None
    finally:
        con.close()
    if uid is None or not access.is_allowed(uid):
        return None
    return {"id": uid, "via": "session"}


def require_user(x_init_data: str = Header(default=""),
                 fepra_session: str | None = Cookie(default=None)) -> dict:
    u = _user_from_session(fepra_session)
    if u is not None:
        return u
    if x_init_data:
        try:
            user = tg_auth.authorized_user(x_init_data)
        except tg_auth.AuthError as e:
            from urllib.parse import parse_qsl
            keys = [k for k, _ in parse_qsl(x_init_data)]
            print(f"[auth] 401: {e} | поля initData: {keys}", flush=True)
            raise HTTPException(status_code=401, detail=str(e))
        return {**user, "via": "initdata"}
    raise HTTPException(status_code=401, detail="нужен вход")


# Историческое имя: на него завязаны dependency_overrides в тестах API.
require_auth = require_user


def require_pro(user: dict = Depends(require_user)) -> dict:
    if not (access.is_admin(user["id"]) or access.is_pro(user["id"])):
        raise HTTPException(status_code=403, detail="нужен Pro")
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if not access.is_admin(user["id"]):
        raise HTTPException(status_code=403, detail="нужны права администратора")
    return user


def resolve_effective_user(user: dict = Depends(require_user),
                           as_user: int | None = Query(default=None, alias="as")) -> int:
    """Чьи данные показываем: ?as=<id> действует только для админа."""
    return tg_auth.resolve_effective_user(user["id"], as_user)


def client_ip(request: Request) -> str:
    """IP клиента; за локальным прокси (Funnel) берём последний элемент X-Forwarded-For."""
    host = request.client.host if request.client else "?"
    if host in ("127.0.0.1", "::1"):
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[-1].strip() or host
    return host
