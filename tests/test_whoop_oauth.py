import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_state(tmp_path, monkeypatch):
    dbp = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(dbp))
    from tjbot import db
    con = db.connect(dbp)
    db.init_schema(con)
    st = db.oauth_state_issue(con, 111, "whoop")
    con.close()
    from tjapp.api import app
    return TestClient(app), st, dbp


def test_callback_happy(client_state, monkeypatch):
    client, st, dbp = client_state
    from tjapp import whoop_oauth
    monkeypatch.setattr(whoop_oauth, "_exchange_code", lambda code: {
        "access_token": "A", "refresh_token": "R",
        "expires_at": "2026-07-11T12:00:00+00:00"})
    r = client.get(f"/whoop/callback?code=C&state={st}")
    assert r.status_code == 200
    assert "Whoop" in r.text
    from tjbot import db
    con = db.connect(dbp)
    assert db.whoop_tokens_get(con, 111)["access_token"] == "A"
    assert db.watch_account_get(con, 111, "whoop")["status"] == "connected"
    con.close()


def test_callback_bad_state(client_state):
    client, st, dbp = client_state
    assert client.get("/whoop/callback?code=C&state=nope").status_code == 400


def test_callback_state_single_use(client_state, monkeypatch):
    client, st, dbp = client_state
    from tjapp import whoop_oauth
    monkeypatch.setattr(whoop_oauth, "_exchange_code", lambda code: {
        "access_token": "A", "refresh_token": "R",
        "expires_at": "2026-07-11T12:00:00+00:00"})
    assert client.get(f"/whoop/callback?code=C&state={st}").status_code == 200
    assert client.get(f"/whoop/callback?code=C&state={st}").status_code == 400
