"""Ленивое применение миграций сервисов: таблицы создаются при первом обращении.

Миграции идемпотентны (IF NOT EXISTS), поэтому вызов безопасен и поверх
общего раннера фундамента, и в тестах поверх голого ``tjbot.db.init_schema``.
Кэша нет намеренно: соединения короткоживущие, а DDL IF NOT EXISTS дёшев.
"""
from __future__ import annotations

import importlib
import sqlite3


def ensure(con: sqlite3.Connection, migration: str) -> None:
    """migration — имя модуля без пакета, напр. ``0040_user_notices``."""
    importlib.import_module(f"tj.migrations.{migration}").upgrade(con)
