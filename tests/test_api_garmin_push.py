"""Роуты garmin / notices / push (TestClient, Garmin и сеть замоканы)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tj.services import garmin as gsvc
from tj.services import jobs, notices, push
from tjapp.api import app
from tjapp.deps import require_user
from tjapp.routes import ALL_ROUTERS, garmin as garmin_routes
from tjbot import db as botdb

PW = "s3cret-Passw0rd!"


class FakeAdapter:
    def __init__(self, mode, prompt_mfa):
        self.mode, self.prompt_mfa = mode, prompt_mfa

    def _login(self):
        if self.mode == "mfa" and self.prompt_mfa() != "123456":
            raise PermissionError(PW)
        if self.mode == "fail":
            raise ValueError(PW)
        return object()


@pytest.fixture
def env(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    for k in ("FEPRA_VAPID_PRIVATE", "FEPRA_VAPID_PUBLIC"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("tj.config.load_dotenv", lambda q: {})
    con = botdb.connect(p)
    botdb.init_schema(con)
    mode = {"m": "ok"}
    monkeypatch.setattr(gsvc, "adapter_factory",
                        lambda e, pw, t, pm: FakeAdapter(mode["m"], pm))
    garmin_routes.login_limiter.reset()
    garmin_routes.mfa_limiter.reset()
    app.dependency_overrides[require_user] = lambda: {"id": 1}
    with gsvc._lock:
        gsvc._sessions.clear()
    yield TestClient(app), con, mode
    app.dependency_overrides.clear()
    con.close()


def test_routers_registered():
    paths = {r.path for rt in ALL_ROUTERS for r in rt.routes}
    assert {"/api/garmin/status", "/api/garmin/login", "/api/garmin/mfa", "/api/garmin/sync",
            "/api/garmin/history", "/api/garmin/disconnect", "/api/notices",
            "/api/notices/{notice_id}/read", "/api/push/key", "/api/push/subscribe",
            "/api/push/unsubscribe"} <= paths


def test_auth_required(env):
    app.dependency_overrides.clear()
    c = TestClient(app)
    for m, u in [("get", "/api/garmin/status"), ("post", "/api/garmin/login"),
                 ("get", "/api/notices"), ("get", "/api/push/key")]:
        assert getattr(c, m)(u).status_code == 401


def test_login_ok_no_password_leak(env, capsys):
    c, con, _ = env
    r = c.post("/api/garmin/login", json={"email": "a@b.c", "password": PW})
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert PW not in r.text
    st = c.get("/api/garmin/status").json()
    assert st["connected"] and st["email"] == "a@b.c"
    out = capsys.readouterr()
    assert PW not in out.out + out.err


def test_login_mfa_and_error_no_leak(env, capsys):
    c, con, mode = env
    mode["m"] = "mfa"
    r = c.post("/api/garmin/login", json={"email": "a@b.c", "password": PW})
    assert r.json()["status"] == "need_mfa"
    r = c.post("/api/garmin/mfa", json={"code": "000000"})
    assert r.json()["status"] == "error" and PW not in r.text
    mode["m"] = "fail"
    r = c.post("/api/garmin/login", json={"email": "a@b.c", "password": PW})
    assert r.json()["status"] == "error" and PW not in r.text
    out = capsys.readouterr()
    assert PW not in out.out + out.err
    r = c.post("/api/garmin/mfa", json={"code": "123456"})   # сессии уже нет
    assert r.json()["status"] == "error"


def test_login_validation_and_ratelimit(env):
    c, _, mode = env
    assert c.post("/api/garmin/login", json={"email": "a@b.c"}).status_code == 422
    mode["m"] = "fail"
    codes = [c.post("/api/garmin/login", json={"email": "a@b.c", "password": PW}).status_code
             for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429
    app.dependency_overrides[require_user] = lambda: {"id": 2}     # лимит по пользователю
    assert c.post("/api/garmin/login", json={"email": "a@b.c", "password": PW}).status_code == 200


def test_sync_requires_account(env):
    c, _, _ = env
    assert c.post("/api/garmin/sync").status_code == 409


def test_sync_job_and_owner_check(env, monkeypatch):
    c, con, _ = env
    botdb.garmin_account_set(con, 1, "a@b.c")
    monkeypatch.setattr(gsvc, "sync_recent", lambda uid: {"days": 2})
    jid = c.post("/api/garmin/sync").json()["job_id"]
    for t in __import__("threading").enumerate():
        if t.name.startswith("job-"):
            t.join(5)
    r = c.get(f"/api/jobs/{jid}")
    assert r.json()["status"] == "done" and r.json()["result"] == {"days": 2}
    app.dependency_overrides[require_user] = lambda: {"id": 2}
    assert c.get(f"/api/jobs/{jid}").status_code == 404


def test_history_days_validation_and_dedupe_running(env, monkeypatch):
    c, con, _ = env
    botdb.garmin_account_set(con, 1, "a@b.c")
    assert c.post("/api/garmin/history", json={"days": 0}).status_code == 422
    assert c.post("/api/garmin/history", json={"days": 999}).status_code == 422
    running = jobs.create_job(con, "garmin_sync", 1)
    jobs.set_running(con, running)
    assert c.post("/api/garmin/history", json={"days": 30}).json() == {"job_id": running}
    assert c.post("/api/garmin/sync").json() == {"job_id": running}


def test_disconnect(env):
    c, con, _ = env
    c.post("/api/garmin/login", json={"email": "a@b.c", "password": PW})
    assert c.post("/api/garmin/disconnect").json() == {"ok": True}
    assert c.get("/api/garmin/status").json()["status"] == "none"


def test_notices_owner_only(env):
    c, con, _ = env
    nid = notices.add(con, 1, "k", "hello")
    other = notices.add(con, 2, "k", "чужое")
    lst = c.get("/api/notices").json()
    assert [n["id"] for n in lst] == [nid]
    assert c.post(f"/api/notices/{other}/read").status_code == 404
    assert c.post("/api/notices/nope/read").status_code == 404
    assert c.post(f"/api/notices/{nid}/read").json() == {"ok": True}
    assert c.get("/api/notices?unread=true").json() == []
    assert len(c.get("/api/notices").json()) == 1


def test_push_key_and_subscribe(env, monkeypatch):
    c, con, _ = env
    assert c.get("/api/push/key").status_code == 503
    monkeypatch.setenv("FEPRA_VAPID_PUBLIC", "PUBKEY")
    monkeypatch.setenv("FEPRA_VAPID_PRIVATE", "PRIV")
    r = c.get("/api/push/key")
    assert r.json() == {"public_key": "PUBKEY"} and "PRIV" not in r.text
    body = {"endpoint": "https://push.example/x", "keys": {"p256dh": "p", "auth": "a"}}
    assert c.post("/api/push/subscribe", json=body).status_code == 200
    assert c.post("/api/push/subscribe", json=body).status_code == 200
    assert len(push.subscriptions(con, 1)) == 1
    assert c.post("/api/push/subscribe",
                  json={**body, "endpoint": "http://insecure/x"}).status_code == 422
    assert c.post("/api/push/subscribe", json={"endpoint": "https://x"}).status_code == 422
    app.dependency_overrides[require_user] = lambda: {"id": 2}
    assert c.post("/api/push/unsubscribe", json={"endpoint": body["endpoint"]}).json() == {"ok": False}
    app.dependency_overrides[require_user] = lambda: {"id": 1}
    assert c.post("/api/push/unsubscribe", json={"endpoint": body["endpoint"]}).json() == {"ok": True}
    assert push.subscriptions(con, 1) == []
