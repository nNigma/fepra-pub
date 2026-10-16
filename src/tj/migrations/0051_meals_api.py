"""0050: приёмы пищи через API — клиентский uuid для идемпотентной записи.

Только добавление: nullable-колонка meals.client_uuid и частичный уникальный индекс
(tg_id, client_uuid). Бот колонку не знает и не трогает. meals.photo_path добавляет 0022.
"""
from __future__ import annotations


def _has_table(con, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (name,)).fetchone() is not None


def _has_col(con, table: str, col: str) -> bool:
    return any(r[1] == col for r in con.execute(f'PRAGMA table_info("{table}")'))


def upgrade(con) -> None:
    if _has_table(con, "meals"):
        if not _has_col(con, "meals", "photo_path"):     # на случай порядка миграций
            con.execute('ALTER TABLE meals ADD COLUMN "photo_path" TEXT')
        if not _has_col(con, "meals", "client_uuid"):
            con.execute('ALTER TABLE meals ADD COLUMN "client_uuid" TEXT')
        con.execute('CREATE UNIQUE INDEX IF NOT EXISTS meals_client_uuid_idx '
                    'ON meals ("tg_id","client_uuid") WHERE "client_uuid" IS NOT NULL')
    con.commit()
