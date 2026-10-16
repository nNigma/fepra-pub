"""Программа зала: сервис tj.services.club и роуты /api/club/*."""
import json
from datetime import date

import pytest

from p5a_env import p5a, wait_job  # noqa: F401
from tj.services import club as svc
from tjbot import db as botdb, vision

TEXT = "Warm up\nFor time:\n21-15-9\nThrusters 43 kg\nPull-ups"
TODAY = date(2026, 9, 28)


@pytest.fixture
def world(p5a, monkeypatch):
    monkeypatch.setattr("tj.services.clock.today", lambda: TODAY)
    monkeypatch.setattr(vision, "subscription_ready", lambda e: False)   # без реального Claude
    botdb.add_gym(p5a.con, "Второй")
    p5a.user(1, "Босс", admin=True)
    p5a.user(2, "Тренер", coach="Universe")
    p5a.user(3, "Атлет")                            # Universe
    p5a.user(4, "Чужой", gym="Второй")
    p5a.user(5, "ТренерВторого", coach="Второй", gym="Второй")
    return p5a


def _put(c, day="2026-09-28", text=TEXT, **kw):
    return c.put("/api/club/program", json={"day": day, "raw_text": text, **kw})


def test_view_empty_and_last(world):
    c = world.client(3)
    j = c.get("/api/club/program").json()
    assert j == {"gym": "Universe", "day": "2026-09-28", "program": None, "last_day": None,
                 "can_manage": False}
    _put(world.client(2), day="2026-09-20")
    j = c.get("/api/club/program").json()
    assert j["program"] is None and j["last_day"] == "2026-09-20"


def test_put_and_view_program(world):
    r = _put(world.client(2))
    assert r.status_code == 200
    p = r.json()["program"]
    assert p["confirmed"] and p["gym"] == "Universe" and p["source"] == "text" and p["created_by"] == 2
    assert p["uuid"] and p["updated_at"] and "thruster" in p["movements"]
    assert r.json()["job_id"] is None
    v = world.client(3).get("/api/club/program?day=2026-09-28").json()
    assert v["program"]["raw_text"] == TEXT and v["program"]["uuid"] == p["uuid"]


def test_put_replaces_keeps_uuid_idempotent(world):
    c = world.client(2)
    a = _put(c).json()["program"]
    b = _put(c).json()["program"]
    assert a["uuid"] == b["uuid"]
    d = _put(c, text="Test\nAMRAP 10\nBurpees\nDouble unders").json()["program"]
    assert d["uuid"] == a["uuid"] and d["raw_text"].startswith("Test")
    n = world.con.execute('SELECT COUNT(*) FROM wod_programs WHERE day=? AND gym=?',
                          ("2026-09-28", "Universe")).fetchone()[0]
    assert n == 1
    assert world.client(3).get("/api/club/program").json()["program"]["raw_text"].startswith("Test")


def test_put_strips_wrappers(world):
    p = _put(world.client(2), text="Программа Universe на 2026-09-28:\n\n" + TEXT).json()["program"]
    assert p["raw_text"] == TEXT


def test_put_permissions(world):
    assert _put(world.client(3)).status_code == 403                 # атлет
    assert _put(world.client(2), gym="Второй").status_code == 403   # тренер чужого зала
    assert _put(world.client(5), gym="Universe").status_code == 403  # тренер Второго -> Universe


def test_put_permissions_own_gym_ok(world):
    assert _put(world.client(5)).status_code == 200
    assert world.client(4).get("/api/club/program").json()["program"] is not None   # зал Второй
    assert world.client(3).get("/api/club/program").json()["program"] is None       # Universe пуст


def test_admin_can_manage_any_gym(world):
    r = _put(world.client(1), gym="Второй")
    assert r.status_code == 200 and r.json()["program"]["gym"] == "Второй"
    assert _put(world.client(1), gym="Нет").status_code == 404


def test_view_foreign_gym_denied_for_non_admin(world):
    assert world.client(3).get("/api/club/program?gym=Второй").status_code == 403
    assert world.client(3).get("/api/club/program?gym=Universe").status_code == 200
    assert world.client(1).get("/api/club/program?gym=Второй").status_code == 200


def test_put_validation(world):
    c = world.client(2)
    assert _put(c, day="вчера").status_code == 422
    assert _put(c, text="ab").status_code == 422
    assert _put(c, text="x" * 20001).status_code == 422
    assert c.put("/api/club/program", json={"day": "2026-09-28"}).status_code == 422
    assert world.client(3).get("/api/club/program?day=bad").status_code == 422


def test_unauthenticated(world):
    from fastapi.testclient import TestClient
    from tjapp.api import app
    c = TestClient(app)
    for m, u in (("get", "/api/club/program"), ("put", "/api/club/program"), ("get", "/api/club/pending"),
                 ("post", "/api/club/pending/1/confirm"), ("get", "/api/club/stats"),
                 ("get", "/api/club/athletes")):
        assert getattr(c, m)(u).status_code == 401


def test_unknown_movements_and_resolve(world):
    c = world.client(2)
    r = _put(c, text="AMRAP 10\n10 Подтягивания\n10 Zzyzx flips").json()
    assert any("Zzyzx" in u for u in r["unknown"])
    phrase = r["unknown"][0]
    res = c.post("/api/club/movements/resolve", json={"phrase": phrase}).json()
    assert res["created"] and res["canon"]
    r2 = _put(c, text="AMRAP 10\n10 Подтягивания\n10 Zzyzx flips").json()
    assert phrase not in r2["unknown"]
    m = c.post("/api/club/movements/resolve", json={"phrase": "щёлк", "name": "подтягивания"}).json()
    assert m["created"] is False and m["canon"]


def test_resolve_and_aliases_permissions(world):
    c = world.client(3)
    assert c.post("/api/club/movements/resolve", json={"phrase": "x"}).status_code == 403
    assert c.post("/api/club/aliases", json={"pairs": [{"alias": "a", "canon": "b"}]}).status_code == 403
    assert c.get("/api/club/dictionary").status_code == 403


def test_aliases_and_dictionary(world):
    c = world.client(2)
    assert c.post("/api/club/aliases", json={"pairs": [{"alias": " Тягуны ", "canon": "deadlift"},
                                                        {"alias": "", "canon": "x"}]}).json() == {"added": 1}
    d = {x["canon"]: x["aliases"] for x in c.get("/api/club/dictionary").json()}
    assert "тягуны" in d["deadlift"]
    assert c.post("/api/club/aliases", json={"pairs": []}).status_code == 422


def test_preview(world):
    j = world.client(2).post("/api/club/program/preview", json={"raw_text": TEXT}).json()
    assert j["raw_text"] == TEXT and j["format"] and "thruster" in j["canon"] and "annotated" in j
    assert world.con.execute("SELECT COUNT(*) FROM wod_programs").fetchone()[0] == 0   # не сохраняет
    assert world.client(3).post("/api/club/program/preview", json={"raw_text": TEXT}).status_code == 403


def test_pending_list_confirm(world):
    con = world.con
    pid = botdb.add_program(con, "2026-09-28", "Universe", "Draft\nFor time\nPull-ups", source="photo", confirmed=0)
    other = botdb.add_program(con, "2026-09-28", "Второй", "Чужой черновик", confirmed=0)
    botdb.add_program(con, "2026-09-27", "Universe", "Готовая", confirmed=1)
    coach = world.client(2)
    lst = coach.get("/api/club/pending").json()
    assert [p["id"] for p in lst] == [pid] and lst[0]["confirmed"] is False and lst[0]["uuid"]
    assert {p["id"] for p in world.client(1).get("/api/club/pending").json()} == {pid, other}
    assert [p["id"] for p in world.client(1).get("/api/club/pending?gym=Второй").json()] == [other]
    assert world.client(3).get("/api/club/pending").status_code == 403
    assert world.client(3).post(f"/api/club/pending/{pid}/confirm").status_code == 403
    assert coach.post(f"/api/club/pending/{other}/confirm").status_code == 403   # чужой зал
    assert coach.post("/api/club/pending/9999/confirm").status_code == 404
    r = coach.post(f"/api/club/pending/{pid}/confirm")
    assert r.status_code == 200 and r.json()["confirmed"] is True
    assert coach.post(f"/api/club/pending/{pid}/confirm").status_code == 200    # идемпотентно
    assert coach.get("/api/club/pending").json() == []
    assert world.client(3).get("/api/club/program").json()["program"]["id"] == pid


def test_confirm_with_edited_text_reparses(world):
    pid = botdb.add_program(world.con, "2026-09-28", "Universe", "[фото]", source="photo", confirmed=0)
    r = world.client(2).post(f"/api/club/pending/{pid}/confirm", json={"raw_text": TEXT}).json()
    assert r["raw_text"] == TEXT and "thruster" in r["movements"] and r["blocks"] is None
    assert world.client(2).post(f"/api/club/pending/{pid}/confirm", json={"raw_text": "ab"}).status_code == 422


def test_reject_draft(world):
    pid = botdb.add_program(world.con, "2026-09-28", "Universe", "Draft text", confirmed=0)
    done = botdb.add_program(world.con, "2026-09-27", "Universe", "Готовая программа", confirmed=1)
    c = world.client(2)
    assert world.client(3).delete(f"/api/club/pending/{pid}").status_code == 403
    assert c.delete(f"/api/club/pending/{done}").status_code == 409
    assert c.delete(f"/api/club/pending/{pid}").status_code == 200
    assert c.delete(f"/api/club/pending/{pid}").status_code == 404


def test_add_from_board_draft_and_confirm(world):
    d = svc.add_from_board(world.con, 2, None, TODAY, TEXT)
    assert d["confirmed"] is False and d["source"] == "photo" and d["uuid"]
    assert [p["id"] for p in svc.pending(world.con, 2)] == [d["id"]]
    assert svc.program_for_day(world.con, 3, TODAY)["program"] is None
    c = svc.add_from_board(world.con, 2, None, TODAY, TEXT, confirm=True)
    assert c["confirmed"] and svc.program_for_day(world.con, 3, TODAY)["program"]["id"] == c["id"]
    assert world.con.execute("SELECT COUNT(*) FROM wod_programs").fetchone()[0] == 1   # замена на день
    with pytest.raises(svc.ClubError) as e:
        svc.add_from_board(world.con, 3, None, TODAY, TEXT)
    assert e.value.status == 403


def test_stats(world):
    _put(world.client(2), text="For time:\n21-15-9\nТрастеры\nПодтягивания")
    _put(world.client(2), day="2026-09-27", text="AMRAP 10\n10 Подтягивания\n10 Бёрпи")
    j = world.client(3).get("/api/club/stats").json()
    assert j["gym"] == "Universe"
    by = {m["canon"]: m["count"] for m in j["movements"]}
    assert by["pull_up"] == 2 and by["thruster"] == 1
    assert all({"canon", "count", "name"} == set(m) for m in j["movements"])
    assert world.client(4).get("/api/club/stats").json()["movements"] == []       # зал Второй
    assert world.client(3).get("/api/club/stats?gym=Второй").status_code == 403


def _act(con, uid, day, sport="crossfit", source="garmin", aid=None):
    con.execute('INSERT INTO activities ("tg_id","day","sport","source","activity_id") VALUES (?,?,?,?,?)',
                (uid, day, sport, source, aid or f"{uid}{day}{sport}{source}"))
    con.commit()


def test_athletes_counts_dedup_and_period(world):
    con = world.con
    _act(con, 3, "2026-09-20")
    _act(con, 3, "2026-09-20", source="manual")           # дубль того же дня+спорта
    _act(con, 3, "2026-09-25", sport="run")
    _act(con, 3, "2026-06-01")                             # вне 30 дней
    _act(con, 4, "2026-09-20")                             # другой зал
    j = world.client(2).get("/api/club/athletes").json()
    assert j["gym"] == "Universe" and j["days"] == 30 and j["since"] == "2026-08-29"
    by = {a["id"]: a["workouts"] for a in j["athletes"]}
    assert by == {3: 2} or (by[3] == 2 and 4 not in by and 5 not in by)
    j = world.client(2).get("/api/club/athletes?days=365").json()
    assert {a["id"]: a["workouts"] for a in j["athletes"]}[3] == 3


def test_athletes_permissions(world):
    assert world.client(3).get("/api/club/athletes").status_code == 403
    assert world.client(2).get("/api/club/athletes?gym=Второй").status_code == 403
    assert world.client(1).get("/api/club/athletes?gym=Второй").status_code == 200
    assert world.client(2).get("/api/club/athletes?days=0").status_code == 422
    assert world.client(2).get("/api/club/athletes?days=366").status_code == 422


def test_verify_job_updates_blocks(world, monkeypatch):
    monkeypatch.setattr(vision, "subscription_ready", lambda e: True)
    seen = {}

    def fake_verify(text, blocks, aliases=None):
        seen["n"] = len(blocks)
        return [{**blocks[0], "verified_marker": True}], True
    monkeypatch.setattr(vision, "verify_result_blocks", fake_verify)
    c = world.client(2)
    r = _put(c).json()
    assert r["job_id"]
    j = wait_job(c, r["job_id"])
    assert j["status"] == "done" and j["result"] == {"verified": True} and seen["n"] >= 1
    p = world.client(3).get("/api/club/program").json()["program"]
    assert p["blocks_verified"] and p["blocks"][0]["verified_marker"] is True


def test_verify_job_not_verified_keeps_null(world, monkeypatch):
    monkeypatch.setattr(vision, "subscription_ready", lambda e: True)
    monkeypatch.setattr(vision, "verify_result_blocks", lambda t, b, a=None: (b, False))
    c = world.client(2)
    j = wait_job(c, _put(c).json()["job_id"])
    assert j["result"]["verified"] is False
    assert world.client(3).get("/api/club/program").json()["program"]["blocks"] is None


def test_verify_job_skips_if_replaced(world, monkeypatch):
    monkeypatch.setattr(vision, "subscription_ready", lambda e: True)
    monkeypatch.setattr(vision, "verify_result_blocks", lambda t, b, a=None: (b, True))
    pid = _put(world.client(2)).json()["program"]["id"]
    _put(world.client(2), text="Другой текст\nAMRAP 5\nBurpees")          # заменили: строка pid удалена
    assert svc.verify_blocks(botdb.default_db_path(), pid) == {"verified": False, "reason": "programme gone"}


def test_bot_written_program_gets_uuid_lazily(world):
    botdb.add_program(world.con, "2026-09-28", "Universe", "Программа от бота", confirmed=1)
    p = world.client(3).get("/api/club/program").json()["program"]
    assert p["uuid"]
    assert world.client(3).get("/api/club/program").json()["program"]["uuid"] == p["uuid"]


def test_slug_and_wrappers_units():
    assert svc.slug("Ring Muscle-Up!") == "ring_muscle_up" and svc.slug("!!!") == ""
    assert svc.strip_wrappers("Программа:\n\nТекущая программа:\nabc") == "abc"
    assert svc.strip_wrappers("Gym program Foo:\nabc") == "abc"
