from fastapi.testclient import TestClient
import tjapp.api as api
from tjbot import db as botdb


def _setup(tmp_path, monkeypatch, me):
    dbp = tmp_path / "t.db"; con = botdb.connect(dbp); botdb.init_schema(con); botdb.seed_standards(con)
    botdb.save_user(con, 1, nick="A", height_cm=175, weight_kg=80, sex="m", age=30, gym="Universe")
    botdb.save_user(con, 2, nick="B", height_cm=175, weight_kg=80, sex="m", age=30, gym="Universe")
    botdb.add_result(con, tg_id=1, discipline="back_squat", value=160, source="manual", day="2026-07-01", reps=1, est_1rm=160)
    con.close()
    monkeypatch.setattr(api, "_db", lambda: str(dbp))
    api.app.dependency_overrides[api.require_auth] = lambda: {"id": me}
    return TestClient(api.app)


def test_leaderboard_overall(monkeypatch, tmp_path):
    c = _setup(tmp_path, monkeypatch, me=2)
    r = c.get("/api/leaderboard?metric=overall", headers={"X-Init-Data": "x"})
    assert r.status_code == 200
    body = r.json()
    assert body["rows"][0]["tg_id"] == 1 and body["rows"][0]["place"] == 1
    assert any(row["is_me"] and row["tg_id"] == 2 for row in body["rows"])
    api.app.dependency_overrides.clear()
