"""Нумерованные миграции схемы. Только добавление (бот живёт на той же БД).

Модуль `NNNN_name.py` с функцией `upgrade(con)` подхватывается автоматически.
Версия хранится в `meta.schema_version`; применяются только миграции новее.
Каждая миграция идемпотентна (IF NOT EXISTS / проверка колонок).
"""
from __future__ import annotations

import importlib
import pkgutil
import re
import sqlite3

_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+$")


def _registry() -> list[tuple[int, str]]:
    found = []
    for m in pkgutil.iter_modules(__path__):
        g = _NAME.match(m.name)
        if g:
            found.append((int(g.group(1)), m.name))
    found.sort()
    return found


def current_version(con: sqlite3.Connection) -> int:
    con.execute('CREATE TABLE IF NOT EXISTS meta ("key" TEXT PRIMARY KEY, "value" TEXT)')
    r = con.execute('SELECT "value" FROM meta WHERE "key"=\'schema_version\'').fetchone()
    try:
        return int(r[0]) if r else 0
    except (TypeError, ValueError):
        return 0


def _applied(con: sqlite3.Connection) -> set[str]:
    """Имена применённых миграций. Учёт по ИМЕНИ, а не по номеру: несколько веток
    добавляют миграции параллельно, и версия-«максимум» пропускала бы опоздавшие."""
    fresh = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone() is None
    con.execute('CREATE TABLE IF NOT EXISTS schema_migrations '
                '("name" TEXT PRIMARY KEY, "applied_at" TEXT)')
    if fresh:
        # БД, migрированные прежним номерным учётом: всё до версии включительно уже применено
        ver = current_version(con)
        for num, name in _registry():
            if num <= ver:
                con.execute('INSERT OR IGNORE INTO schema_migrations ("name","applied_at") '
                            "VALUES (?, datetime('now'))", (name,))
        con.commit()
    return {r[0] for r in con.execute('SELECT "name" FROM schema_migrations')}


def run_migrations(con: sqlite3.Connection) -> int:
    """Применить недостающие миграции; вернуть максимальный номер. Идемпотентно."""
    done = _applied(con)
    ver = current_version(con)
    for num, name in _registry():
        if name in done:
            continue
        mod = importlib.import_module(f"{__name__}.{name}")
        mod.upgrade(con)
        con.execute('INSERT OR IGNORE INTO schema_migrations ("name","applied_at") '
                    "VALUES (?, datetime('now'))", (name,))
        ver = max(ver, num)
        con.execute('INSERT OR REPLACE INTO meta ("key","value") VALUES (\'schema_version\',?)',
                    (str(ver),))
        con.commit()
    con.commit()
    return ver
