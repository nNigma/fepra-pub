"""nutrition_week в /api/summary: окно без сегодня, Pro-гейт."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from tj.models import DailyMetrics
from tjbot import db as botdb
from tjapp import api
from tjapp.api import app, require_auth


def _setup(tmp_path, monkeypatch, pro=True):
    dbp = tmp_path / "t.db"
    con = botdb.connect(dbp)
    botdb.init_schema(con)
    botdb.save_user(con, 1, nick="ник", height_cm=183, weight_kg=78, sex="m",
                    age=36, gym="U")
    botdb.insert_daily(con, DailyMetrics(day=date.today(), readiness=50),
                       tg_id=1)
    yday = (date.today() - timedelta(days=1)).isoformat()
    botdb.add_meal(con, 1, yday, yday + "T12:00:00", [],
                   {"kcal": 900, "protein_g": 50, "fat_g": 20, "carb_g": 100})
    today = date.today().isoformat()
    botdb.add_meal(con, 1, today, today + "T12:00:00", [],
                   {"kcal": 500, "protein_g": 30, "fat_g": 10, "carb_g": 50})
    con.close()
    monkeypatch.setattr(api, "_db", lambda: str(dbp))
    monkeypatch.setattr(api, "is_pro", lambda tg: pro)
    app.dependency_overrides[require_auth] = lambda: {"id": 1}
    return TestClient(app)


def test_summary_has_nutrition_week_without_today(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch)
    d = c.get("/api/summary", headers={"X-Init-Data": "x"}).json()
    nw = d["nutrition_week"]
    assert nw["days_recorded"] == 1
    assert nw["kcal"]["sum"] == 900
    assert nw["metrics"]["kcal"]["series"] == [
        [(date.today() - timedelta(days=1)).isoformat(), 900]]
    assert nw["kcal"]["target_week"] > 0
    assert nw["metrics"]["fiber_g"]["target_week"] == 210
    app.dependency_overrides.clear()


def test_summary_nutrition_week_not_for_free(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=False)
    monkeypatch.setattr(api, "is_admin", lambda tg: False)
    d = c.get("/api/summary", headers={"X-Init-Data": "x"}).json()
    assert d["nutrition_week"] is None
    app.dependency_overrides.clear()


def test_summary_nutrition_week_for_admin_without_pro(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=False)
    monkeypatch.setattr(api, "is_admin", lambda tg: True)
    d = c.get("/api/summary", headers={"X-Init-Data": "x"}).json()
    assert d["nutrition_week"] is not None
    assert d["nutrition_week"]["days_recorded"] == 1
    app.dependency_overrides.clear()
