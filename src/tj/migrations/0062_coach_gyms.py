"""Тренер может вести несколько залов: таблица coach_gyms(user_id, gym).

user_roles(user_id, 'coach').gym остаётся «основным» залом (совместимость с ботом и старым кодом),
полный список залов тренера — в coach_gyms. Существующие тренеры импортируются с их залом."""
from __future__ import annotations

import sqlite3


def upgrade(con: sqlite3.Connection) -> None:
    con.execute('CREATE TABLE IF NOT EXISTS coach_gyms ('
                '"user_id" INTEGER NOT NULL, "gym" TEXT NOT NULL, PRIMARY KEY("user_id","gym"))')
    con.execute('INSERT OR IGNORE INTO coach_gyms ("user_id","gym") '
                'SELECT "user_id","gym" FROM user_roles WHERE "role"=\'coach\' AND "gym" IS NOT NULL')
    con.commit()
