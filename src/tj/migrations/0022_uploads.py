"""0020: загрузки файлов (uploads) и ссылка на файл фото еды (meals.photo_path).

Только добавление: бот продолжает работать на той же БД.
"""
from __future__ import annotations


def _has_table(con, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (name,)).fetchone() is not None


def _has_col(con, table: str, col: str) -> bool:
    return any(r[1] == col for r in con.execute(f'PRAGMA table_info("{table}")'))


def upgrade(con) -> None:
    con.execute(
        '''CREATE TABLE IF NOT EXISTS uploads (
            "id" TEXT PRIMARY KEY, "uid" INTEGER NOT NULL, "kind" TEXT,
            "path" TEXT NOT NULL, "mime" TEXT, "size" INTEGER, "sha256" TEXT,
            "created_at" TEXT, "deleted_at" TEXT )''')
    con.execute('CREATE INDEX IF NOT EXISTS uploads_uid_idx ON uploads ("uid","created_at")')
    if _has_table(con, "meals") and not _has_col(con, "meals", "photo_path"):
        con.execute('ALTER TABLE meals ADD COLUMN "photo_path" TEXT')
    con.commit()
