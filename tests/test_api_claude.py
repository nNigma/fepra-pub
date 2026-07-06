from __future__ import annotations

from fastapi.testclient import TestClient
from tjbot import db as botdb
from tjapp import api
from tjapp.api import app, require_auth


def _setup(tmp_path, monkeypatch, pro: bool):
    dbp = tmp_path / "t.db"
    con = botdb.connect(dbp)
    botdb.init_schema(con)
    botdb.claude_review_put(con, 1, "2026-07-01", "# разбор\nтело")
    con.close()
    monkeypatch.setattr(api, "_db", lambda: str(dbp))
    monkeypatch.setattr(api, "is_pro", lambda tg: pro)
    app.dependency_overrides[require_auth] = lambda: {"id": 1}
    return TestClient(app)


def test_pro_gets_text(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=True)
    r = c.get("/api/claude/2026-07-01")
    assert r.status_code == 200
    assert r.json() == {"available": True, "text": "# разбор\nтело"}
    app.dependency_overrides.clear()


def test_pro_null_when_no_review(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=True)
    r = c.get("/api/claude/2026-07-02")
    assert r.status_code == 200
    assert r.json() == {"available": True, "text": None}
    app.dependency_overrides.clear()


def test_non_pro_not_available(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=False)
    r = c.get("/api/claude/2026-07-01")
    assert r.status_code == 200
    assert r.json() == {"available": False, "text": None}
    app.dependency_overrides.clear()
