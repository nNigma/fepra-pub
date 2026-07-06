from fastapi.testclient import TestClient
from tjbot import db as botdb
from tjapp import api
from tjapp.api import app, require_auth


def _setup(tmp_path, monkeypatch, admin: bool):
    dbp = tmp_path / "t.db"
    con = botdb.connect(dbp); botdb.init_schema(con)
    botdb.save_user(con, 111, nick="Аня", height_cm=170, weight_kg=60, sex="f", age=30, gym="U")
    con.close()
    monkeypatch.setattr(api, "_db", lambda: str(dbp))
    monkeypatch.setattr(api, "is_admin", lambda tg: admin)
    app.dependency_overrides[require_auth] = lambda: {"id": 900}
    return TestClient(app)


def test_users_admin_ok(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, admin=True)
    r = c.get("/api/users")
    assert r.status_code == 200 and any(u["tg_id"] == 111 for u in r.json())
    app.dependency_overrides.clear()


def test_users_non_admin_403(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, admin=False)
    r = c.get("/api/users")
    assert r.status_code == 403
    app.dependency_overrides.clear()
