"""Уведомления пользователю (user_notices): баннеры PWA."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ._schema import ensure

_MIG = "0040_user_notices"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def add(con, uid: int, kind: str, text: str, dedupe: bool = True) -> str | None:
    """Записать уведомление. dedupe: если непрочитанное того же kind уже есть — не дублируем
    (возвращает None)."""
    ensure(con, _MIG)
    if dedupe and con.execute(
            'SELECT 1 FROM user_notices WHERE "uid"=? AND "kind"=? AND "read_at" IS NULL',
            (int(uid), kind)).fetchone():
        return None
    nid = str(uuid.uuid4())
    con.execute('INSERT INTO user_notices ("id","uid","kind","text","created_at") VALUES (?,?,?,?,?)',
                (nid, int(uid), kind, text, _now()))
    con.commit()
    return nid


def list_notices(con, uid: int, unread_only: bool = False, limit: int = 50) -> list[dict]:
    ensure(con, _MIG)
    sql = 'SELECT "id","kind","text","created_at","read_at" FROM user_notices WHERE "uid"=?'
    if unread_only:
        sql += ' AND "read_at" IS NULL'
    sql += ' ORDER BY "created_at" DESC, rowid DESC LIMIT ?'
    return [dict(r) for r in con.execute(sql, (int(uid), int(limit))).fetchall()]


def mark_read(con, uid: int, notice_id: str) -> bool:
    """Только свои уведомления; повторное прочтение не меняет read_at."""
    ensure(con, _MIG)
    cur = con.execute('UPDATE user_notices SET "read_at"=? WHERE "id"=? AND "uid"=? AND "read_at" IS NULL',
                      (_now(), notice_id, int(uid)))
    con.commit()
    if cur.rowcount:
        return True
    return con.execute('SELECT 1 FROM user_notices WHERE "id"=? AND "uid"=?',
                       (notice_id, int(uid))).fetchone() is not None


def mark_kind_read(con, uid: int, kind: str) -> int:
    ensure(con, _MIG)
    cur = con.execute('UPDATE user_notices SET "read_at"=? WHERE "uid"=? AND "kind"=? AND "read_at" IS NULL',
                      (_now(), int(uid), kind))
    con.commit()
    return cur.rowcount
