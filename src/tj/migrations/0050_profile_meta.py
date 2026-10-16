"""Профиль: время последней правки (users.updated_at, nullable; бот колонку не трогает)."""
import sqlite3


def upgrade(con: sqlite3.Connection) -> None:
    cols = {r[1] for r in con.execute('PRAGMA table_info("users")')}
    if cols and "updated_at" not in cols:
        con.execute('ALTER TABLE users ADD COLUMN "updated_at" TEXT')
    con.commit()
