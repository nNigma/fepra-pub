"""Синк Whoop: окно 3 дня перезахватом (recovery опаздывает за сном), идемпотентно."""
from __future__ import annotations

import os
from datetime import date, timedelta

import httpx

from tj import config as cfgmod
from tj.adapters import whoop
from . import db as botdb


def _creds() -> tuple[str, str]:
    env = cfgmod.load_dotenv(cfgmod.default_env_path())
    return (os.environ.get("WHOOP_CLIENT_ID") or env.get("WHOOP_CLIENT_ID", ""),
            os.environ.get("WHOOP_CLIENT_SECRET") or env.get("WHOOP_CLIENT_SECRET", ""))


def _client(db_path, tg_id: int) -> whoop.WhoopClient:
    def load():
        con = botdb.connect(db_path)
        try:
            return botdb.whoop_tokens_get(con, tg_id) or {}
        finally:
            con.close()

    def save(t):
        con = botdb.connect(db_path)
        try:
            botdb.whoop_tokens_set(con, tg_id, access_token=t["access_token"],
                                   refresh_token=t["refresh_token"],
                                   expires_at=t.get("expires_at", ""))
        finally:
            con.close()

    return whoop.WhoopClient(_creds(), load, save)


def sync_recent(db_path, tg_id: int, days_back: int = 3) -> dict:
    con = botdb.connect(db_path)
    try:
        if not botdb.whoop_tokens_get(con, tg_id):
            return {"error": "not connected"}
        client = _client(db_path, tg_id)
        start = (date.today() - timedelta(days=days_back)).isoformat() + "T00:00:00.000Z"
        end = (date.today() + timedelta(days=1)).isoformat() + "T00:00:00.000Z"
        try:
            sleeps = client.collection("/activity/sleep", start, end)
            recs = client.collection("/recovery", start, end)
            works = client.collection("/activity/workout", start, end)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 401, 403):
                botdb.watch_account_set_status(con, tg_id, "whoop", "error")
            return {"error": e.response.status_code}
        except httpx.HTTPError as e:
            return {"error": type(e).__name__}
        days = whoop.map_daily(sleeps, recs)
        acts = whoop.map_workouts(works)
        for m in days:
            botdb.upsert_daily_merge(con, m, tg_id)
        for a in acts:
            botdb.insert_activity(con, a, tg_id)
        botdb.touch_watch_sync(con, tg_id, "whoop")
        return {"days": len(days), "activities": len(acts)}
    finally:
        con.close()


def sync_all(db_path) -> dict:
    con = botdb.connect(db_path)
    try:
        ids = botdb.watch_accounts_by_provider(con, "whoop")
    finally:
        con.close()
    return {tg_id: sync_recent(db_path, tg_id) for tg_id in ids}
