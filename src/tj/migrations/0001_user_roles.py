"""Роли пользователей в БД (вместо четырёх JSON-файлов) + разовый импорт из них."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

_FILES = {  # роль -> (файл, ключ)
    "allowlist": ("users_allow.json", "allowed_users"),
    "admin": ("admins.json", "admins"),
    "pro": ("pro_users.json", "pro_users"),
    "coach": ("coaches.json", "coaches"),
}


def _db_file(con: sqlite3.Connection) -> Path | None:
    for r in con.execute("PRAGMA database_list"):
        if r[1] == "main" and r[2]:
            return Path(r[2])
    return None


def _candidate_dirs(con) -> list[Path]:
    dbf = _db_file(con)
    if dbf is None:
        return []
    dirs = [dbf.parent]
    from tjbot import db as botdb
    try:
        # каталог кода — только для БД по умолчанию; с переопределённым FEPRA_DB_PATH
        # (тесты, dev) чужие боевые JSON подтягивать нельзя
        if "FEPRA_DB_PATH" not in os.environ and dbf.resolve() == botdb.default_db_path().resolve():
            # файлы там, где их искал tjbot/access.py
            dirs.append(Path(__file__).resolve().parents[2].parent)
    except OSError:
        pass
    return dirs


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def import_json_roles(con: sqlite3.Connection) -> int:
    n = 0
    for d in _candidate_dirs(con):
        for role, (fname, key) in _FILES.items():
            data = _read(d / fname)
            if not isinstance(data, dict):
                continue
            items = data.get(key) or ([] if role != "coach" else {})
            if role == "coach":
                pairs = list(dict(items).items())
            else:
                pairs = [(k, None) for k in items]
            for uid, gym in pairs:
                try:
                    uid = int(uid)
                except (TypeError, ValueError):
                    continue
                cur = con.execute(
                    'INSERT OR IGNORE INTO user_roles ("user_id","role","gym") VALUES (?,?,?)',
                    (uid, role, str(gym) if gym is not None else None))
                n += cur.rowcount
    return n


def upgrade(con: sqlite3.Connection) -> None:
    con.execute('CREATE TABLE IF NOT EXISTS user_roles ('
                '"user_id" INTEGER, "role" TEXT, "gym" TEXT, PRIMARY KEY("user_id","role"))')
    import_json_roles(con)
