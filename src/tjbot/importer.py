"""Разовый импорт истории из cache.duckdb -> training.db (канон-таблицы).

Берёт уже собранный аналитический кэш (tj build) и переносит daily/activities/
competitions в SQLite один-в-один. Идемпотентно: канон перезаписывается целиком.
"""
from __future__ import annotations

from pathlib import Path

from tj.store.build import _COLS
from . import db as botdb


def import_from_duckdb(duck_path, sqlite_path) -> dict[str, int]:
    import duckdb

    con = botdb.connect(sqlite_path)
    botdb.init_schema(con)
    duck = duckdb.connect(str(duck_path), read_only=True)
    counts: dict[str, int] = {}
    try:
        for table, cols in _COLS.items():
            collist = ", ".join(f'"{c}"' for c in cols)
            rows = duck.execute(f"SELECT {collist} FROM {table}").fetchall()
            con.execute(f"DELETE FROM {table}")
            if rows:
                ph = ", ".join("?" * len(cols))
                con.executemany(f"INSERT INTO {table} VALUES ({ph})", rows)
            counts[table] = len(rows)
        con.commit()
    finally:
        duck.close()
        con.close()
    return counts


if __name__ == "__main__":
    import sys

    duck = sys.argv[1] if len(sys.argv) > 1 else "cache.duckdb"
    sqlite_path = sys.argv[2] if len(sys.argv) > 2 else str(botdb.default_db_path())
    res = import_from_duckdb(duck, sqlite_path)
    print(f"импорт -> {sqlite_path}")
    for t, n in res.items():
        print(f"  {t}: {n}")
