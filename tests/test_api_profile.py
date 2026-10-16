"""Роуты /api/profile, /api/gyms, /api/onboarding."""
from p5a_env import p5a  # noqa: F401
from fastapi.testclient import TestClient
from tj.services import auth
from tjapp.api import app
from tjbot import db as botdb


def test_requires_login(p5a):
    c = TestClient(app)
    for m, u in (("get", "/api/profile"), ("patch", "/api/profile"), ("get", "/api/gyms"),
                 ("get", "/api/onboarding")):
        assert getattr(c, m)(u).status_code == 401


def test_get_profile(p5a):
    p5a.user(10, "Вася")
    r = p5a.client(10).get("/api/profile")
    assert r.status_code == 200
    j = r.json()
    assert j["id"] == 10 and j["nick"] == "Вася" and "available_watch_actions" in j


def test_get_profile_404_without_row(p5a):
    p5a.user(11, profile=False)
    assert p5a.client(11).get("/api/profile").status_code == 404


def test_patch_and_own_only(p5a):
    p5a.user(10, "Вася")
    p5a.user(20, "Петя")
    r = p5a.client(10).patch("/api/profile", json={"height_cm": 190, "city": "Казань"})
    assert r.status_code == 200 and r.json()["height_cm"] == 190
    assert p5a.client(20).get("/api/profile").json()["height_cm"] == 180   # чужой не тронут


def test_patch_validation_json_errors(p5a):
    p5a.user(10)
    r = p5a.client(10).patch("/api/profile", json={"height_cm": 5, "sex": "z"})
    assert r.status_code == 422
    j = r.json()
    assert isinstance(j["detail"], str) and set(j["fields"]) == {"height_cm", "sex"}


def test_patch_ignores_asuser(p5a):
    """?as= для профиля не работает даже у админа: правится только свой."""
    p5a.user(1, admin=True)
    p5a.user(20, "Петя")
    p5a.client(1).patch("/api/profile?as=20", json={"age": 40})
    assert p5a.client(20).get("/api/profile").json()["age"] == 30


def test_gyms_endpoint(p5a):
    p5a.user(10)
    botdb.add_gym(p5a.con, "Второй")
    j = p5a.client(10).get("/api/gyms").json()
    assert [g["name"] for g in j["gyms"]] == ["Universe", "Второй"] and j["special"] == ["solo", "other"]


def test_onboarding_flow_for_web_user(p5a):
    uid = auth.create_web_user(p5a.con, "Веб")
    c = p5a.client(uid)
    assert c.get("/api/onboarding").json()["complete"] is False
    r = c.patch("/api/profile", json={"height_cm": 170, "weight_kg": 60, "sex": "f", "age": 22,
                                      "gym": "Universe"})
    assert r.status_code == 200
    assert c.get("/api/onboarding").json() == {**c.get("/api/onboarding").json(), "complete": True,
                                               "missing": []}
