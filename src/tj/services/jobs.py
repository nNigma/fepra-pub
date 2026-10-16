"""Фоновые задачи: POST возвращает job_id, результат — GET /api/jobs/{id}.

Состояние в таблице jobs (переживает рестарт), исполнение — потоки процесса
(uvicorn в один воркер). Зависшие после рестарта задачи помечаются ошибкой.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

STATUSES = ("pending", "running", "done", "error")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_job(con: sqlite3.Connection, kind: str, uid: int, payload: Any = None) -> str:
    jid = str(uuid.uuid4())
    t = _ts()
    con.execute('INSERT INTO jobs ("id","uid","kind","status","payload","created_at","updated_at") '
                'VALUES (?,?,?,?,?,?,?)',
                (jid, int(uid), kind, "pending",
                 json.dumps(payload, ensure_ascii=False) if payload is not None else None, t, t))
    con.commit()
    return jid


def _set(con, job_id: str, status: str, result: Any = None, error: str | None = None) -> None:
    con.execute('UPDATE jobs SET "status"=?,"result"=?,"error"=?,"updated_at"=? WHERE "id"=?',
                (status, json.dumps(result, ensure_ascii=False) if result is not None else None,
                 error, _ts(), job_id))
    con.commit()


def set_running(con, job_id: str) -> None:
    _set(con, job_id, "running")


def set_result(con, job_id: str, result: Any) -> None:
    _set(con, job_id, "done", result=result)


def set_error(con, job_id: str, error: str) -> None:
    _set(con, job_id, "error", error=str(error)[:2000])


def get_job(con, job_id: str, uid: int) -> dict | None:
    """Задача только для владельца; чужая или несуществующая — None (404)."""
    r = con.execute('SELECT * FROM jobs WHERE "id"=? AND "uid"=?', (job_id, int(uid))).fetchone()
    if r is None:
        return None
    return {"id": r["id"], "kind": r["kind"], "status": r["status"],
            "result": json.loads(r["result"]) if r["result"] else None,
            "error": r["error"], "created_at": r["created_at"], "updated_at": r["updated_at"]}


def fail_stale(con) -> int:
    """При старте процесса: pending/running → error (потоки не пережили рестарт)."""
    cur = con.execute('UPDATE jobs SET "status"=\'error\',"error"=\'прервано перезапуском сервера\','
                      '"updated_at"=? WHERE "status" IN (\'pending\',\'running\')', (_ts(),))
    con.commit()
    return cur.rowcount


def run_in_background(job_id: str, fn: Callable[[], Any], db_path=None) -> threading.Thread:
    """Выполнить fn() в потоке: возврат → done(result), исключение → error.
    Результат fn должен сериализоваться в JSON. Возвращает поток (тесты делают join)."""
    from tjbot import db as botdb
    path = db_path or botdb.default_db_path()

    def _worker():
        con = botdb.connect(path)
        try:
            set_running(con, job_id)
            try:
                res = fn()
            except Exception as e:
                set_error(con, job_id, f"{type(e).__name__}: {e}")
            else:
                set_result(con, job_id, res)
        finally:
            con.close()

    th = threading.Thread(target=_worker, name=f"job-{job_id[:8]}", daemon=True)
    th.start()
    return th
