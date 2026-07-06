from __future__ import annotations
from datetime import date
from fastapi.testclient import TestClient
from tj.models import DailyMetrics
from tjbot import db as botdb, access
from tjapp import api
from tjapp.api import app, require_auth


def _setup(tmp_path, monkeypatch, admin_id: int):
    dbp = tmp_path / "t.db"
    con = botdb.connect(dbp); botdb.init_schema(con)
    botdb.save_user(con, 111, nick="Аня", height_cm=170, weight_kg=60, sex="f", age=30, gym="U")
    botdb.save_user(con, 900, nick="Админ", height_cm=180, weight_kg=80, sex="m", age=40, gym="U")
    botdb.insert_daily(con, DailyMetrics(day=date(2026, 7, 1), readiness=42), tg_id=111)
    botdb.insert_daily(con, DailyMetrics(day=date(2026, 7, 1), readiness=77), tg_id=900)
    con.close()
    monkeypatch.setattr(api, "_db", lambda: str(dbp))
    monkeypatch.setattr(access, "load_admins", lambda path=None: {900})
    monkeypatch.setattr(access, "load_allow", lambda path=None: {900, 111})
    app.dependency_overrides[require_auth] = lambda: {"id": admin_id}
    return TestClient(app)


def test_admin_sees_target_user_via_as(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, admin_id=900)
    r = c.get("/api/summary?as=111", headers={"X-Init-Data": "x"})
    assert r.status_code == 200
    data = r.json()
    assert data["viewing"] == 111
    assert data["is_admin"] is True
    assert data["metrics"]["readiness"]["series"][-1] == ["2026-07-01", 42]
    app.dependency_overrides.clear()


def test_admin_without_as_sees_own_data(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, admin_id=900)
    r = c.get("/api/summary", headers={"X-Init-Data": "x"})
    assert r.status_code == 200
    data = r.json()
    assert data["viewing"] == 900
    assert data["metrics"]["readiness"]["series"][-1] == ["2026-07-01", 77]
    app.dependency_overrides.clear()


def test_non_admin_as_is_ignored(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, admin_id=111)
    r = c.get("/api/summary?as=900", headers={"X-Init-Data": "x"})
    assert r.status_code == 200
    data = r.json()
    assert data["viewing"] == 111
    assert data["metrics"]["readiness"]["series"][-1] == ["2026-07-01", 42]
    app.dependency_overrides.clear()
