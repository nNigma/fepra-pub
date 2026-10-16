"""Питание через API: разбор по фото/тексту (job), сохранение, правка, удаление, вода."""
from __future__ import annotations

import copy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import tjbot.vision as vision
from tj.services import meals as svc
from tj.services.errors import Invalid
from tjbot import access, db as botdb

from api_common import DRAFT, JPEG, env, login, make_upload, wait_job  # noqa: F401


@pytest.fixture
def ai(monkeypatch):
    """Мок ИИ: запоминает вызовы."""
    calls = {"photo": [], "text": []}
    monkeypatch.setattr(vision, "has_vision", lambda: True)

    def fake_photo(data, media_type="image/jpeg", engine="gemini", correction=None, hint=None):
        calls["photo"].append((data, correction))
        calls.setdefault("hint", []).append(hint)
        return copy.deepcopy(DRAFT)

    def fake_text(desc, engine="gemini", correction=None):
        calls["text"].append((desc, correction))
        return copy.deepcopy(DRAFT)

    monkeypatch.setattr(vision, "parse_meal", fake_photo)
    monkeypatch.setattr(vision, "parse_meal_text", fake_text)
    return calls


# --- Pro-гейт -----------------------------------------------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/meals/parse", {"text": "суп"}),
    ("post", "/api/meals", {"draft": DRAFT}),
    ("get", "/api/meals", None),
    ("put", "/api/meals/1", {"draft": DRAFT}),
    ("post", "/api/meals/1/reparse", {"correction": "ещё хлеб"}),
    ("delete", "/api/meals/1", None),
    ("post", "/api/water", {"delta_ml": 250}),
    ("get", "/api/water", None),
])
def test_pro_gate(env, method, path, body):
    c = login(10)                       # не Pro
    r = getattr(c, method)(path, **({"json": body} if body is not None else {}))
    assert r.status_code == 403


def test_pro_and_admin_pass(env, ai):
    assert login(11, pro=True).get("/api/meals").status_code == 200
    assert login(12, admin=True).get("/api/meals").status_code == 200


def test_requires_login(env):
    from fastapi.testclient import TestClient
    from tjapp.api import app
    app.dependency_overrides.clear()
    assert TestClient(app).get("/api/meals").status_code == 401


# --- разбор ---------------------------------------------------------------------------

def test_parse_text_job_and_save_with_note(env, ai):
    c = login(20, pro=True)
    r = c.post("/api/meals/parse", json={"text": "стандартный овощной суп"})
    assert r.status_code == 200
    job = wait_job(c, r.json()["job_id"])
    assert job["status"] == "done", job
    res = job["result"]
    assert res["recognized"] and res["draft"]["totals"]["kcal"] == 150
    assert res["source"]["kind"] == "text" and res["notes"] == []
    assert ai["text"] == [("стандартный овощной суп", None)]

    s = c.post("/api/meals", json={"draft": res["draft"], "day": "2026-07-11",
                                   "text": res["source"]["text"]})
    assert s.status_code == 200 and s.json()["created"]
    meal = s.json()["meal"]
    assert meal["note"] == "стандартный овощной суп" and meal["kcal"] == 150
    assert meal["quality"] == 2 and meal["day"] == "2026-07-11"
    assert meal["ts"] == "2026-07-11T12:00:00"          # не сегодня -> полдень
    got = c.get("/api/meals", params={"day": "2026-07-11"}).json()
    assert [m["id"] for m in got["meals"]] == [meal["id"]]
    assert got["totals"]["kcal"] == 150


def test_parse_photo_saves_photo_path_not_file_id(env, ai):
    c = login(21, pro=True)
    up = make_upload(env, 21)
    job = wait_job(c, c.post("/api/meals/parse", json={"upload_id": up}).json()["job_id"])
    res = job["result"]
    assert res["recognized"] and res["source"]["upload_id"] == up
    assert ai["photo"][0][0] == JPEG
    s = c.post("/api/meals", json={"draft": res["draft"], "day": "2026-07-11", "upload_id": up})
    meal = s.json()["meal"]
    assert meal["photo_url"] == f"/api/uploads/{up}"
    row = env.execute("SELECT photo_id, photo_path FROM meals WHERE id=?", (meal["id"],)).fetchone()
    assert row["photo_id"] is None and row["photo_path"].startswith("21/")


def test_parse_source_validation(env, ai):
    c = login(22, pro=True)
    assert c.post("/api/meals/parse", json={}).status_code == 400
    assert c.post("/api/meals/parse", json={"text": "  "}).status_code == 400
    # фото + текст допустимы; чужой/несуществующий файл — 404
    assert c.post("/api/meals/parse", json={"upload_id": "x", "text": "суп"}).status_code == 404
    # короткий текст: 422 в задаче, квота не списана
    job = wait_job(c, c.post("/api/meals/parse", json={"text": "аб"}).json()["job_id"])
    assert job["status"] == "error" and "коротк" in job["error"]
    assert botdb.llm_quota_used(env, 22, __import__("datetime").date.today().isoformat()) == 0


def test_parse_foreign_upload_is_404(env, ai):
    up = make_upload(env, 99)
    c = login(23, pro=True)
    assert c.post("/api/meals/parse", json={"upload_id": up}).status_code == 404


def test_correction_accumulates(env, ai):
    c = login(24, pro=True)
    r1 = wait_job(c, c.post("/api/meals/parse", json={"text": "суп дня"}).json()["job_id"])["result"]
    r2 = wait_job(c, c.post("/api/meals/parse", json={
        "text": "суп дня", "correction": "без сливок", "notes": r1["notes"]}).json()["job_id"])["result"]
    r3 = wait_job(c, c.post("/api/meals/parse", json={
        "text": "суп дня", "correction": "порция 400 г", "notes": r2["notes"]}).json()["job_id"])["result"]
    assert r3["notes"] == ["без сливок", "порция 400 г"]
    assert ai["text"][-1] == ("суп дня", "без сливок; порция 400 г")


def test_quota_blocks_non_admin_not_admin(env, ai):
    c = login(25, pro=True)
    from datetime import date
    day = date.today().isoformat()
    for _ in range(access.LLM_DAILY_LIMIT - 1):
        botdb.llm_quota_bump(env, 25, day)
    ok = wait_job(c, c.post("/api/meals/parse", json={"text": "суп дня"}).json()["job_id"])
    assert ok["result"]["recognized"]
    blocked = wait_job(c, c.post("/api/meals/parse", json={"text": "суп дня"}).json()["job_id"])
    assert blocked["result"] == {"recognized": False, "reason": "quota", "draft": None,
                                 "notes": [], "source": blocked["result"]["source"]}
    adm = login(26, admin=True)
    for _ in range(3):
        assert wait_job(adm, adm.post("/api/meals/parse", json={"text": "суп дня"}
                                      ).json()["job_id"])["result"]["recognized"]


def test_not_recognized(env, monkeypatch):
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    monkeypatch.setattr(vision, "parse_meal_text", lambda *a, **k: None)
    c = login(27, pro=True)
    res = wait_job(c, c.post("/api/meals/parse", json={"text": "что-то"}).json()["job_id"])["result"]
    assert res["recognized"] is False and res["reason"] == "not_recognized"


def test_no_vision_on_photo(env, monkeypatch):
    monkeypatch.setattr(vision, "has_vision", lambda: False)
    c = login(28, pro=True)
    up = make_upload(env, 28)
    res = wait_job(c, c.post("/api/meals/parse", json={"upload_id": up}).json()["job_id"])["result"]
    assert res["reason"] == "no_vision"


# --- сохранение и идемпотентность -------------------------------------------------------

def test_save_idempotent_by_uuid(env, ai):
    c = login(30, pro=True)
    u = "5b1f0e5e-0000-4000-8000-000000000001"
    body = {"draft": DRAFT, "day": "2026-07-11", "uuid": u}
    a = c.post("/api/meals", json=body).json()
    b = c.post("/api/meals", json=body).json()
    assert a["created"] is True and b["created"] is False
    assert a["meal"]["id"] == b["meal"]["id"] and a["meal"]["uuid"] == u
    assert len(c.get("/api/meals", params={"day": "2026-07-11"}).json()["meals"]) == 1
    # без uuid — обычная запись, дубль допустим (два приёма)
    c.post("/api/meals", json={"draft": DRAFT, "day": "2026-07-11"})
    c.post("/api/meals", json={"draft": DRAFT, "day": "2026-07-11"})
    assert len(c.get("/api/meals", params={"day": "2026-07-11"}).json()["meals"]) == 3


def test_same_uuid_other_user_is_independent(env, ai):
    u = "5b1f0e5e-0000-4000-8000-000000000002"
    a = login(31, pro=True).post("/api/meals", json={"draft": DRAFT, "day": "2026-07-11", "uuid": u})
    b = login(32, pro=True).post("/api/meals", json={"draft": DRAFT, "day": "2026-07-11", "uuid": u})
    assert a.json()["created"] and b.json()["created"]


def test_save_validation(env, ai):
    c = login(33, pro=True)
    assert c.post("/api/meals", json={"draft": {"foods": []}}).status_code == 422
    assert c.post("/api/meals", json={"draft": DRAFT, "day": "вчера"}).status_code == 422
    assert c.post("/api/meals", json={"draft": DRAFT, "day": "2999-01-01"}).status_code == 422
    assert c.post("/api/meals", json={"draft": DRAFT, "uuid": "nope"}).status_code == 422
    assert c.post("/api/meals", json={"draft": DRAFT, "upload_id": "nope"}).status_code == 404


def test_save_recomputes_totals(env, ai):
    c = login(34, pro=True)
    bad = copy.deepcopy(DRAFT)
    bad["totals"] = {"kcal": 1, "protein_g": 0, "fat_g": 0, "carb_g": 0}
    m = c.post("/api/meals", json={"draft": bad, "day": "2026-07-11"}).json()["meal"]
    assert m["kcal"] == 150


def test_meal_ts_today_uses_user_tz():
    now = datetime(2026, 7, 11, 22, 30, tzinfo=ZoneInfo("UTC"))
    assert svc.meal_ts("2026-07-12", "Europe/Moscow", now) == "2026-07-12T01:30:00+03:00"
    assert svc.meal_ts("2026-07-11", "Europe/Moscow", now) == "2026-07-11T12:00:00"
    assert svc.check_day(None, "Europe/Moscow", now) == "2026-07-12"
    with pytest.raises(Invalid):
        svc.check_day("2026-07-20", "UTC", now)


# --- правка / перепарс / удаление ------------------------------------------------------------

def _saved(c, **kw):
    return c.post("/api/meals", json={"draft": DRAFT, "day": "2026-07-11", **kw}).json()["meal"]


def test_replace_keeps_id_and_is_idempotent(env, ai):
    c = login(40, pro=True)
    up = make_upload(env, 40)
    m = _saved(c, upload_id=up, text="суп", uuid="5b1f0e5e-0000-4000-8000-000000000003")
    new = copy.deepcopy(DRAFT)
    new["foods"][0]["kcal"] = 400
    new["totals"]["kcal"] = 400
    r1 = c.put(f"/api/meals/{m['id']}", json={"draft": new}).json()
    r2 = c.put(f"/api/meals/{m['id']}", json={"draft": new}).json()
    assert r1 == r2
    assert r1["id"] == m["id"] and r1["kcal"] == 400 and r1["uuid"] == m["uuid"]
    assert r1["photo_url"] == m["photo_url"] and r1["note"] == "суп" and r1["ts"] == m["ts"]
    assert len(c.get("/api/meals", params={"day": "2026-07-11"}).json()["meals"]) == 1
    moved = c.put(f"/api/meals/{m['id']}", json={"draft": new, "day": "2026-07-10"}).json()
    assert moved["day"] == "2026-07-10" and moved["ts"] == "2026-07-10T12:00:00"


def test_replace_atomic_on_bad_draft(env, ai):
    c = login(41, pro=True)
    m = _saved(c)
    assert c.put(f"/api/meals/{m['id']}", json={"draft": {"foods": []}}).status_code == 422
    assert c.get("/api/meals", params={"day": "2026-07-11"}).json()["meals"][0]["kcal"] == 150


def test_foreign_meal_is_404(env, ai):
    m = _saved(login(42, pro=True))
    c = login(43, pro=True)
    assert c.put(f"/api/meals/{m['id']}", json={"draft": DRAFT}).status_code == 404
    assert c.delete(f"/api/meals/{m['id']}").status_code == 404
    assert c.post(f"/api/meals/{m['id']}/reparse", json={"correction": "хлеб"}).status_code == 404
    assert c.get("/api/meals", params={"day": "2026-07-11"}).json()["meals"] == []
    assert login(42, pro=True).get("/api/meals", params={"day": "2026-07-11"}).json()["meals"]


def test_delete(env, ai):
    c = login(44, pro=True)
    m = _saved(c)
    assert c.delete(f"/api/meals/{m['id']}").json() == {"ok": True}
    assert c.delete(f"/api/meals/{m['id']}").status_code == 404


def test_reparse_by_saved_file(env, ai):
    c = login(45, pro=True)
    up = make_upload(env, 45)
    m = _saved(c, upload_id=up)
    res = wait_job(c, c.post(f"/api/meals/{m['id']}/reparse",
                             json={"correction": "порция больше"}).json()["job_id"])["result"]
    assert res["recognized"] and res["source"]["kind"] == "photo" and res["source"]["meal_id"] == m["id"]
    assert ai["photo"][-1] == (JPEG, "порция больше")
    # мягко удалённая загрузка: файл на диске есть, перепарс по нему всё ещё работает
    env.execute("UPDATE uploads SET deleted_at='x' WHERE id=?", (up,))
    env.commit()
    res = wait_job(c, c.post(f"/api/meals/{m['id']}/reparse",
                             json={"correction": "ещё"}).json()["job_id"])["result"]
    assert res["recognized"] and res["source"]["kind"] == "photo"


def test_reparse_by_saved_text(env, ai):
    c = login(46, pro=True)
    m = _saved(c, text="стандартный овощной суп")
    res = wait_job(c, c.post(f"/api/meals/{m['id']}/reparse",
                             json={"correction": "со сливками"}).json()["job_id"])["result"]
    assert res["source"]["kind"] == "text"
    assert ai["text"][-1] == ("стандартный овощной суп", "со сливками")


def test_reparse_nothing_to_reparse(env, ai):
    c = login(47, pro=True)
    m = _saved(c)                                   # ни фото, ни описания (как из Telegram)
    job = wait_job(c, c.post(f"/api/meals/{m['id']}/reparse", json={"correction": "хлеб"}).json()["job_id"])
    assert job["status"] == "error" and "нечего перепарсить" in job["error"]


def test_telegram_meal_with_only_photo_id_not_reparsable(env, ai):
    c = login(48, pro=True)
    mid = botdb.add_meal(env, 48, "2026-07-11", "2026-07-11T12:00:00", DRAFT["foods"],
                         DRAFT["totals"], photo_id="tg-file-id")
    job = wait_job(c, c.post(f"/api/meals/{mid}/reparse", json={"correction": "хлеб"}).json()["job_id"])
    assert job["status"] == "error"
    listed = c.get("/api/meals", params={"day": "2026-07-11"}).json()["meals"][0]
    assert "photo_id" not in listed and "photo_path" not in listed and listed["photo_url"] is None


# --- вода ---------------------------------------------------------------------------------

def test_water(env, ai):
    c = login(50, pro=True)
    assert c.post("/api/water", json={"delta_ml": 250, "day": "2026-07-11"}).json() == {
        "day": "2026-07-11", "water_l": 0.25, "water_ml": 250}
    c.post("/api/water", json={"delta_ml": 500, "day": "2026-07-11"})
    assert c.get("/api/water", params={"day": "2026-07-11"}).json()["water_ml"] == 750
    assert c.post("/api/water", json={"delta_ml": -2000, "day": "2026-07-11"}).json()["water_ml"] == 0
    assert c.get("/api/meals", params={"day": "2026-07-11"}).json()["water_ml"] == 0
    for bad in (0, 6000, -6000):
        assert c.post("/api/water", json={"delta_ml": bad}).status_code == 422
    assert c.post("/api/water", json={"delta_ml": "много"}).status_code == 422
    assert login(51, pro=True).get("/api/water", params={"day": "2026-07-11"}).json()["water_ml"] == 0


def test_migration_0050_idempotent(env):
    import importlib
    mod = importlib.import_module("tj.migrations.0051_meals_api")
    mod.upgrade(env)
    mod.upgrade(env)
    cols = {r[1] for r in env.execute("PRAGMA table_info(meals)")}
    assert {"photo_path", "client_uuid"} <= cols


def test_photo_with_text_description_reaches_the_model(env, ai):
    c = login(23, pro=True)
    up = make_upload(env, 23)
    r = wait_job(c, c.post("/api/meals/parse", json={"upload_id": up, "text": "борщ со сметаной"}).json()["job_id"])["result"]
    assert r["recognized"] and r["source"]["kind"] == "photo" and r["source"]["text"] == "борщ со сметаной"
    assert ai["hint"] == ["борщ со сметаной"] and len(ai["photo"]) == 1 and not ai["text"]
    s = c.post("/api/meals", json={"draft": r["draft"], "upload_id": up, "text": "борщ со сметаной"}).json()["meal"]
    assert s["photo_url"] and s["note"] == "борщ со сметаной"
    # перепарс сохранённого фото тоже помнит описание
    r2 = wait_job(c, c.post(f"/api/meals/{s['id']}/reparse", json={"correction": "порция 400 г"}).json()["job_id"])["result"]
    assert r2["recognized"] and ai["hint"][-1] == "борщ со сметаной"


def test_day_has_targets_and_micro_norms(env, ai):
    c = login(24, pro=True)
    d = c.get("/api/meals").json()
    assert d["micro_targets"]["fiber_g"] == 30 and "sodium_mg" in d["micro_limit"]
    assert "targets" in d and "burned" in d and d["water_target_l"] >= 2.2
    env.execute("INSERT OR REPLACE INTO users (tg_id, sex, age, height_cm, weight_kg) VALUES (24,'m',30,180,80)")
    env.commit()
    t = c.get("/api/meals").json()["targets"]
    assert t and t["kcal"] > 1500 and t["protein_g"] == round(80 * 1.8)
