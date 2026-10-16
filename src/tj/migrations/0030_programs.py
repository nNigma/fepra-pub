"""0030: каталог программ, записи на программы, сессии и журнал подходов (фаза 4).

Только добавление: бот живёт на той же БД. Идемпотентно (IF NOT EXISTS).
Дерево каталога наполняется из tj/data/programs/catalog.json (повторный вызов обновляет строки).
"""
from __future__ import annotations

import sqlite3

DDL = (
    """CREATE TABLE IF NOT EXISTS program_nodes (
        id TEXT PRIMARY KEY,
        parent_id TEXT,
        kind TEXT NOT NULL CHECK (kind IN ('sport','system','program')),
        slug TEXT NOT NULL UNIQUE,
        title_ru TEXT NOT NULL,
        title_en TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('active','planned','hidden')),
        sort INTEGER NOT NULL DEFAULT 0,
        template_slug TEXT )""",
    """CREATE TABLE IF NOT EXISTS program_enrollments (
        id TEXT PRIMARY KEY,
        uid INTEGER NOT NULL,
        program_slug TEXT NOT NULL,
        template_version INTEGER NOT NULL,
        start_day TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','done','cancelled')),
        base_maxes TEXT,
        level TEXT,
        created_at TEXT,
        updated_at TEXT,
        deleted_at TEXT )""",
    "CREATE INDEX IF NOT EXISTS ix_program_enrollments_uid ON program_enrollments (uid, status)",
    """CREATE TABLE IF NOT EXISTS program_sessions (
        id TEXT PRIMARY KEY,
        enrollment_id TEXT NOT NULL,
        planned_day TEXT NOT NULL,
        week INTEGER NOT NULL,
        idx INTEGER NOT NULL,
        kind TEXT NOT NULL DEFAULT 'normal' CHECK (kind IN ('normal','test','deload')),
        status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','in_progress','done','skipped')),
        plan TEXT,
        checkin TEXT,
        activity_id TEXT,
        updated_at TEXT,
        UNIQUE (enrollment_id, week, idx) )""",
    "CREATE INDEX IF NOT EXISTS ix_program_sessions_enr_day ON program_sessions (enrollment_id, planned_day)",
    """CREATE TABLE IF NOT EXISTS set_log (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        exercise TEXT,
        planned_kg REAL,
        done_kg REAL,
        reps INTEGER,
        ok INTEGER,
        note TEXT,
        ts TEXT,
        updated_at TEXT,
        deleted_at TEXT )""",
    "CREATE INDEX IF NOT EXISTS ix_set_log_session ON set_log (session_id)",
)


def upgrade(con: sqlite3.Connection) -> None:
    for ddl in DDL:
        con.execute(ddl)
    from tj.services.programs import seed_catalog
    seed_catalog(con)
    con.commit()
