"""Админка: сервис и роуты /api/admin/* (users, roles, gyms, coaches, stats, review)."""
from datetime import datetime, timezone

import pytest

from p5a_env import p5a, wait_job  # noqa: F401
from tj import llm
from tj.services import admin as svc
from tjbot import access, claude_review, db as botdb


@pytest.fixture
def world(p5a):
    p5a.user(1, "Босс", admin=True)
    p5a.user(2, "Про", pro=True)
    p5a.user(3, "Обычный")
    return p5a


ADMIN_URLS = [("get", "/api/admin/users"), ("put", "/api/admin/users/3/roles"),
              ("delete", "/api/admin/users/3"), ("get", "/api/admin/gyms"),
              ("post", "/api/admin/gyms"), ("get", "/api/admin/coaches"),
              ("post", "/api/admin/coaches"), ("delete", "/api/admin/coaches/3"),
              ("get", "/api/admin/stats"), ("post", "/api/admin/review")]


@pytest.mark.parametrize("who", [None, 2, 3])
def test_non_admin_denied(world, who):
    from fastapi.testclient import TestClient
    from tjapp.api import app
    c = TestClient(app) if who is None else world.client(who)
    for m, u in ADMIN_URLS:
        r = getattr(c, m)(u, **({"json": {}} if m in ("put", "post") else {}))
        assert r.status_code == (401 if who is None else 403), (m, u, r.status_code)


def test_coach_is_not_admin(world):
    world.user(4, "Тренер", coach="Universe")
    assert world.client(4).get("/api/admin/users").status_code == 403


def test_list_users_with_roles(world):
    world.user(4, "Тренер", coach="Universe")
    users = {u["id"]: u for u in world.client(1).get("/api/admin/users").json()}
    assert users[1]["roles"]["admin"] and users[2]["roles"]["pro"] and not users[3]["roles"]["pro"]
    assert users[4]["roles"]["coach_gym"] == "Universe" and users[3]["nick"] == "Обычный"
    q = world.client(1).get("/api/admin/users?q=про").json()
    assert [u["id"] for u in q] == [2]


def test_list_includes_role_holder_without_profile(world):
    world.user(9, profile=False)
    assert 9 in {u["id"] for u in world.client(1).get("/api/admin/users").json()}


def test_grant_and_revoke_roles(world):
    c = world.client(1)
    r = c.put("/api/admin/users/3/roles", json={"pro": True})
    assert r.status_code == 200 and r.json()["roles"]["pro"] is True and access.is_pro(3)
    c.put("/api/admin/users/3/roles", json={"pro": False})
    assert not access.is_pro(3)
    r = c.put("/api/admin/users/3/roles", json={"coach": "Universe"})
    assert r.json()["roles"]["coach_gym"] == "Universe" and access.coach_gym(3) == "Universe"
    c.put("/api/admin/users/3/roles", json={"coach": None})
    assert not access.is_coach(3)


def test_roles_validation(world):
    c = world.client(1)
    assert c.put("/api/admin/users/3/roles", json={}).status_code == 422
    assert c.put("/api/admin/users/3/roles", json={"pro": "yes"}).status_code == 422
    assert c.put("/api/admin/users/3/roles", json={"root": True}).status_code == 422
    assert c.put("/api/admin/users/3/roles", json={"coach": "Нет"}).status_code == 422
    assert c.put("/api/admin/users/9999/roles", json={"pro": True}).status_code == 404


def test_grant_admin_also_allowlist(world):
    world.user(5, "Новый", allowed=False)
    world.client(1).put("/api/admin/users/5/roles", json={"admin": True})
    assert access.is_admin(5) and access.is_allowed(5)


def test_cannot_demote_last_admin(world):
    r = world.client(1).put("/api/admin/users/1/roles", json={"admin": False})
    assert r.status_code == 409 and "последн" in r.json()["detail"]
    assert access.is_admin(1)


def test_can_demote_admin_when_another_exists(world):
    world.user(6, "Второй", admin=True)
    r = world.client(1).put("/api/admin/users/6/roles", json={"admin": False})
    assert r.status_code == 200 and not access.is_admin(6)
    # а теперь 1 — снова последний
    assert world.client(1).put("/api/admin/users/1/roles", json={"admin": False}).status_code == 409


def test_last_admin_also_blocked_by_combined_request(world):
    r = world.client(1).put("/api/admin/users/1/roles", json={"admin": False, "pro": True})
    assert r.status_code == 409 and not access.is_pro(1)      # ничего не применилось


def test_cannot_drop_allowlist_of_admin(world):
    r = world.client(1).put("/api/admin/users/1/roles", json={"allowlist": False})
    assert r.status_code == 409 and access.is_allowed(1)


def test_remove_access(world):
    from tj.services import auth
    world.user(4, "Тренер", pro=True, coach="Universe")
    sess = auth.create_session(world.con, 4)
    r = world.client(1).delete("/api/admin/users/4")
    assert r.status_code == 200
    assert not access.is_allowed(4) and not access.is_pro(4) and not access.is_coach(4)
    assert auth.validate_session(world.con, sess) is None
    assert botdb.get_user(world.con, 4) is not None          # история остаётся


def test_cannot_remove_admin_or_unknown(world):
    assert world.client(1).delete("/api/admin/users/1").status_code == 409
    assert world.client(1).delete("/api/admin/users/9999").status_code == 404


def test_gyms_add_and_list(world):
    c = world.client(1)
    r = c.post("/api/admin/gyms", json={"name": "  Very Long Gym Name " + "я" * 30})
    assert r.status_code == 201       # больше нет лимита 64 байт callback_data
    assert c.post("/api/admin/gyms", json={"name": "Universe"}).status_code == 409
    assert c.post("/api/admin/gyms", json={"name": "universe"}).status_code == 409
    assert c.post("/api/admin/gyms", json={"name": "Solo"}).status_code == 422
    assert c.post("/api/admin/gyms", json={"name": "a\nb"}).status_code == 422
    assert c.post("/api/admin/gyms", json={"name": "я" * 61}).status_code == 422
    assert c.post("/api/admin/gyms", json={"name": "   "}).status_code == 422
    names = [g["name"] for g in c.get("/api/admin/gyms").json()]
    assert names[0] == "Universe" and len(names) == 2


def test_gyms_show_members_and_coaches(world):
    world.user(4, "Тренер", coach="Universe")
    g = world.client(1).get("/api/admin/gyms").json()[0]
    assert g["members"] == 4 and g["coaches"] == [{"id": 4, "nick": "Тренер"}]


def test_coaches_assign_revoke(world):
    c = world.client(1)
    botdb.add_gym(world.con, "Второй")
    r = c.post("/api/admin/coaches", json={"user_id": 3, "gym": "Второй"})
    assert r.status_code == 200 and r.json() == {"id": 3, "nick": "Обычный", "gym": "Второй", "gyms": ["Второй"]}
    assert c.get("/api/admin/coaches").json() == [{"id": 3, "nick": "Обычный", "gym": "Второй", "gyms": ["Второй"]}]
    assert c.post("/api/admin/coaches", json={"user_id": 3, "gym": "Нет"}).status_code == 422
    assert c.post("/api/admin/coaches", json={"user_id": 9999, "gym": "Второй"}).status_code == 404
    assert c.delete("/api/admin/coaches/3").status_code == 200
    assert c.delete("/api/admin/coaches/3").status_code == 404


def test_stats_data_not_text(world):
    now = datetime(2026, 9, 28, tzinfo=timezone.utc)
    botdb.log_action(world.con, 3, "workout_recorded", "2026-09-27T10:00:00")
    botdb.log_action(world.con, 3, "meal_added", "2026-09-27T11:00:00")
    botdb.log_action(world.con, 2, "workout_recorded", "2026-08-01T10:00:00")
    s = svc.stats(world.con, 30, now=now)
    assert s["total"] == 2 and [u["id"] for u in s["users"]] == [3]
    u = s["users"][0]
    assert u["nick"] == "Обычный" and u["total"] == 2
    assert {"key": "workout_recorded", "label": "Тренировка", "n": 1} in u["actions"]
    assert svc.stats(world.con, None, now=now)["total"] == 3


def test_stats_route(world):
    botdb.log_action(world.con, 3, "workout_recorded")
    c = world.client(1)
    j = c.get("/api/admin/stats?days=7").json()
    assert j["days"] == 7 and j["total"] == 1
    assert c.get("/api/admin/stats").json()["days"] is None
    assert c.get("/api/admin/stats?days=-1").status_code == 422
    assert c.get("/api/admin/stats?days=999999").status_code == 422


def test_review_job_and_busy_flag(world, monkeypatch):
    import threading
    gate = threading.Event()

    def run_all(db_path=None):
        gate.wait(5)
        return [{"tg_id": 2, "days": [{"ok": True}, {"skip": "x"}, {"error": "llm"}], "summary": True}]
    monkeypatch.setattr(claude_review, "run_all", run_all)
    monkeypatch.setattr(llm, "has_text_llm", lambda: True)
    c = world.client(1)
    r1 = c.post("/api/admin/review").json()
    assert r1["already_running"] is False
    r2 = c.post("/api/admin/review").json()
    assert r2 == {"job_id": r1["job_id"], "already_running": True}
    gate.set()
    j = wait_job(c, r1["job_id"])
    assert j["status"] == "done"
    assert j["result"] == {"ok": True, "error": None,
                           "users": [{"id": 2, "ok": 1, "skipped": 1, "errors": 1, "summary": True}]}
    assert c.post("/api/admin/review").json()["already_running"] is False   # прогон окончен


def test_review_without_llm(world, monkeypatch):
    monkeypatch.setattr(llm, "has_text_llm", lambda: False)
    assert world.client(1).post("/api/admin/review").status_code == 503


def test_review_run_all_error_summary():
    assert svc.summarize_review([{"error": "LLM недоступен"}]) == {
        "ok": False, "error": "LLM недоступен", "users": []}
