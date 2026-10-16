"""Программы зала (wod_programs): UUID, время правки, автор. Все колонки nullable —
бот и userbot пишут в таблицу без них, сервис дозаполняет uuid лениво."""
import sqlite3

_COLS = (("uuid", "TEXT"), ("updated_at", "TEXT"), ("created_by", "INTEGER"))


def upgrade(con: sqlite3.Connection) -> None:
    have = {r[1] for r in con.execute('PRAGMA table_info("wod_programs")')}
    if have:
        for name, typ in _COLS:
            if name not in have:
                con.execute(f'ALTER TABLE wod_programs ADD COLUMN "{name}" {typ}')
        con.execute('CREATE INDEX IF NOT EXISTS idx_wod_programs_gym_day '
                    'ON wod_programs ("gym","day")')
    con.commit()
