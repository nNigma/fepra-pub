"""Роуты программ: полный сценарий, права, ошибки."""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from tj.services import auth
from tj.services import program_engine as eng
from tjapp.api import app
from tjapp.routes import ALL_ROUTERS, auth as auth_routes
from tjbot import db as botdb

D = "2026-09-28"


@pytest.fixture
def env(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    con = botdb.connect(p)
    botdb.init_schema(con)
    auth_routes.redeem_limiter.reset()
    auth_routes.login_limiter.reset()
    yield con
    con.close()
    app.dependency_overrides.clear()


def _login(con, role="user", nick="A", sex="m", bw=80):
    tok = auth.create_invite(con, None, role)
    c = TestClient(app)
    r = c.post("/api/auth/redeem", json={"token": tok, "nick": nick})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    botdb.set_sex(con, uid, sex)
    botdb.set_weight(con, uid, bw)
    return c, uid


def _sets(sess):
    return [s for b in sess["blocks"] for ex in b["exercises"] for s in ex["sets"]]


def test_routes_registered():
    paths = {(m, r.path) for rt in ALL_ROUTERS for r in rt.routes for m in getattr(r, "methods", [])}
    for m, p in [("GET", "/api/programs/tree"), ("GET", "/api/programs/{slug}"),
                 ("POST", "/api/programs/{slug}/enroll"), ("GET", "/api/enrollments"),
                 ("GET", "/api/enrollments/{enrollment_id}"), ("GET", "/api/enrollments/{enrollment_id}/today"),
                 ("POST", "/api/enrollments/{enrollment_id}/refresh-base"), ("GET", "/api/sessions/{session_id}"),
                 ("PUT", "/api/sessions/{session_id}/sets/{set_id}"), ("POST", "/api/sessions/{session_id}/checkin"),
                 ("POST", "/api/sessions/{session_id}/finish"), ("GET", "/api/lifts/{lift}/trend"),
                 ("POST", "/api/programs/enrollments/{enrollment_id}/pause"),
                 ("POST", "/api/programs/enrollments/{enrollment_id}/resume"),
                 ("POST", "/api/programs/enrollments/{enrollment_id}/cancel")]:
        assert (m, p) in paths, (m, p)


def test_requires_login(env):
    c = TestClient(app)
    for m, url in [("get", "/api/programs/tree"), ("get", "/api/enrollments"), ("get", "/api/sessions/x"),
                   ("get", "/api/lifts/squat_snatch/trend"), ("post", "/api/programs/bulgarian-peak-8w/enroll")]:
        assert getattr(c, m)(url).status_code == 401, url


def test_full_scenario(env):
    c, uid = _login(env)
    # 1. дерево
    tree = c.get("/api/programs/tree").json()["tree"]
    assert [n["slug"] for n in tree] == ["crossfit", "weightlifting", "running"]
    assert tree[0]["soon"] is True and tree[1]["children"][0]["children"][0]["slug"] == "bulgarian-adaptation"
    # 2. карточка: нет максов -> нужен ввод, три варианта старта
    card = c.get("/api/programs/bulgarian-peak-8w", params={"today": D}).json()
    assert card["template"]["required_lifts"] == ["squat_snatch", "clean_and_jerk", "back_squat"]
    req = {x["lift"]: x for x in card["requirements"]["lifts"]}
    assert req["squat_snatch"]["reference"]["source"] == "needs_input"
    assert req["squat_snatch"]["reference"]["options"] == {"careful": 34, "normal": 48, "experienced": 66}
    assert card["requirements"]["needs_input"] and card["enrollment_id"] is None
    assert c.get("/api/programs/run-speed").json()["soon"] is True
    assert c.get("/api/programs/nope").status_code == 404
    # 3. запись без максов -> 422 со списком вопросов
    r = c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D}, json={"start_day": D})
    assert r.status_code == 422 and r.json()["code"] == "needs_input"
    assert r.json()["items"]["squat_snatch"]["options"]["normal"] == 48
    # 4. запись со стартовым уровнем -> тест-сессия
    eid = str(uuid.uuid4())
    r = c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D},
               json={"start_day": D, "level": "normal", "id": eid})
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["id"] == eid and set(e["test_lifts"]) == {"squat_snatch", "clean_and_jerk", "back_squat"}
    assert e["base_maxes"]["squat_snatch"]["source"] == "starter"
    again = c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D},
                   json={"start_day": D, "level": "normal", "id": eid}).json()
    assert again["existing"] is True
    assert c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D},
                  json={"start_day": D, "level": "normal"}).status_code == 409
    assert [x["id"] for x in c.get("/api/enrollments").json()["enrollments"]] == [eid]
    assert c.get(f"/api/enrollments/{eid}").json()["sessions"]["total"] > 30
    # 5. сегодня -> тест-сессия
    t = c.get(f"/api/enrollments/{eid}/today", params={"today": D}).json()
    assert t["state"] == "today" and t["session"]["kind"] == "test" and t["session"]["week"] == 0
    sid = t["session"]["id"]
    sess = c.get(f"/api/sessions/{sid}").json()
    sets = _sets(sess)
    assert sets[0]["planned_kg"] and sets[0]["rest_sec"] and sess["blocks"][0]["exercises"][0]["lift"]
    # 6. чек-ин в тест-сессии: вес не меняем, советуем перенести
    ck = c.post(f"/api/sessions/{sid}/checkin", json={"tired": True, "sleepy": True}).json()
    assert ck["adjust"]["postpone_advised"] is True and "перенести" in ck["why"]
    assert [s["planned_kg"] for s in _sets(ck)] == [s["planned_kg"] for s in sets]
    assert c.post(f"/api/sessions/{sid}/checkin", json={"energy": 9}).status_code == 422
    # 7. подходы: рывок — лесенка и попытка 60
    targets = {"squat_snatch": 60, "clean_and_jerk": 75, "back_squat": 110}
    for ex in sess["blocks"][0]["exercises"]:
        cap = targets[ex["lift"]]
        for s in ex["sets"]:
            kg = min(s["planned_kg"], cap)
            if s["kind"] == "attempt" and s["n"] != 7:
                continue
            if s["kind"] == "attempt":
                kg = cap
            r = c.put(f"/api/sessions/{sid}/sets/{s['id']}", json={"done_kg": kg, "reps": 1, "ok": True})
            assert r.status_code == 200, r.text
    r = c.put(f"/api/sessions/{sid}/sets/{sets[0]['id']}", json={"done_kg": 9999})
    assert r.status_code == 422
    assert c.get(f"/api/sessions/{sid}").json()["status"] == "in_progress"
    # 8. финиш
    aid = str(uuid.uuid4())
    fin = c.post(f"/api/sessions/{sid}/finish", params={"today": D}, json={"rpe": 8, "feel": 4, "activity_id": aid})
    assert fin.status_code == 200, fin.text
    f = fin.json()
    assert f["activity_id"] == aid and {m["lift"]: m["kg"] for m in f["maxes"]} == targets
    assert set(f["base_updated"]) == set(targets)
    rows = env.execute("SELECT discipline, value, source FROM discipline_results WHERE tg_id=? AND activity_id=?",
                       (uid, aid)).fetchall()
    assert {r["discipline"]: r["value"] for r in rows} == targets and all(r["source"] == "auto" for r in rows)
    act = env.execute("SELECT sport, source, perf_rpe, extra FROM activities WHERE tg_id=? AND activity_id=?",
                      (uid, aid)).fetchone()
    assert act["sport"] == "weightlifting" and act["perf_rpe"] == 8
    assert json.loads(act["extra"])["program"]["session_id"] == sid
    again = c.post(f"/api/sessions/{sid}/finish", json={"rpe": 3}).json()
    assert again["already"] is True and again["activity_id"] == aid
    assert c.put(f"/api/sessions/{sid}/sets/{sets[0]['id']}", json={"done_kg": 50}).status_code == 409
    assert c.get(f"/api/enrollments/{eid}").json()["base_maxes"]["squat_snatch"]["source"] == "test"
    # 9. рабочая сессия: рывок 65 при базе 60 -> предложение обновить
    t = c.get(f"/api/enrollments/{eid}/today", params={"today": "2026-09-29"}).json()
    s2 = t["session"]
    assert s2["week"] == 1 and s2["idx"] == 1
    sn = next(ex for ex in s2["blocks"][0]["exercises"] if ex["lift"] == "squat_snatch")
    c.put(f"/api/sessions/{s2['id']}/sets/{sn['sets'][0]['id']}", json={"done_kg": 65, "reps": 1, "ok": True})
    f2 = c.post(f"/api/sessions/{s2['id']}/finish", params={"today": "2026-09-29"}, json={"rpe": 6}).json()
    assert [x["lift"] for x in f2["refresh"]] == ["squat_snatch"] and f2["refresh"][0]["new_kg"] == 65
    assert c.get(f"/api/enrollments/{eid}").json()["base_maxes"]["squat_snatch"]["kg"] == 60
    ref = c.post(f"/api/enrollments/{eid}/refresh-base", json={}).json()
    assert ref["base_maxes"]["squat_snatch"]["kg"] == 65 and ref["refreshed"] == ["squat_snatch"]
    # 10. тренд
    tr = c.get("/api/lifts/squat_snatch/trend", params={"window": 5}).json()
    assert [p["kg"] for p in tr["points"]] == [60, 65] and tr["trend"] in ("up", "flat")
    assert c.get("/api/lifts/pull_up/trend").status_code == 404
    assert c.get("/api/lifts/squat_snatch/trend", params={"window": 0}).status_code == 422


def test_on_miss_over_api(env):
    c, uid = _login(env)
    for d, kg in (("squat_snatch", 80), ("clean_and_jerk", 100), ("back_squat", 140)):
        botdb.add_result(env, uid, d, kg, "manual", "2026-09-20", reps=1, est_1rm=kg)
    eid = c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D}, json={"start_day": D}).json()["id"]
    s = c.get(f"/api/enrollments/{eid}/today", params={"today": "2026-10-12"}).json()["session"]   # неделя 3
    sn = next(ex for ex in s["blocks"][0]["exercises"] if ex["lift"] == "squat_snatch")["sets"]
    r = c.put(f"/api/sessions/{s['id']}/sets/{sn[3]['id']}", json={"done_kg": sn[3]["planned_kg"], "reps": 1, "ok": False})
    body = r.json()
    assert r.status_code == 200 and body["changed"] and "5" in body["why"]["ru"]
    s2 = c.get(f"/api/sessions/{s['id']}").json()
    sn2 = next(ex for ex in s2["blocks"][0]["exercises"] if ex["lift"] == "squat_snatch")["sets"]
    assert sn2[4]["planned_kg"] == sn[4]["planned_kg"] - 5
    ck = c.post(f"/api/sessions/{s['id']}/checkin", json={"tired": True}).json()
    assert ck["why"] and ck["adjust"]["level"] == "minus5"


def test_other_users_data_is_404_and_admin_as(env):
    a, uid_a = _login(env, nick="A")
    b, uid_b = _login(env, nick="B")
    adm, uid_adm = _login(env, role="admin", nick="Root")
    for d, kg in (("squat_snatch", 80), ("clean_and_jerk", 100), ("back_squat", 140)):
        botdb.add_result(env, uid_a, d, kg, "manual", "2026-09-20", reps=1, est_1rm=kg)
    e = a.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D}, json={"start_day": D}).json()
    eid = e["id"]
    sid = a.get(f"/api/enrollments/{eid}/today", params={"today": D}).json()["session"]["id"]
    for method, url, kw in [("get", f"/api/enrollments/{eid}", {}), ("get", f"/api/enrollments/{eid}/today", {}),
                            ("post", f"/api/enrollments/{eid}/refresh-base", {"json": {}}),
                            ("post", f"/api/programs/enrollments/{eid}/cancel", {}),
                            ("get", f"/api/sessions/{sid}", {}),
                            ("put", f"/api/sessions/{sid}/sets/x", {"json": {"done_kg": 50, "exercise": "back_squat"}}),
                            ("post", f"/api/sessions/{sid}/checkin", {"json": {"tired": True}}),
                            ("post", f"/api/sessions/{sid}/finish", {"json": {}})]:
        assert getattr(b, method)(url, **kw).status_code == 404, url
    assert b.get("/api/enrollments").json() == {"enrollments": []}
    # на «чужой» ?as= обычный пользователь не влияет
    assert b.get(f"/api/enrollments/{eid}", params={"as": uid_a}).status_code == 404
    # админ через ?as=
    assert adm.get(f"/api/enrollments/{eid}").status_code == 404
    r = adm.get(f"/api/enrollments/{eid}", params={"as": uid_a})
    assert r.status_code == 200 and r.json()["id"] == eid
    assert adm.get(f"/api/sessions/{sid}", params={"as": uid_a}).status_code == 200


def test_pause_resume_cancel(env):
    c, uid = _login(env)
    for d, kg in (("squat_snatch", 80), ("clean_and_jerk", 100), ("back_squat", 140)):
        botdb.add_result(env, uid, d, kg, "manual", "2026-09-20", reps=1, est_1rm=kg)
    e = c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D}, json={"start_day": D}).json()
    eid = e["id"]
    sid = c.get(f"/api/enrollments/{eid}/today", params={"today": D}).json()["session"]["id"]
    base = f"/api/programs/enrollments/{eid}"
    assert c.post(f"{base}/resume").status_code == 409                      # активная не возобновляется
    assert c.post(f"{base}/pause").json()["status"] == "paused"
    assert c.post(f"{base}/pause").status_code == 409
    assert c.get(f"/api/enrollments/{eid}/today", params={"today": D}).json() == {
        "state": "paused", "enrollment_id": eid, "date": D, "session": None}
    assert c.put(f"/api/sessions/{sid}/sets/x", json={"done_kg": 50, "exercise": "back_squat"}).status_code == 409
    assert c.post(f"/api/enrollments/{eid}/resume").json()["status"] == "active"     # короткий алиас
    assert c.post(f"{base}/cancel").json()["status"] == "cancelled"
    assert c.post(f"{base}/cancel").status_code == 409
    assert c.post(f"{base}/resume").status_code == 409
    assert c.get(f"/api/sessions/{sid}").status_code == 200                  # история читается
    assert c.get("/api/enrollments", params={"status": "cancelled"}).json()["enrollments"][0]["id"] == eid
    # после отмены можно записаться заново
    assert c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D}, json={"start_day": D}).status_code == 200


def test_error_mapping(env):
    c, uid = _login(env)
    assert c.post("/api/programs/run-speed/enroll", params={"today": D}, json={"start_day": D}).status_code == 409
    assert c.post("/api/programs/ghost/enroll", params={"today": D}, json={"start_day": D}).status_code == 404
    assert c.post("/api/programs/bulgarian-peak-8w/enroll", json={"start_day": "вчера"}).status_code == 422
    assert c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D},
                  json={"start_day": D, "level": "crazy"}).status_code in (422,)
    assert c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D},
                  json={"start_day": D, "base_maxes": {"squat_snatch": -1}}).status_code == 422
    r = c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D},
               json={"start_day": D, "level": "normal"}).json()
    sid = c.get(f"/api/enrollments/{r['id']}/today", params={"today": D}).json()["session"]["id"]
    bad = c.post(f"/api/sessions/{sid}/finish", json={"activity_id": "not-a-uuid"})
    assert bad.status_code == 400 and bad.json()["code"] == "bad_id"          # ServiceError из workouts
    assert c.post(f"/api/sessions/{sid}/finish", json={"rpe": 11}).status_code == 422
    assert c.get("/api/sessions/unknown").status_code == 404
    assert c.get("/api/enrollments/x/today").status_code == 404
    assert c.get("/api/enrollments", params={"as": "nan"}).status_code == 422


def test_invalid_template_is_500_not_crash(env, tmp_path, monkeypatch):
    c, uid = _login(env)
    good = json.loads((eng.PROGRAMS_DIR / "bulgarian-peak-8w.json").read_text(encoding="utf-8"))
    good["slug"] = "broken-one"
    del good["weeks"][0]["sessions"][0]["blocks"][0]["exercises"][0]["lift"]
    d = tmp_path / "programs"
    d.mkdir()
    (d / "broken-one.json").write_text(json.dumps(good), encoding="utf-8")
    monkeypatch.setattr(eng, "PROGRAMS_DIR", d)
    eng._load_template_cached.cache_clear()
    env.execute("INSERT INTO program_nodes (id,parent_id,kind,slug,title_ru,title_en,status,sort,template_slug) "
                "VALUES ('broken-one','bulgarian','program','broken-one','Сломанная','Broken','active',99,'broken-one')")
    env.commit()
    r = c.get("/api/programs/broken-one")
    assert r.status_code == 500 and r.json()["code"] == "template"
    r = c.post("/api/programs/broken-one/enroll", params={"today": D}, json={"start_day": D, "level": "normal"})
    assert r.status_code == 500
    assert env.execute("SELECT COUNT(*) FROM program_enrollments").fetchone()[0] == 0
    eng._load_template_cached.cache_clear()


def test_lifespan_seeds_catalog(env, monkeypatch):
    env.execute("UPDATE program_nodes SET title_ru='сломано' WHERE slug='running'")
    env.commit()
    with TestClient(app) as c:                       # lifespan: миграции + seed_catalog
        pass
    row = botdb.connect(botdb.default_db_path()).execute("SELECT title_ru FROM program_nodes WHERE slug='running'").fetchone()
    assert row["title_ru"] == "Бег"


def _enroll_fresh(c, con, uid):
    for d, kg in (("squat_snatch", 80), ("clean_and_jerk", 100), ("back_squat", 140)):
        botdb.add_result(con, uid, d, kg, "manual", "2026-09-20", reps=1, est_1rm=kg)
    return c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D}, json={"start_day": D}).json()["id"]


def test_enrollment_sessions_list(env):
    c, uid = _login(env)
    eid = _enroll_fresh(c, env, uid)
    lst = c.get(f"/api/enrollments/{eid}/sessions").json()["sessions"]
    assert len(lst) == 38 and [s["planned_day"] for s in lst] == sorted(s["planned_day"] for s in lst)
    first = lst[0]
    assert set(first) >= {"id", "planned_day", "week", "idx", "kind", "status", "activity_id", "sets_done", "sets_total"}
    assert first["status"] == "planned" and first["sets_done"] == 0 and first["sets_total"] > 5
    assert lst[-1]["kind"] == "test" and lst[-1]["week"] == 8
    sess = c.get(f"/api/sessions/{first['id']}").json()
    sets = _sets(sess)
    c.put(f"/api/sessions/{first['id']}/sets/{sets[0]['id']}", json={"done_kg": sets[0]["planned_kg"], "ok": True})
    c.put(f"/api/sessions/{first['id']}/sets/{sets[1]['id']}", json={"done_kg": 40, "ok": False})   # промах не в счёт
    got = c.get(f"/api/enrollments/{eid}/sessions").json()["sessions"][0]
    assert got["status"] == "in_progress" and got["sets_done"] == 1 and got["sets_total"] == len(sets)
    c.post(f"/api/sessions/{first['id']}/finish", params={"today": D}, json={})
    got = c.get(f"/api/enrollments/{eid}/sessions").json()["sessions"][0]
    assert got["status"] == "done" and got["activity_id"]
    b, _ = _login(env, nick="B")
    assert b.get(f"/api/enrollments/{eid}/sessions").status_code == 404
    assert TestClient(app).get(f"/api/enrollments/{eid}/sessions").status_code == 401


def test_enrollment_get_has_refresh(env):
    c, uid = _login(env)
    eid = _enroll_fresh(c, env, uid)
    assert c.get(f"/api/enrollments/{eid}").json()["refresh"] == []
    botdb.add_result(env, uid, "back_squat", 145, "manual", D, reps=1, est_1rm=145)
    botdb.add_result(env, uid, "clean_and_jerk", 101, "manual", D, reps=1, est_1rm=101)     # +1 — не в счёт
    r = c.get(f"/api/enrollments/{eid}").json()["refresh"]
    assert [x["lift"] for x in r] == ["back_squat"] and r[0]["base_kg"] == 140 and r[0]["new_kg"] == 145
    assert c.get("/api/enrollments").json()["enrollments"][0].get("refresh") is None      # в списке не считаем
    assert c.get(f"/api/enrollments/{eid}").json()["base_maxes"]["back_squat"]["kg"] == 140
    botdb.add_result(env, uid, "squat_snatch", 85, "manual", D, reps=1, est_1rm=85)
    only = c.post(f"/api/enrollments/{eid}/refresh-base", json={"lifts": ["squat_snatch"]}).json()
    assert only["refreshed"] == ["squat_snatch"] and only["base_maxes"]["back_squat"]["kg"] == 140
    assert [x["lift"] for x in only["refresh"]] == ["back_squat"]
    allr = c.post(f"/api/enrollments/{eid}/refresh-base").json()                       # без тела: все из refresh
    assert allr["refreshed"] == ["back_squat"] and allr["refresh"] == []
    b, _ = _login(env, nick="B")
    assert b.get(f"/api/enrollments/{eid}").status_code == 404


def test_put_set_partial_and_reset(env):
    c, uid = _login(env)
    eid = _enroll_fresh(c, env, uid)
    s = c.get(f"/api/enrollments/{eid}/today", params={"today": "2026-10-12"}).json()["session"]   # неделя 3, рывок
    sid = s["id"]
    sn = next(ex for ex in s["blocks"][0]["exercises"] if ex["lift"] == "squat_snatch")["sets"]
    url = lambda i: f"/api/sessions/{sid}/sets/{sn[i]['id']}"
    planned = [x["planned_kg"] for x in sn]
    # ok не передан -> отметка сохраняется при правке веса/заметки
    c.put(url(0), json={"done_kg": 40, "reps": 1, "ok": True})
    r = c.put(url(0), json={"note": "легко"}).json()["set"]
    assert r["ok"] is True and r["done_kg"] == 40 and r["note"] == "легко"
    r = c.put(url(0), json={"done_kg": 42.5}).json()["set"]
    assert r["ok"] is True and r["done_kg"] == 42.5 and r["note"] == "легко"
    # промах, затем сброс: подход неотмеченный, done_kg очищен, вес остатка снова от базы
    c.put(url(3), json={"done_kg": planned[3], "reps": 1, "ok": False})
    cur = next(ex for ex in c.get(f"/api/sessions/{sid}").json()["blocks"][0]["exercises"] if ex["lift"] == "squat_snatch")["sets"]
    assert cur[4]["planned_kg"] == planned[4] - 5
    r = c.put(url(3), json={"ok": None})
    assert r.status_code == 200
    body = r.json()
    assert body["set"]["ok"] is None and body["set"]["done_kg"] is None and cur[4]["id"] in body["changed"]
    cur = next(ex for ex in c.get(f"/api/sessions/{sid}").json()["blocks"][0]["exercises"] if ex["lift"] == "squat_snatch")["sets"]
    assert [x["planned_kg"] for x in cur] == planned            # план как без промаха
    assert cur[3]["ok"] is None and cur[3]["done_kg"] is None and cur[3]["planned_kg"] == planned[3]
    assert c.get(f"/api/sessions/{sid}").json()["misses"] == []
    # сброс остаётся идемпотентным; ok: false после ok не передан -> остаётся
    assert c.put(url(3), json={"ok": None}).json()["changed"] == []
    c.put(url(3), json={"done_kg": planned[3], "ok": False})
    assert c.put(url(3), json={"note": "тяжело"}).json()["set"]["ok"] is False
    assert c.put(url(3), json={"ok": None, "done_kg": 60}).json()["set"]["done_kg"] == 60     # вес передан — не сброс
    # внеплановый подход можно убрать сбросом
    c.put(f"/api/sessions/{sid}/sets/extra-1", json={"done_kg": 50, "ok": True, "exercise": "back_squat"})
    assert len(c.get(f"/api/sessions/{sid}").json()["extra_sets"]) == 1
    c.put(f"/api/sessions/{sid}/sets/extra-1", json={"ok": None})
    assert c.get(f"/api/sessions/{sid}").json()["extra_sets"] == []
    # чужой не может
    b, _ = _login(env, nick="B")
    assert b.put(url(0), json={"ok": None}).status_code == 404


def test_program_descriptions_in_card_and_sessions(env):
    c, uid = _login(env)
    for slug in ("bulgarian-peak-8w", "bulgarian-adaptation"):
        card = c.get(f"/api/programs/{slug}", params={"today": D}).json()["template"]
        assert [b["id"] for b in card["about"]][:2] == ["intro", "what"]
        assert all(b["title"]["ru"] and b["text"]["en"] for b in card["about"])
        assert {"medium", "high"} <= set(card["week_types"])
        # у каждого дня есть назначение и «над чем работаем»
        for w in card["weeks"]:
            assert len(w["days"]) == w["sessions"]
            for d in w["days"]:
                assert d["purpose"]["ru"] and d["focus"]["ru"] and d["intensity"]
    # описание дня видно и в самой сессии (берётся из шаблона по неделе и дню)
    r = c.post("/api/programs/bulgarian-peak-8w/enroll", params={"today": D},
               json={"start_day": D, "level": "normal", "base_maxes": {"squat_snatch": 80, "clean_and_jerk": 100, "back_squat": 130}})
    eid = r.json()["id"]
    sessions = c.get(f"/api/enrollments/{eid}/sessions").json()
    sid = next(s["id"] for s in sessions["sessions"] if s["week"] == 1 and s["idx"] == 1)
    s = c.get(f"/api/sessions/{sid}").json()
    assert s["purpose"]["ru"] and s["focus"]["ru"] and s["week_type_info"]["title"]["ru"] == "Объёмная неделя"


def test_template_validation_checks_descriptions():
    import copy
    tpl = copy.deepcopy(eng.load_template("bulgarian-peak-8w"))
    assert eng.template_errors(tpl) == []
    tpl["about"][0]["text"] = {"ru": "только русский"}
    tpl["weeks"][0]["sessions"][0]["purpose"] = {"ru": "", "en": ""}
    errs = eng.template_errors(tpl)
    assert any("about[1].text" in e for e in errs) and any("purpose" in e for e in errs)
