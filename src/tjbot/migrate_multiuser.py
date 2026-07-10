"""Идемпотентная миграция: daily/activities -> мультитенант (колонка tg_id).
daily получает составной PK (tg_id, day) — пересоздание; activities — ALTER.
Существующие строки бэкфиллятся на owner_id. Гнать ТОЛЬКО поверх свежего kuz-ops-снимка.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from tj.store.build import _DDL


def _cols(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info({table})')]


def migrate(db_path, owner_id: int) -> dict:
    con = sqlite3.connect(str(Path(db_path)))
    changed = {"daily": False, "activities": False}
    try:
        if "tg_id" not in _cols(con, "daily"):
            old = [c for c in _cols(con, "daily")]           # без tg_id
            con.execute("ALTER TABLE daily RENAME TO daily_old")
            con.execute(_DDL["daily"])                        # новая схема с PK (tg_id, day)
            collist = ", ".join(f'"{c}"' for c in old)
            con.execute(f'INSERT INTO daily ({collist}, "tg_id") '
                        f'SELECT {collist}, ? FROM daily_old', (owner_id,))
            con.execute("DROP TABLE daily_old")
            changed["daily"] = True
        if "tg_id" not in _cols(con, "activities"):
            con.execute('ALTER TABLE activities ADD COLUMN "tg_id" INTEGER')
            con.execute('UPDATE activities SET "tg_id"=? WHERE "tg_id" IS NULL', (owner_id,))
            changed["activities"] = True
        con.commit()
    finally:
        con.close()
    return changed


if __name__ == "__main__":
    import sys
    from tjbot.db import OWNER_ID, default_db_path
    path = sys.argv[1] if len(sys.argv) > 1 else str(default_db_path())
    print(migrate(path, OWNER_ID))
