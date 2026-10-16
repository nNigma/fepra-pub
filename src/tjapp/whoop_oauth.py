"""OAuth-колбэк Whoop: state -> tg_id, обмен кода на токены, статус connected."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from tj import config as cfgmod
from tj.adapters import whoop
from tj.services.urls import public_link
from tjbot import db as botdb

router = APIRouter()

_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>FePra</title></head>
<body style="font-family:-apple-system,sans-serif;text-align:center;padding:3em 1em">
<h2>Whoop подключён ✅</h2><p>Whoop connected. Можно вернуться в бота.</p>
</body></html>"""


def whoop_creds() -> tuple[str, str]:
    env = cfgmod.load_dotenv(cfgmod.default_env_path())
    cid = os.environ.get("WHOOP_CLIENT_ID") or env.get("WHOOP_CLIENT_ID", "")
    sec = os.environ.get("WHOOP_CLIENT_SECRET") or env.get("WHOOP_CLIENT_SECRET", "")
    return cid, sec


def redirect_uri() -> str:
    return os.environ.get("WHOOP_REDIRECT_URI") or public_link("/whoop/callback")


def _exchange_code(code: str) -> dict:
    cid, sec = whoop_creds()
    r = httpx.post(whoop.TOKEN_URL, data={
        "grant_type": "authorization_code", "code": code,
        "client_id": cid, "client_secret": sec,
        "redirect_uri": redirect_uri()}, timeout=30)
    r.raise_for_status()
    d = r.json()
    return {
        "access_token": d["access_token"],
        "refresh_token": d.get("refresh_token", ""),
        "expires_at": (datetime.now(timezone.utc)
                       + timedelta(seconds=int(d.get("expires_in", 3600)))).isoformat(timespec="seconds")}


@router.get("/whoop/callback")
async def whoop_callback(code: str = "", state: str = ""):
    con = botdb.connect(botdb.default_db_path())
    try:
        who = botdb.oauth_state_consume(con, state)
        if not who or who[1] != "whoop" or not code:
            raise HTTPException(status_code=400, detail="ссылка устарела — нажми «Подключить Whoop» заново")
        tg_id = who[0]
        try:
            tokens = _exchange_code(code)
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="обмен кода не удался, попробуй ещё раз")
        botdb.whoop_tokens_set(con, tg_id, **tokens)
        botdb.watch_account_ensure(con, tg_id, "whoop", "connected")
    finally:
        con.close()
    return HTMLResponse(_PAGE)
