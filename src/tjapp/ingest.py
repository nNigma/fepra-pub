"""Приёмник push-данных от компаньонов часов (Samsung через Health Connect, Apple Watch).

Bearer-токен -> (tg_id, provider); тело -> маппер -> insert_daily/insert_activity.
HR-серия кладётся в sidecar data/hr_<tg_id>_<activity_id>.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from tj.ingest import apple_health as ah
from tj.ingest import health_connect as hc
from tjbot import db as botdb

router = APIRouter()


def _auth(authorization: str | None, provider: str):
    parts = (authorization or "").split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="no token")
    raw = parts[1].strip()
    con = botdb.connect(botdb.default_db_path())
    try:
        who = botdb.resolve_watch_token(con, raw)
    finally:
        con.close()
    if not who:
        raise HTTPException(status_code=401, detail="bad token")
    if who[1] != provider:
        raise HTTPException(status_code=403, detail="wrong provider")
    return who


def _data_dir() -> Path:
    d = botdb.default_db_path().parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _store_hr_series(a, tg_id: int) -> None:
    series = (a.extra or {}).pop("_hr_series", None)
    if isinstance(series, list) and len(series) >= 2 and a.activity_id:
        safe_id = re.sub(r"[^\w.-]", "_", str(a.activity_id))
        name = f"hr_{tg_id}_{safe_id}.json"
        (_data_dir() / name).write_text(json.dumps(series, ensure_ascii=False),
                                        encoding="utf-8")
        a.extra["hr_series_ref"] = f"data/{name}"


@router.post("/ingest/samsung/verify")
async def ingest_verify(authorization: str | None = Header(None)):
    tg_id, provider = _auth(authorization, "samsung")
    con = botdb.connect(botdb.default_db_path())
    try:
        botdb.watch_account_set_status(con, tg_id, provider, "connected")
    finally:
        con.close()
    return {"ok": True}


@router.post("/ingest/samsung")
async def ingest_samsung(request: Request, authorization: str | None = Header(None)):
    tg_id, provider = _auth(authorization, "samsung")
    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="bad json")
    days, acts = hc.parse(payload if isinstance(payload, dict) else {})
    con = botdb.connect(botdb.default_db_path())
    try:
        for m in days:
            botdb.upsert_daily_merge(con, m, tg_id)
        for a in acts:
            _store_hr_series(a, tg_id)
            botdb.insert_activity(con, a, tg_id)
        botdb.touch_watch_sync(con, tg_id, provider)
    finally:
        con.close()
    return {"days_written": len(days), "activities_written": len(acts)}


@router.post("/ingest/apple")
async def ingest_apple(request: Request, authorization: str | None = Header(None)):
    tg_id, provider = _auth(authorization, "apple")
    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="bad json")
    days, acts = ah.parse(payload if isinstance(payload, dict) else {})
    con = botdb.connect(botdb.default_db_path())
    try:
        for m in days:
            botdb.upsert_daily_merge(con, m, tg_id)
        for a in acts:
            _store_hr_series(a, tg_id)
            botdb.insert_activity(con, a, tg_id)
        botdb.touch_watch_sync(con, tg_id, provider)
    finally:
        con.close()
    return {"days_written": len(days), "activities_written": len(acts)}
