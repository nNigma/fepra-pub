"""Соревнования через API: старты, участие, этапы, результаты, итог, размер поля."""
from __future__ import annotations

from datetime import date

import pytest

import tjbot.vision as vision
from tj.services import competitions as svc
from tjbot import db as botdb

from api_common import env, login, make_upload, wait_job  # noqa: F401


def _mk_event(env, uid, *, name="Кубок", city="Владимир", d="2026-04-12", div="PRO",
              field=None, join=True):
    eid = botdb.create_event(env, name=name, city=city, date_start=d, date_end=d,
                             sport="crossfit", fmt="", created_by=uid)
    did = botdb.add_division(env, eid, name=div, field_size=field)
    pid = botdb.add_participant(env, did, tg_id=uid, athlete=None) if join else None
    return eid, did, pid


def _stages(env, did, n=3):
    return [botdb.add_stage(env, did, idx=i, name=f"Этап {i}", prescription="x")
            for i in range(1, n + 1)]


# --- чистые функции (кейсы из хендлера) -------------------------------------------------

def test_parse_date_formats():
    t = date(2026, 5, 1)
    assert svc.parse_date("12.04.2026", t) == date(2026, 4, 12)
    assert svc.parse_date("12.04", t) == date(2026, 4, 12)
    assert svc.parse_date("2026-04-12", t) == date(2026, 4, 12)
    assert svc.parse_date("вчера", t) is None and svc.parse_date("", t) is None


def test_parse_result_text():
    assert svc.parse_result_text("5:30, 12") == {"value": "5:30", "place": 12, "field_size": None}
    assert svc.parse_result_text("5:30, 12, 40")["field_size"] == 40
    assert svc.parse_result_text("5:30, 12, много")["field_size"] is None   # игнорируется
    with pytest.raises(svc.Invalid) as e:
        svc.parse_result_text("5:30")
    assert e.value.code == "result_text_hint"
    with pytest.raises(svc.Invalid) as e:
        svc.parse_result_text("5:30, второе")
    assert e.value.code == "place_invalid"


def _st(i, name, results=()):
    return {"id": i * 10, "idx": i, "name": name,
            "results": [{"athlete": a} for a in results]}


def test_pick_stage_last_without_own_result():
    stages = [_st(1, "a", ["Я"]), _st(2, "b"), _st(3, "c")]
    assert svc.pick_stage_for_text_result(stages, "Я") == 30       # последний без результата
    stages = [_st(1, "a"), _st(2, "b", ["Я"]), _st(3, "c", ["Я"])]
    assert svc.pick_stage_for_text_result(stages, "Я") == 10
    stages = [_st(1, "a", ["Я"]), _st(2, "b", ["Я"])]
    assert svc.pick_stage_for_text_result(stages, "Я") == 20       # везде есть — последний
    assert svc.pick_stage_for_text_result([_st(1, "a", ["Другой"])], "Я") == 10
    assert svc.pick_stage_for_text_result([], "Я") is None


def test_map_result_rows_rules():
    stages = [_st(1, "Fran"), _st(2, "Grace"), _st(3, "Murph")]
    ids = svc.map_result_rows([{"stage": 2}, {"stage": "3"}, {"stage": "Fran"}], stages)
    assert ids == [20, 30, 10]                                     # idx, цифры строкой, имя
    # ни idx, ни имени -> позиция строки по порядку этапов
    assert svc.map_result_rows([{"stage": "??"}, {"stage": None}, {"stage": "x"}], stages) == [10, 20, 30]
    # позиция вне этапов -> None
    assert svc.map_result_rows([{"stage": 9}] * 4, stages)[3] is None
    # порядок этапов по idx, а не по списку
    assert svc.map_result_rows([{"stage": "?"}], list(reversed(stages))) == [10]
    assert svc.map_result_rows([{"stage": True}], stages) == [10]  # bool — не номер этапа


def test_category_labels():
    assert svc.category_label("pro") == "PRO" and svc.category_label("newbie") == "Новички"
    assert svc.category_label("newbie", "en") == "Beginners"
    with pytest.raises(svc.Invalid):
        svc.category_label("weird")


# --- события: список, создание, дедуп ---------------------------------------------------------

def test_list_mine_and_others(env):
    _mk_event(env, 1, name="Моё", d="2026-05-01")
    _mk_event(env, 1, name="Старое", city="Тула", d="2026-01-01")
    _mk_event(env, 2, name="Чужое", city="Омск", d="2026-04-04")
    lst = login(1).get("/api/comp/list").json()
    assert [e["name"] for e in lst["mine"]] == ["Моё", "Старое"]       # новые сверху
    assert [e["name"] for e in lst["others"]] == ["Чужое"]
    assert lst["mine"][0]["divisions"][0]["participant_id"] is not None
    assert lst["others"][0]["divisions"][0]["participant_id"] is None
    assert lst["others"][0]["division_id"] == lst["others"][0]["divisions"][0]["id"]


def test_create_event_and_dedup(env):
    c = login(1)
    body = {"name": "Кубок Тулы", "date": "12.04.2026", "city": "Тула", "category": "rx"}
    r = c.post("/api/comp/events", json=body).json()
    assert r["created"] and r["participant_id"]
    ev = c.get(f"/api/comp/events/{r['event_id']}").json()
    assert ev["date_start"] == "2026-04-12" and ev["divisions"][0]["name"] == "RX"
    # тот же город (без регистра) и дата -> дубль, ничего не создано
    dup = login(2).post("/api/comp/events", json={**body, "city": "тула"}).json()
    assert dup["created"] is False and dup["duplicate"] is True
    assert dup["candidates"][0]["id"] == r["event_id"]
    assert len(botdb.list_other_competitions(env, 2)) == 1
    forced = login(2).post("/api/comp/events", json={**body, "city": "тула", "force_new": True}).json()
    assert forced["created"] and forced["event_id"] != r["event_id"]
    # другая дата — не дубль
    other = c.post("/api/comp/events", json={**body, "date": "13.04.2026"}).json()
    assert other["created"]


def test_create_event_validation(env):
    c = login(1)
    ok = {"name": "A", "date": "2026-04-12", "city": "B", "category": "pro"}
    assert c.post("/api/comp/events", json={**ok, "date": "завтра"}).status_code == 422
    assert c.post("/api/comp/events", json={**ok, "category": None}).status_code == 422
    assert c.post("/api/comp/events", json={**ok, "category": "custom"}).status_code == 422
    assert c.post("/api/comp/events", json={**ok, "category": "zzz"}).status_code == 422
    assert c.post("/api/comp/events", json={**ok, "name": " "}).status_code == 422
    custom = c.post("/api/comp/events", json={**{k: v for k, v in ok.items() if k != "category"},
                                              "division": "Мастера 40+"}).json()
    assert c.get(f"/api/comp/events/{custom['event_id']}").json()["divisions"][0]["name"] == "Мастера 40+"


def test_join_idempotent_and_divisions(env):
    eid, did, _ = _mk_event(env, 2, div="RX")
    c = login(1)
    a = c.post(f"/api/comp/events/{eid}/join").json()
    b = c.post(f"/api/comp/events/{eid}/join", json={}).json()
    assert a["created"] and not b["created"] and a["participant_id"] == b["participant_id"]
    d2 = botdb.add_division(env, eid, name="INT")
    assert login(3).post(f"/api/comp/events/{eid}/join").status_code == 422      # нужен division_id
    j = login(3).post(f"/api/comp/events/{eid}/join", json={"division_id": d2}).json()
    assert j["division_id"] == d2
    assert login(3).post(f"/api/comp/events/{eid}/join", json={"division_id": 9999}).status_code == 404
    assert login(3).post("/api/comp/events/9999/join").status_code == 404
    empty = botdb.create_event(env, name="Пустой", city="X", date_start="2026-01-01",
                               date_end="2026-01-01", sport="crossfit", fmt="", created_by=2)
    assert login(3).post(f"/api/comp/events/{empty}/join").status_code == 422


def test_view_foreign_event_hides_results(env):
    eid, did, pid = _mk_event(env, 2)
    (sid,) = _stages(env, did, 1)
    botdb.add_comp_result(env, sid, athlete="Я", value="5:00", place=3)
    c = login(1)
    ev = c.get(f"/api/comp/events/{eid}").json()
    assert ev["divisions"][0]["stages"][0]["name"] == "Этап 1"
    assert "results" not in ev["divisions"][0]["stages"][0]
    own = login(2).get(f"/api/comp/events/{eid}").json()
    assert own["divisions"][0]["stages"][0]["results"][0]["place"] == 3
    assert c.get("/api/comp/events/9999").status_code == 404


# --- права ----------------------------------------------------------------------------

def test_foreign_event_write_forbidden(env):
    eid, did, _ = _mk_event(env, 2)
    (sid,) = _stages(env, did, 1)
    c = login(1)
    assert c.post(f"/api/comp/events/{eid}/stages", json={"text": "Fran"}).status_code == 403
    assert c.post(f"/api/comp/events/{eid}/results", json={"text": "5:00, 3"}).status_code == 403
    assert c.post("/api/comp/stages/confirm", json={"event_id": eid, "stages": [{"name": "x"}]}).status_code == 403
    assert c.post("/api/comp/results/confirm", json={"event_id": eid, "rows": [{"stage": 1}]}).status_code == 403
    assert c.put(f"/api/comp/divisions/{did}/field_size", json={"field_size": 10}).status_code == 403
    assert c.put(f"/api/comp/events/{eid}/total", json={}).status_code == 403
    assert c.post(f"/api/comp/events/{eid}/stages", json={"text": "Fran", "division_id": did}).status_code == 403
    up = make_upload(env, 1)
    assert c.post(f"/api/comp/events/{eid}/stages/parse", json={"upload_id": up}).status_code == 403
    assert c.post(f"/api/comp/events/{eid}/results/parse", json={"upload_id": up}).status_code == 403


def test_admin_can_edit_foreign_event(env):
    eid, did, _ = _mk_event(env, 2)
    c = login(1, admin=True)
    assert c.post(f"/api/comp/events/{eid}/stages", json={"text": "Fran\n21-15-9"}).status_code == 200
    assert c.put(f"/api/comp/divisions/{did}/field_size", json={"field_size": 30}).status_code == 200
    r = c.post(f"/api/comp/events/{eid}/results", json={"text": "5:00, 3", "athlete": "Иван"})
    assert r.status_code == 200
    # итог — только по своему участию, админ не участник
    assert c.put(f"/api/comp/events/{eid}/total", json={"total_points": 3, "final_place": 1}).status_code == 403


def test_need_division_when_two_mine(env):
    eid, d1, _ = _mk_event(env, 1, div="A")
    d2 = botdb.add_division(env, eid, name="B")
    botdb.add_participant(env, d2, tg_id=1)
    c = login(1)
    r = c.post(f"/api/comp/events/{eid}/stages", json={"text": "x"})
    assert r.status_code == 422 and "division_id" in r.json()["detail"]
    ok = c.post(f"/api/comp/events/{eid}/stages", json={"text": "x", "division_id": d2})
    assert ok.status_code == 200 and ok.json()["division_id"] == d2


# --- этапы ---------------------------------------------------------------------------------

def test_stage_text_numbering(env):
    eid, did, _ = _mk_event(env, 1)
    c = login(1)
    a = c.post(f"/api/comp/events/{eid}/stages", json={"text": "Fran\n21-15-9 трастеры"}).json()
    b = c.post(f"/api/comp/events/{eid}/stages", json={"text": "Grace"}).json()
    assert (a["idx"], b["idx"]) == (1, 2)
    st = botdb.get_stages(env, did)
    assert st[0]["name"] == "Fran" and st[0]["prescription"].startswith("Fran\n21") and st[0]["fmt"] == "text"
    assert c.post(f"/api/comp/events/{eid}/stages", json={"text": "  "}).status_code == 422


@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    state = {"stages": [{"name": "Fran", "prescription": "21-15-9", "format": "for_time",
                         "movements": ["трастер"], "movements_canon": []},
                        {"name": "", "prescription": "3 круга", "format": None, "movements": []}],
             "results": {"athlete": "Я", "rows": [{"stage": 2, "value": "4:10", "place": 5},
                                                  {"stage": "Fran", "value": "3:00", "place": 2},
                                                  {"stage": None, "value": "9:99", "place": None}]}}
    monkeypatch.setattr(vision, "parse_stages", lambda *a, **k: state["stages"])
    monkeypatch.setattr(vision, "parse_results", lambda *a, **k: state["results"])
    return state


def test_stages_photo_parse_and_confirm_idempotent(env, ai):
    eid, did, _ = _mk_event(env, 1)
    _stages(env, did, 1)                      # уже есть этап 1
    c = login(1)
    up = make_upload(env, 1, "other")
    job = wait_job(c, c.post(f"/api/comp/events/{eid}/stages/parse", json={"upload_id": up}).json()["job_id"])
    res = job["result"]
    assert res["recognized"] and len(res["stages"]) == 2 and len(res["preview"]) == 2
    assert res["stages"][0]["source_ref"] == f"upload:{up}#1"
    assert len(botdb.get_stages(env, did)) == 1          # превью ничего не пишет
    body = {"event_id": eid, "stages": res["stages"]}
    r1 = c.post("/api/comp/stages/confirm", json=body).json()
    r2 = c.post("/api/comp/stages/confirm", json=body).json()
    assert (r1["saved"], r1["skipped"]) == (2, 0) and (r2["saved"], r2["skipped"]) == (0, 2)
    st = botdb.get_stages(env, did)
    assert [s["idx"] for s in st] == [1, 2, 3]
    assert st[1]["fmt"] == "for_time" and st[1]["movements"] == ["трастер"]
    assert st[2]["name"] == "Этап 3" and st[2]["fmt"] == "text"     # пустое имя, пустой формат


def test_stages_parse_failures(env, ai, monkeypatch):
    eid, did, _ = _mk_event(env, 1)
    c = login(1)
    up = make_upload(env, 1)
    ai["stages"] = None
    res = wait_job(c, c.post(f"/api/comp/events/{eid}/stages/parse", json={"upload_id": up}).json()["job_id"])["result"]
    assert res["recognized"] is False and res["reason"] == "not_recognized"
    monkeypatch.setattr(vision, "has_vision", lambda: False)
    res = wait_job(c, c.post(f"/api/comp/events/{eid}/stages/parse", json={"upload_id": up}).json()["job_id"])["result"]
    assert res["reason"] == "no_vision"
    assert c.post(f"/api/comp/events/{eid}/stages/parse", json={"upload_id": make_upload(env, 77)}).status_code == 404


def test_stages_parse_quota(env, ai):
    from tjbot import access
    eid, did, _ = _mk_event(env, 1)
    c = login(1)
    up = make_upload(env, 1)
    for _ in range(access.LLM_DAILY_LIMIT):
        botdb.llm_quota_bump(env, 1, date.today().isoformat())
    res = wait_job(c, c.post(f"/api/comp/events/{eid}/stages/parse", json={"upload_id": up}).json()["job_id"])["result"]
    assert res["reason"] == "quota"


def test_confirm_stages_validation(env):
    eid, did, _ = _mk_event(env, 1)
    c = login(1)
    assert c.post("/api/comp/stages/confirm", json={"event_id": eid, "stages": []}).status_code == 422
    assert c.post("/api/comp/stages/confirm", json={"event_id": eid, "stages": ["x"]}).status_code == 422
    assert c.post("/api/comp/stages/confirm", json={"event_id": 9999, "stages": [{"name": "a"}]}).status_code == 404


# --- результаты ------------------------------------------------------------------------------

def test_result_text_heuristic_and_field_size(env):
    eid, did, _ = _mk_event(env, 1)
    ids = _stages(env, did, 3)
    c = login(1)
    r1 = c.post(f"/api/comp/events/{eid}/results", json={"text": "5:30, 12, 40"}).json()
    assert r1["stage_id"] == ids[2] and r1["field_size"] == 40         # последний без результата
    r2 = c.post(f"/api/comp/events/{eid}/results", json={"text": "6:00, 7, 99"}).json()
    assert r2["stage_id"] == ids[1]
    div = env.execute("SELECT field_size FROM comp_divisions WHERE id=?", (did,)).fetchone()
    assert div["field_size"] == 40                                     # уже задан — не перетирается
    r3 = c.post(f"/api/comp/events/{eid}/results", json={"text": "7:00, 9"}).json()
    r4 = c.post(f"/api/comp/events/{eid}/results", json={"text": "8:00, 1"}).json()
    assert (r3["stage_id"], r4["stage_id"]) == (ids[0], ids[2])        # всё заполнено -> последний
    res = env.execute("SELECT * FROM comp_results WHERE stage_id=?", (ids[2],)).fetchall()
    assert len(res) == 2 and all(r["athlete"] == "Я" and r["points"] == r["place"] for r in res)


def test_result_text_errors(env):
    eid, did, _ = _mk_event(env, 1)
    c = login(1)
    assert c.post(f"/api/comp/events/{eid}/results", json={"text": "5:30, 3"}).status_code == 422  # нет этапов
    _stages(env, did, 1)
    assert c.post(f"/api/comp/events/{eid}/results", json={"text": "5:30"}).status_code == 422
    assert c.post(f"/api/comp/events/{eid}/results", json={"text": "5:30, x"}).status_code == 422


def test_result_text_explicit_stage_is_upsert(env):
    eid, did, _ = _mk_event(env, 1)
    ids = _stages(env, did, 2)
    c = login(1)
    for _ in range(2):
        r = c.post(f"/api/comp/events/{eid}/results", json={"text": "5:00, 4", "stage_idx": 1})
        assert r.json()["stage_id"] == ids[0]
    c.post(f"/api/comp/events/{eid}/results", json={"text": "4:50, 2", "stage_idx": 1})
    rows = env.execute("SELECT * FROM comp_results WHERE stage_id=?", (ids[0],)).fetchall()
    assert len(rows) == 1 and rows[0]["value"] == "4:50" and rows[0]["place"] == 2
    assert c.post(f"/api/comp/events/{eid}/results", json={"text": "1, 1", "stage_idx": 9}).status_code == 404


def test_results_photo_parse_and_confirm(env, ai):
    eid, did, _ = _mk_event(env, 1)
    ids = _stages(env, did, 3)
    env.execute("UPDATE comp_stages SET name='Fran' WHERE id=?", (ids[0],))
    env.commit()
    c = login(1)
    up = make_upload(env, 1)
    res = wait_job(c, c.post(f"/api/comp/events/{eid}/results/parse", json={"upload_id": up}).json()["job_id"])["result"]
    assert res["recognized"] and [r["stage_id"] for r in res["rows"]] == [ids[1], ids[0], ids[2]]
    assert res["rows"][0]["stage_idx"] == 2 and res["rows"][1]["stage_name"] == "Fran"
    assert env.execute("SELECT COUNT(*) FROM comp_results").fetchone()[0] == 0     # превью не пишет
    body = {"event_id": eid, "rows": res["rows"]}
    r1 = c.post("/api/comp/results/confirm", json=body).json()
    r2 = c.post("/api/comp/results/confirm", json=body).json()
    assert r1["saved"] == 3 and r2["saved"] == 3
    rows = env.execute("SELECT * FROM comp_results ORDER BY stage_id").fetchall()
    assert len(rows) == 3                                                      # без дублей
    by = {r["stage_id"]: r for r in rows}
    assert by[ids[1]]["value"] == "4:10" and by[ids[1]]["place"] == 5 and by[ids[1]]["points"] == 5
    assert by[ids[2]]["place"] is None and by[ids[2]]["athlete"] == "Я"


def test_results_confirm_mapping_fallbacks_and_skip(env):
    eid, did, _ = _mk_event(env, 1)
    ids = _stages(env, did, 2)
    c = login(1)
    rows = [{"stage": "??", "value": "2", "place": "3"},          # позиция 0 -> первый этап
            {"stage": "Этап 2", "value": "1", "place": 1},        # по имени
            {"stage": 7, "value": "3", "place": 3}]
    r = c.post("/api/comp/results/confirm", json={"event_id": eid, "rows": rows, "athlete": "Иван"}).json()
    assert r == {"saved": 2, "skipped": 1, "division_id": did}      # третья строка вне этапов
    got = env.execute("SELECT stage_id, athlete, place FROM comp_results ORDER BY stage_id").fetchall()
    assert [(g["stage_id"], g["athlete"], g["place"]) for g in got] == [(ids[0], "Иван", 3), (ids[1], "Иван", 1)]
    bad = c.post("/api/comp/results/confirm", json={"event_id": eid, "rows": [{"stage_id": 424242, "value": "1"}]})
    assert bad.status_code == 404


def test_results_parse_not_recognized(env, ai):
    eid, did, _ = _mk_event(env, 1)
    ai["results"] = {"athlete": "", "rows": []}
    c = login(1)
    up = make_upload(env, 1)
    res = wait_job(c, c.post(f"/api/comp/events/{eid}/results/parse", json={"upload_id": up}).json()["job_id"])["result"]
    assert res["recognized"] is False and res["reason"] == "not_recognized"


# --- итог, поле --------------------------------------------------------------------------------

def test_total_suggest_and_confirm(env):
    eid, did, pid = _mk_event(env, 1, field=22)
    ids = _stages(env, did, 2)
    botdb.add_comp_result(env, ids[0], athlete="Я", value="a", place=3)
    botdb.add_comp_result(env, ids[1], athlete="Я", value="b", place=2)
    botdb.add_comp_result(env, ids[0], athlete="Соперник", value="a", place=1)
    botdb.add_comp_result(env, ids[1], athlete="Соперник", value="b", place=1)
    c = login(1)
    sug = c.get(f"/api/comp/events/{eid}/total").json()
    assert sug["total_points"] == 5 and sug["final_place"] == 2 and sug["place_str"] == "2/22"
    put = c.put(f"/api/comp/events/{eid}/total", json={}).json()
    assert put == {"participant_id": pid, "total_points": 5.0, "final_place": 2, "source": "suggested"}
    row = env.execute("SELECT * FROM comp_participants WHERE id=?", (pid,)).fetchone()
    assert (row["final_place"], row["total_points"], row["confirmed_total"]) == (2, 5.0, 1)
    man = c.put(f"/api/comp/events/{eid}/total", json={"total_points": 4.5, "final_place": 1}).json()
    assert man["source"] == "manual"
    assert env.execute("SELECT final_place FROM comp_participants WHERE id=?", (pid,)).fetchone()[0] == 1
    assert c.put(f"/api/comp/events/{eid}/total", json={"total_points": 4}).status_code == 422
    assert c.put(f"/api/comp/events/{eid}/total", json={"total_points": 4, "final_place": 0}).status_code == 422


def test_total_without_results(env):
    eid, did, pid = _mk_event(env, 1)
    _stages(env, did, 1)
    c = login(1)
    assert c.get(f"/api/comp/events/{eid}/total").json()["total_points"] is None
    assert c.put(f"/api/comp/events/{eid}/total", json={}).status_code == 422


def test_field_size(env):
    eid, did, _ = _mk_event(env, 1, field=10)
    c = login(1)
    assert c.put(f"/api/comp/divisions/{did}/field_size", json={"field_size": 55}).json() == {
        "division_id": did, "field_size": 55}
    assert env.execute("SELECT field_size FROM comp_divisions WHERE id=?", (did,)).fetchone()[0] == 55
    assert c.put(f"/api/comp/divisions/{did}/field_size", json={"field_size": 0}).status_code == 422
    assert c.put("/api/comp/divisions/9999/field_size", json={"field_size": 5}).status_code == 404


def test_requires_login(env):
    from fastapi.testclient import TestClient
    from tjapp.api import app
    app.dependency_overrides.clear()
    assert TestClient(app).get("/api/comp/list").status_code == 401


def test_migration_0060_idempotent(env):
    import importlib
    mod = importlib.import_module("tj.migrations.0061_comp_api")
    mod.upgrade(env)
    mod.upgrade(env)
    names = {r[0] for r in env.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"comp_participants_div_idx", "comp_results_stage_idx", "comp_stages_source_idx"} <= names


def test_photo_note_reaches_vision_for_stages_and_results(env, ai, monkeypatch):
    seen = []
    monkeypatch.setattr(vision, "parse_stages", lambda *a, **k: seen.append(("st", k.get("hint"))) or ai["stages"])
    monkeypatch.setattr(vision, "parse_results", lambda *a, **k: seen.append(("rs", k.get("hint"))) or ai["results"])
    eid, did, _ = _mk_event(env, 1)
    _stages(env, did, 2)
    c = login(1)
    up = make_upload(env, 1, "other")
    wait_job(c, c.post(f"/api/comp/events/{eid}/stages/parse", json={"upload_id": up, "note": "второй день"}).json()["job_id"])
    wait_job(c, c.post(f"/api/comp/events/{eid}/results/parse", json={"upload_id": up, "note": "я в синей майке"}).json()["job_id"])
    wait_job(c, c.post(f"/api/comp/events/{eid}/results/parse", json={"upload_id": up}).json()["job_id"])
    assert seen == [("st", "второй день"), ("rs", "я в синей майке"), ("rs", None)]
