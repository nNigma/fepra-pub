"""Фоновые задачи (LLM, vision, синк): результат читается через GET /api/jobs/{id}."""
from __future__ import annotations

import sqlite3


def upgrade(con: sqlite3.Connection) -> None:
    con.execute('CREATE TABLE IF NOT EXISTS jobs ('
                'id TEXT PRIMARY KEY, uid INTEGER NOT NULL, kind TEXT, status TEXT, '
                'payload TEXT, result TEXT, error TEXT, created_at TEXT, updated_at TEXT)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_jobs_uid ON jobs(uid)')
