"""Атлет может ходить в несколько залов: user_gyms(tg_id, gym) — дополнительные залы.

Основной зал остаётся в users.gym (совместимость с ботом и онбордингом)."""
from __future__ import annotations

import sqlite3


def upgrade(con: sqlite3.Connection) -> None:
    con.execute('CREATE TABLE IF NOT EXISTS user_gyms ('
                '"tg_id" INTEGER NOT NULL, "gym" TEXT NOT NULL, PRIMARY KEY("tg_id","gym"))')
    con.commit()
