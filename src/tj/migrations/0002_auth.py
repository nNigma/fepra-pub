"""Идентичность и вход: identities, invites, sessions, passkeys, webauthn challenges."""
from __future__ import annotations

import sqlite3


def upgrade(con: sqlite3.Connection) -> None:
    con.executescript('''
    CREATE TABLE IF NOT EXISTS auth_identities (
        provider TEXT NOT NULL, subject TEXT NOT NULL, user_id INTEGER NOT NULL,
        created_at TEXT, PRIMARY KEY (provider, subject));
    CREATE INDEX IF NOT EXISTS idx_auth_identities_user ON auth_identities(user_id);
    CREATE TABLE IF NOT EXISTS invites (
        token_hash TEXT PRIMARY KEY, created_by INTEGER, role TEXT, gym TEXT,
        existing_user_id INTEGER, expires_at TEXT, used_at TEXT, used_by INTEGER, note TEXT,
        created_at TEXT);
    CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT,
        last_seen TEXT, expires_at TEXT, user_agent TEXT);
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    CREATE TABLE IF NOT EXISTS passkeys (
        credential_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, public_key BLOB,
        sign_count INTEGER DEFAULT 0, transports TEXT, created_at TEXT, name TEXT);
    CREATE INDEX IF NOT EXISTS idx_passkeys_user ON passkeys(user_id);
    CREATE TABLE IF NOT EXISTS webauthn_challenges (
        id TEXT PRIMARY KEY, user_id INTEGER, challenge TEXT NOT NULL, purpose TEXT,
        expires_at TEXT);
    ''')
    cols = {r[1] for r in con.execute("PRAGMA table_info(invites)")}
    if "created_at" not in cols:
        con.execute('ALTER TABLE invites ADD COLUMN created_at TEXT')
