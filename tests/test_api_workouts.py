"""Роуты записи тренировки (TestClient, FEPRA_DB_PATH; vision/LLM замоканы)."""
from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from svc_common import BOARD
from tj.services import uploads
from tjapp.api import app
from tjapp.deps import require_user
from tjapp.routes import ALL_ROUTERS
from tjbot import access, vision
from tjbot import db as botdb

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
SNATCH_BOARD = "2 ТА.\n- Е2МОМх3х3х80%\nрывок\n\n3 WOD\n3 сета:\n- 20 бёрпи"
ME, OTHER = 301, 302
DAY = "2026-09-01"


@pytest.fixture
def env(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    monkeypatch.setenv("FEPRA_UPLOADS_DIR", str(tmp_path / "up"))
    con = botdb.connect(p)
    botdb.init_schema(con)
    calls = {"text": [], "board": []}
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    monkeypatch.setattr(vision, "has_claude", lambda: False)
    monkeypatch.setattr(vision, "enrich_aliases", lambda c, t, use_llm=True: botdb.load_aliases(c))
    monkeypatch.setattr(vision, "parse_text", lambda t, use_llm=True: calls["text"].append(use_llm)
                        or {"raw_text": t.strip(), "format": "other", "movements": []})

    def parse_board(data, media_type="image/jpeg", engine="gemini"):
        calls["board"].append(engine)
        return {"raw_text": SNATCH_BOARD, "format": "other", "engine_used": engine}

    monkeypatch.setattr(vision, "parse_board", parse_board)
    monkeypatch.setattr(vision, "parse_lifts", lambda t, use_llm=True: None)
    who = {"id": ME}
    app.dependency_overrides[require_user] = lambda: {"id": who["id"]}
    c = TestClient(app)
    c.who, c.calls, c.con = who, calls, con
    yield c
    app.dependency_overrides.clear()
    con.close()


def _job(c, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.02)
    raise AssertionError("job не завершился")


def _upload(c, data=JPEG, kind="board", ctype="image/jpeg"):
    return c.post("/api/uploads", files={"file": ("доска.jpg", data, ctype)}, data={"kind": kind})


def _uuid():
    return str(uuid.uuid4())


def _fill(form, mapping):
    fields = [f for b in form["blocks"] for f in b["fields"]]
    out = {}
    for spec, val in mapping.items():
        needle, _, nth = spec.partition("#")
        out[[f for f in fields if needle in f["label"]][int(nth or 0)]["key"]] = val
    return out


def test_routers_registered():
    paths = {(m, r.path) for rt in ALL_ROUTERS for r in rt.routes for m in r.methods}
    assert {("POST", "/api/uploads"), ("GET", "/api/uploads/{upload_id}"), ("POST", "/api/board/parse"),
            ("PUT", "/api/workouts/{activity_id}"), ("GET", "/api/workouts/recent"),
            ("PATCH", "/api/workouts/{activity_id}"), ("DELETE", "/api/workouts/{activity_id}"),
            ("POST", "/api/workouts/{activity_id}/restore"),
            ("POST", "/api/workouts/{activity_id}/lifts/resolve"),
            ("POST", "/api/workouts/{activity_id}/maxes"), ("GET", "/api/goals/items"),
            ("POST", "/api/goals/items"), ("POST", "/api/pm"), ("POST", "/api/bodyweight"),
            ("POST", "/api/feel"), ("GET", "/api/gym-program")} <= paths


def test_auth_required(env):
    app.dependency_overrides.clear()
    c = TestClient(app)
    for m, u in (("get", "/api/workouts/recent"), ("post", "/api/uploads"), ("post", "/api/pm"),
                 ("get", "/api/goals/items"), ("get", "/api/gym-program"),
                 ("put", f"/api/workouts/{_uuid()}")):
        assert getattr(c, m)(u).status_code == 401, u


# --- полный сценарий ------------------------------------------------------------------------

def test_full_scenario_photo_to_resolved_lift(env):
    c = env
    up = _upload(c)
    assert up.status_code == 200, up.text
    up = up.json()
    assert up["mime"] == "image/jpeg" and up["url"] == f"/api/uploads/{up['id']}"
    assert c.get(up["url"]).content == JPEG

    r = c.post("/api/board/parse", json={"upload_id": up["id"], "sport": "weightlifting", "engine": "slow"})
    assert r.status_code == 200, r.text
    job = _job(c, r.json()["job_id"])
    assert job["status"] == "done", job
    res = job["result"]
    assert res["recognized"] and res["engine_used"] == "claude" and c.calls["board"] == ["claude"]
    form = res["form"]
    assert [b["kind"] for b in form["blocks"]] == ["strength", "metcon"]

    wid = _uuid()
    put = c.put(f"/api/workouts/{wid}", json={
        "day": DAY, "sport": "weightlifting", "rpe": 8, "bodyweight": 80,
        "board": {"text": res["board_text"], "source": "own", "blocks": res["blocks"]},
        "form_result": _fill(form, {"раунд 1": "70x3", "раунд 3": "80x3", "время": "6:00"})})
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["created"] and body["rpe"] == 8 and body["score"] == "6:00"
    assert body["credited"] == [] and len(body["ambiguous"]) == 1
    q = body["ambiguous"][0]
    assert q["family"] == "snatch" and q["weight"] == 80

    rr = c.post(f"/api/workouts/{wid}/lifts/resolve", json={
        "movement": q["movement"], "variant": q["variants"][1]["id"], "weight": q["weight"], "reps": q["reps"]})
    assert rr.status_code == 200 and rr.json()["discipline"] == "power_snatch"
    # повторный PUT — идемпотентен и ничего не переспрашивает
    again = c.put(f"/api/workouts/{wid}", json={
        "day": DAY, "sport": "weightlifting",
        "board": {"text": res["board_text"], "source": "own", "blocks": res["blocks"]},
        "form_result": _fill(form, {"раунд 1": "70x3", "раунд 3": "80x3"})}).json()
    assert not again["created"] and again["ambiguous"] == []
    assert [x["discipline"] for x in again["credited"]] == ["power_snatch"]

    got = c.get(f"/api/workouts/{wid}").json()
    assert got["editable"] and got["board_editable"] and got["form"] and got["bodyweight"] == 80
    assert got["maxes"][0]["discipline"] == "power_snatch"
    mx = c.post(f"/api/workouts/{wid}/maxes", json={"maxes": [
        {"movement": "становая тяга", "weight_kg": 150, "reps": 3}]})
    assert mx.status_code == 200 and mx.json()["credited"][0]["discipline"] == "deadlift"
    pa = c.patch(f"/api/workouts/{wid}", json={"rpe": 9, "scaling": "scaled"})
    assert pa.status_code == 200 and pa.json()["workout"]["rpe"] == 9

    assert c.delete(f"/api/workouts/{wid}").status_code == 200
    assert c.get(f"/api/workouts/{wid}").status_code == 404
    assert c.post(f"/api/workouts/{wid}/restore").json()["id"] == wid
    assert c.get("/api/workouts/recent").json()[0]["id"] == wid


def test_parse_text_job_and_validation(env):
    c = env
    r = c.post("/api/board/parse", json={"text": BOARD, "sport": "hyrox"})
    job = _job(c, r.json()["job_id"])
    assert job["result"]["recognized"] and len(job["result"]["form"]["blocks"]) == 4
    assert c.calls["text"] == [True]
    job = _job(c, c.post("/api/board/parse", json={"text": BOARD, "verbatim": True}).json()["job_id"])
    assert job["status"] == "done" and c.calls["text"] == [True]         # verbatim: без ИИ
    assert c.post("/api/board/parse", json={"text": "x", "sport": "curling"}).status_code == 422
    assert c.post("/api/board/parse", json={"text": "x", "sport": "run"}).status_code == 422
    assert c.post("/api/board/parse", json={"text": "x", "engine": "warp"}).status_code == 422
    assert c.post("/api/board/parse", json={}).status_code == 400
    assert c.post("/api/board/parse", json={"text": "x", "upload_id": _uuid()}).status_code == 400
    assert c.post("/api/board/parse", json={"upload_id": _uuid()}).status_code == 404


def test_parse_llm_quota_in_job(env):
    c = env
    up = _upload(c).json()
    for _ in range(access.LLM_DAILY_LIMIT):
        assert _job(c, c.post("/api/board/parse", json={"upload_id": up["id"]}).json()["job_id"]
                    )["result"]["recognized"]
    job = _job(c, c.post("/api/board/parse", json={"upload_id": up["id"]}).json()["job_id"])
    assert job["status"] == "done" and job["result"]["recognized"] is False
    assert job["result"]["reason"] == "quota"


# --- несколько тренировок, чужие данные --------------------------------------------------------

def test_several_workouts_same_day_incl_two_weightlifting(env):
    c = env
    ids = [_uuid() for _ in range(3)]
    for wid, sport, t in zip(ids, ("weightlifting", "weightlifting", "run"), ("09:00", "18:00", "07:00")):
        r = c.put(f"/api/workouts/{wid}", json={"day": DAY, "sport": sport, "start_time": t,
                                                "board": {"text": "ТА", "source": "own"}} if sport != "run"
                  else {"day": DAY, "sport": "run", "start_time": t, "duration_min": 30, "distance_km": 5})
        assert r.status_code == 200, r.text
    rec = c.get("/api/workouts/recent").json()
    assert {w["id"] for w in rec} == set(ids) and {w["day"] for w in rec} == {DAY}
    assert [w["sport"] for w in rec].count("weightlifting") == 2


def test_foreign_data_is_hidden(env):
    c = env
    wid = _uuid()
    assert c.put(f"/api/workouts/{wid}", json={"day": DAY, "sport": "run"}).status_code == 200
    up = _upload(c).json()
    goal = c.post("/api/goals/items", json={"kind": "numeric", "discipline": "back_squat",
                                            "target": 140}).json()
    c.who["id"] = OTHER
    for r in (c.get(f"/api/workouts/{wid}"), c.delete(f"/api/workouts/{wid}"),
              c.patch(f"/api/workouts/{wid}", json={"rpe": 3}), c.post(f"/api/workouts/{wid}/restore"),
              c.post(f"/api/workouts/{wid}/maxes", json={"text": "Присед 100"}),
              c.get(up["url"]), c.post("/api/goals/items/%d/archive" % goal["id"]),
              c.post("/api/goals/items/%d/complete" % goal["id"]), c.delete("/api/goals/items/%d" % goal["id"]),
              c.get(f"/api/jobs/{_uuid()}")):
        assert r.status_code == 404, (r.request.url, r.text)
    assert c.post("/api/board/parse", json={"upload_id": up["id"]}).status_code == 404
    assert c.get("/api/workouts/recent").json() == [] and c.get("/api/goals/items").json() == []
    c.who["id"] = ME
    assert c.get(f"/api/workouts/{wid}").status_code == 200
    assert c.get("/api/goals/items").json()[0]["status"] == "active"


def test_admin_can_read_foreign_upload_and_job_owner_only(env, monkeypatch):
    c = env
    up = _upload(c).json()
    jid = c.post("/api/board/parse", json={"text": BOARD}).json()["job_id"]
    _job(c, jid)
    c.who["id"] = OTHER
    monkeypatch.setattr(access, "is_admin", lambda tg, path=None: tg == OTHER)
    assert c.get(up["url"]).content == JPEG
    assert c.get(f"/api/jobs/{jid}").status_code == 404      # задачи — только владельцу


def test_gym_board_rules_over_http(env):
    c = env
    botdb.add_program(c.con, DAY, "Universe", "3 WOD\n3 сета:\n- 20 бёрпи", confirmed=1)
    gp = c.get("/api/gym-program", params={"day": DAY}).json()
    assert gp["found"] and gp["board_text"].startswith("3 WOD") and gp["form"]["blocks"]
    assert c.get("/api/gym-program", params={"day": "2026-01-01"}).json() == {"found": False, "day": "2026-01-01"}
    assert c.get("/api/gym-program", params={"day": "вчера"}).status_code == 422
    assert c.get("/api/gym-program").json()["found"] is False      # день по умолчанию — сегодня
    wid = _uuid()
    r = c.put(f"/api/workouts/{wid}", json={"day": DAY, "sport": "crossfit",
                                            "board": {"text": "подделка", "source": "gym"}})
    assert r.status_code == 200 and r.json()["board_source"] == "gym"
    assert c.patch(f"/api/workouts/{wid}", json={"board": {"text": "моя"}}).status_code == 403
    assert c.get(f"/api/workouts/{wid}").json()["board_editable"] is False
    r = c.put(f"/api/workouts/{_uuid()}", json={"day": "2026-01-01", "sport": "crossfit",
                                                "board": {"source": "gym"}})
    assert r.status_code == 422


def test_workout_validation_codes(env):
    c = env
    assert c.put("/api/workouts/not-a-uuid", json={"day": DAY, "sport": "run"}).status_code == 400
    assert c.put(f"/api/workouts/{_uuid()}", json={"day": DAY, "sport": "curling"}).status_code == 422
    assert c.put(f"/api/workouts/{_uuid()}", json={"day": DAY, "sport": "run", "rpe": 12}).status_code == 422
    assert c.patch(f"/api/workouts/{_uuid()}", json={"rpe": 3}).status_code == 404
    wid = _uuid()
    c.put(f"/api/workouts/{wid}", json={"day": DAY, "sport": "run"})
    assert c.patch(f"/api/workouts/{wid}", json={}).status_code == 422
    assert c.post(f"/api/workouts/{wid}/lifts/resolve", json={
        "movement": "x", "variant": "back_squat", "weight": 80, "reps": 1}).status_code == 422
    assert c.post(f"/api/workouts/{wid}/lifts/resolve", json={"movement": "x"}).status_code == 422


# --- загрузки: типы и лимиты ----------------------------------------------------------------

def test_upload_limits_and_types(env):
    c = env
    assert _upload(c, b"<html>", ctype="image/jpeg").status_code == 422          # content-type не решает
    assert _upload(c, JPEG, ctype="text/plain").status_code == 200               # решает сигнатура
    assert _upload(c, b"").status_code == 422
    big = JPEG + b"\x00" * uploads.MAX_BYTES
    r = _upload(c, big)
    assert r.status_code == 422 and "10 МБ" in r.json()["detail"]
    ok = JPEG + b"\x00" * (uploads.MAX_BYTES - len(JPEG))
    assert _upload(c, ok).status_code == 200
    assert _upload(c, JPEG, kind="virus").status_code == 422
    assert c.post("/api/uploads").status_code == 422                              # нет файла
    assert c.get(f"/api/uploads/{_uuid()}").status_code == 404
    assert c.get("/api/uploads/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_upload_content_length_checked_before_reading(env):
    c = env
    r = c.post("/api/uploads", content=b"x", headers={
        "content-type": "multipart/form-data; boundary=b", "content-length": str(uploads.MAX_BYTES * 2)})
    assert r.status_code == 422


# --- цели, ПМ, вес, самочувствие -----------------------------------------------------------------

def test_goals_pm_bodyweight_feel(env):
    c = env
    g = c.post("/api/goals/items", json={"kind": "numeric", "discipline": "back_squat", "target": "140"})
    assert g.status_code == 200 and g.json()["status"] == "active"
    assert c.post("/api/goals/items", json={"kind": "numeric", "discipline": "nope", "target": 1}).status_code == 422
    assert c.post("/api/goals/items", json={"kind": "weird", "discipline": "back_squat", "target": 1}).status_code == 422
    assert c.post(f"/api/goals/items/{g.json()['id']}/complete").json()["status"] == "done"
    g2 = c.post("/api/goals/items", json={"kind": "numeric", "discipline": "deadlift", "target": 180}).json()
    assert c.delete(f"/api/goals/items/{g2['id']}").json()["status"] == "archived"
    assert c.get("/api/goals/items").json() == []
    assert "/api/goals" not in {r.path for rt in ALL_ROUTERS for r in rt.routes}   # старый экран не перекрыт

    pm = c.post("/api/pm", json={"discipline": "back_squat", "value": "100x3"})
    assert pm.status_code == 200 and pm.json()["reps"] == 3 and pm.json()["est_1rm"] == 110.0
    assert c.post("/api/pm", json={"discipline": "back_squat", "value": "abc"}).status_code == 422
    bw = c.post("/api/bodyweight", json={"kg": 79.5, "day": DAY})
    assert bw.json() == {"day": DAY, "kg": 79.5}
    assert c.post("/api/bodyweight", json={"kg": 3}).status_code == 422
    assert c.post("/api/bodyweight", json={"kg": "abc"}).status_code == 422
    fe = c.post("/api/feel", json={"score": 8})
    assert fe.status_code == 200 and fe.json()["score"] == 8
    assert c.post("/api/feel", json={"score": 11}).status_code == 422
