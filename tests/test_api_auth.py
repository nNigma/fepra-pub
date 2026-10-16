from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tj.services import auth
from tjapp import deps
from tjapp.api import app, require_auth
from tjapp.deps import require_admin, require_pro, require_user
from tjapp.routes import ALL_ROUTERS, auth as auth_routes
from tjbot import access, db as botdb


@pytest.fixture
def env(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    monkeypatch.setenv("FEPRA_PUBLIC_URL", "https://fepra.example")
    con = botdb.connect(p)
    botdb.init_schema(con)
    auth_routes.redeem_limiter.reset()
    auth_routes.login_limiter.reset()
    yield con
    con.close()
    app.dependency_overrides.clear()


def _admin_client(con):
    """Админ без Telegram: первый инвайт, как через CLI."""
    tok = auth.create_invite(con, None, "admin")
    c = TestClient(app)
    r = c.post("/api/auth/redeem", json={"token": tok, "nick": "Root"})
    assert r.status_code == 200, r.text
    return c, r.json()


def test_require_auth_is_require_user():
    assert require_auth is require_user


def test_all_routers_registered():
    paths = {r.path for rt in ALL_ROUTERS for r in rt.routes}
    assert {"/api/me", "/api/auth/redeem", "/api/admin/invites", "/api/jobs/{job_id}",
            "/api/auth/logout", "/api/auth/passkey/login/options"} <= paths


def test_me_requires_login(env):
    assert TestClient(app).get("/api/me").status_code == 401


def test_redeem_sets_cookie_and_me_works(env):
    c, me = _admin_client(env)
    assert me["roles"]["admin"] is True and me["id"] >= auth.WEB_ID_BASE and me["nick"] == "Root"
    assert c.get("/api/me").json() == me
    assert me["public_url"] == "https://fepra.example"


def test_cookie_flags(env):
    tok = auth.create_invite(env, None, "user")
    c = TestClient(app)
    r = c.post("/api/auth/redeem", json={"token": tok, "nick": "A"},
               headers={"x-forwarded-proto": "https"})
    sc = r.headers["set-cookie"].lower()
    assert "fepra_session=" in sc and "httponly" in sc and "samesite=lax" in sc and "secure" in sc
    tok = auth.create_invite(env, None, "user")
    r = c.post("/api/auth/redeem", json={"token": tok, "nick": "B"})  # http на testserver
    assert "secure" not in r.headers["set-cookie"].lower()


def test_redeem_errors(env):
    c = TestClient(app)
    assert c.post("/api/auth/redeem", json={"token": "bad", "nick": "x"}).status_code == 400
    tok = auth.create_invite(env, None, "user")
    assert c.post("/api/auth/redeem", json={"token": tok, "nick": ""}).status_code == 422
    assert c.post("/api/auth/redeem", json={"token": tok, "nick": "ok"}).status_code == 200
    assert c.post("/api/auth/redeem", json={"token": tok, "nick": "ok"}).status_code == 400


def test_redeem_rate_limited(env):
    c = TestClient(app)
    codes = [c.post("/api/auth/redeem", json={"token": "bad", "nick": "x"}).status_code for _ in range(12)]
    assert codes[:10] == [400] * 10 and codes[10:] == [429, 429]


def test_login_options_rate_limited(env):
    c = TestClient(app)
    codes = [c.post("/api/auth/passkey/login/options").status_code for _ in range(22)]
    assert codes[:20] == [200] * 20 and codes[20:] == [429, 429]


def test_rate_limit_uses_forwarded_ip_behind_proxy(env):
    class R:
        client = SimpleNamespace(host="127.0.0.1")
        headers = {"x-forwarded-for": "9.9.9.9, 1.2.3.4"}
    assert deps.client_ip(R()) == "1.2.3.4"


def test_logout_revokes(env):
    c, _ = _admin_client(env)
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/me").status_code == 401


def test_removed_from_allowlist_loses_session(env):
    c, me = _admin_client(env)
    env.execute("DELETE FROM user_roles WHERE user_id=? AND role='allowlist'", (me["id"],))
    env.commit()
    assert c.get("/api/me").status_code == 401


def test_invites_admin_only_and_flow(env):
    c, admin = _admin_client(env)
    r = c.post("/api/admin/invites", json={"role": "pro", "ttl_hours": 24, "note": "Маша"})
    assert r.status_code == 200
    body = r.json()
    assert body["url"] == f"https://fepra.example/app/#/invite/{body['token']}"
    lst = c.get("/api/admin/invites").json()
    assert len(lst) == 2 and lst[0]["note"] == "Маша" and lst[0]["status"] == "active"
    assert all("token" not in i for i in lst)
    # обычный пользователь — 403
    u = TestClient(app)
    u.post("/api/auth/redeem", json={"token": body["token"], "nick": "Маша"})
    assert u.get("/api/me").json()["roles"]["pro"] is True
    assert u.post("/api/admin/invites", json={}).status_code == 403
    assert u.get("/api/admin/invites").status_code == 403
    assert TestClient(app).post("/api/admin/invites", json={}).status_code == 401


def test_invite_validation_errors(env):
    c, _ = _admin_client(env)
    assert c.post("/api/admin/invites", json={"role": "god"}).status_code == 400
    assert c.post("/api/admin/invites", json={"role": "coach"}).status_code == 400
    assert c.post("/api/admin/invites", json={"existing_user_id": 1}).status_code == 400


def test_link_existing_telegram_account(env):
    botdb.save_user(env, 111, nick="Аня", height_cm=None, weight_kg=None, sex="f", gym=None)
    access.add_user(111)
    c, _ = _admin_client(env)
    tok = c.post("/api/admin/invites", json={"existing_user_id": 111}).json()["token"]
    u = TestClient(app)
    me = u.post("/api/auth/redeem", json={"token": tok}).json()
    assert me["id"] == 111 and me["nick"] == "Аня"


def test_initdata_header_still_works(env, monkeypatch):
    monkeypatch.setattr(deps.tg_auth, "authorized_user", lambda s: {"id": 111, "first_name": "A"})
    botdb.save_user(env, 111, nick="Аня", height_cm=None, weight_kg=None, sex="f", gym=None)
    r = TestClient(app).get("/api/me", headers={"X-Init-Data": "whatever"})
    assert r.status_code == 200 and r.json()["id"] == 111


def test_initdata_bad_is_401(env):
    def bad(s):
        raise deps.tg_auth.AuthError("подпись")
    import tjapp.deps as d
    d.tg_auth.authorized_user, orig = bad, d.tg_auth.authorized_user
    try:
        assert TestClient(app).get("/api/me", headers={"X-Init-Data": "x"}).status_code == 401
    finally:
        d.tg_auth.authorized_user = orig


def test_require_pro_admin_and_effective_user(env):
    access.add_user(1); access.add_user(2); access.add_pro(2); access.add_admin(3); access.add_user(3)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        require_pro({"id": 1})
    assert e.value.status_code == 403
    assert require_pro({"id": 2}) and require_pro({"id": 3})
    with pytest.raises(HTTPException):
        require_admin({"id": 2})
    assert require_admin({"id": 3})
    assert deps.resolve_effective_user({"id": 3}, 1) == 1      # админ, цель в allowlist
    assert deps.resolve_effective_user({"id": 2}, 1) == 2      # не админ — игнор ?as=
    assert deps.resolve_effective_user({"id": 3}, None) == 3


def test_passkey_endpoints_with_mocked_verification(env, monkeypatch):
    c, me = _admin_client(env)
    monkeypatch.setattr(auth, "verify_registration_response",
                        lambda **kw: SimpleNamespace(credential_id=b"c1", credential_public_key=b"K", sign_count=0))
    monkeypatch.setattr(auth, "verify_authentication_response",
                        lambda **kw: SimpleNamespace(new_sign_count=1))
    o = c.post("/api/auth/passkey/register/options").json()
    r = c.post("/api/auth/passkey/register/verify",
               json={"challenge_id": o["challenge_id"], "credential": {"id": "x"}, "name": "Mac"})
    assert r.status_code == 200 and c.get("/api/me").json()["has_passkey"] is True
    # повтор того же challenge
    assert c.post("/api/auth/passkey/register/verify",
                  json={"challenge_id": o["challenge_id"], "credential": {"id": "x"}}).status_code == 400
    # вход без сессии
    cred = auth.bytes_to_base64url(b"c1")
    anon = TestClient(app)
    lo = anon.post("/api/auth/passkey/login/options").json()
    r = anon.post("/api/auth/passkey/login/verify",
                  json={"challenge_id": lo["challenge_id"], "credential": {"id": cred}})
    assert r.status_code == 200 and r.json()["id"] == me["id"]
    assert anon.get("/api/me").status_code == 200
    # регистрация требует сессию
    assert TestClient(app).post("/api/auth/passkey/register/options").status_code == 401


def test_startup_lifespan_builds_schema(tmp_path, monkeypatch):
    p = tmp_path / "fresh.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    with TestClient(app):
        pass
    con = botdb.connect(p)
    assert con.execute("SELECT name FROM sqlite_master WHERE name='sessions'").fetchone()
    con.close()
