"""/api/nutrition отдаёт нормы, burned и цель воды."""
from __future__ import annotations

import json
from fastapi.testclient import TestClient
from tjbot import db as botdb
from tjapp import api
from tjapp.api import app, require_auth


def _setup(tmp_path, monkeypatch):
    dbp = tmp_path / "t.db"
    con = botdb.connect(dbp)
    botdb.init_schema(con)
    botdb.save_user(con, 1, nick="ник", height_cm=183, weight_kg=78,
                    sex="m", gym="дом", age=36)
    botdb.set_goal(con, 1, "recomp")
    con.execute(
        'INSERT INTO activities ("tg_id","day","sport","activity_id","source",'
        '"calories","extra") VALUES (?,?,?,?,?,?,?)',
        (1, "2026-07-08", "wod", "a1", "test", 500,
         json.dumps({"sweat_loss_ml": 700})))
    con.commit()
    botdb.add_meal(con, 1, "2026-07-08", "2026-07-08T12:00:00",
                   [], {"kcal": 900, "protein_g": 50, "fat_g": 20, "carb_g": 100})
    con.close()
    monkeypatch.setattr(api, "_db", lambda: str(dbp))
    monkeypatch.setattr(api, "is_pro", lambda tg: True)
    app.dependency_overrides[require_auth] = lambda: {"id": 1}
    return TestClient(app)


def test_nutrition_targets(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch)
    con = botdb.connect(tmp_path / "t.db")
    botdb.add_meal(con, 1, "2026-07-08", "2026-07-08T19:00:00",
                   [], {"kcal": 400, "protein_g": 20, "fat_g": 10, "carb_g": 40},
                   quality=4)
    con.close()
    r = c.get("/api/nutrition?day=2026-07-08")
    assert r.status_code == 200
    d = r.json()
    assert d["targets"]["protein_g"] == 172
    assert d["burned"] == 500
    assert d["water_target_l"] == 2.9
    assert d["goal"] == "recomp"
    assert d["day_verdict"] == 4
    app.dependency_overrides.clear()


def test_nutrition_targets_absent_without_profile(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch)
    con = botdb.connect(tmp_path / "t.db")
    con.execute('UPDATE users SET "age"=NULL WHERE "tg_id"=1')
    con.commit()
    con.close()
    r = c.get("/api/nutrition?day=2026-07-08")
    assert r.status_code == 200
    d = r.json()
    assert d["targets"] is None
    assert d["meals"] and d["totals"]["kcal"] == 900
    app.dependency_overrides.clear()


def test_nutrition_days_has_targets(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch)
    con = botdb.connect(tmp_path / "t.db")
    botdb.add_meal(con, 1, "2026-07-08", "2026-07-08T19:00:00",
                   [], {"kcal": 400, "protein_g": 20, "fat_g": 10, "carb_g": 40},
                   quality=4)
    con.close()
    r = c.get("/api/nutrition/days")
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d["targets"], dict) and "kcal" in d["targets"]
    assert d["goal"] == "recomp"
    day = next(x for x in d["days"] if x["day"] == "2026-07-08")
    assert day["verdict"] == 4
    app.dependency_overrides.clear()
