from __future__ import annotations

from pathlib import Path

from tjbot import db as botdb


def test_default_db_path_respects_env(monkeypatch):
    monkeypatch.setenv("KUZ_DB_PATH", "/tmp/kuz-dev/training.dev.db")
    assert botdb.default_db_path() == Path("/tmp/kuz-dev/training.dev.db")


def test_default_db_path_falls_back_without_env(monkeypatch):
    monkeypatch.delenv("KUZ_DB_PATH", raising=False)
    expected = Path(botdb.__file__).resolve().parents[2] / "training.db"
    assert botdb.default_db_path() == expected
