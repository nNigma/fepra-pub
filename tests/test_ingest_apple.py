import json
import pytest
from fastapi.testclient import TestClient

from test_apple_health_mapper import PAYLOAD


@pytest.fixture
def client_token_db(tmp_path, monkeypatch):
    dbp = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(dbp))
    from tjbot import db
    con = db.connect(dbp)
    db.init_schema(con)
    con.close()
    from tjapp.api import app
    return TestClient(app), dbp


def test_apple_401_without_token(client_token_db):
    client, dbp = client_token_db
    r = client.post("/ingest/apple", json={})
    assert r.status_code == 401


def test_apple_403_wrong_provider_token(client_token_db):
    client, dbp = client_token_db
    from tjbot import db
    con = db.connect(dbp)
    token = db.issue_watch_token(con, 1, "samsung")
    con.close()
    r = client.post("/ingest/apple", json={"data": {}},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_apple_400_bad_json(client_token_db):
    client, dbp = client_token_db
    from tjbot import db
    con = db.connect(dbp)
    token = db.issue_watch_token(con, 1, "apple")
    con.close()
    r = client.post("/ingest/apple", content="не json".encode("utf-8"),
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"})
    assert r.status_code == 400


def test_apple_first_post_writes_and_connects(client_token_db):
    client, dbp = client_token_db
    from tjbot import db
    con = db.connect(dbp)
    token = db.issue_watch_token(con, 1, "apple")
    con.close()

    r = client.post("/ingest/apple", json=PAYLOAD,
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"days_written": 1, "activities_written": 2}

    con = db.connect(dbp)
    acc = db.watch_account_get(con, 1, "apple")
    assert acc["status"] == "connected"
    assert acc["last_sync_at"]

    row = con.execute('SELECT * FROM daily WHERE tg_id=1').fetchone()
    assert row["sleep_h"] == 7.4
    assert row["resting_hr"] == 47

    run = con.execute('SELECT * FROM activities WHERE tg_id=1 AND activity_id=?',
                      ("apple-ABC-123",)).fetchone()
    assert run is not None
    assert run["source"] == "apple"
    extra = json.loads(run["extra"]) if run["extra"] else {}
    assert extra.get("hr_series_ref") == "data/hr_1_apple-ABC-123.json"
    assert "_hr_series" not in extra
    con.close()

    assert (dbp.parent / "data" / "hr_1_apple-ABC-123.json").exists()


def test_apple_repeat_post_no_dupes(client_token_db):
    client, dbp = client_token_db
    from tjbot import db
    con = db.connect(dbp)
    token = db.issue_watch_token(con, 1, "apple")
    con.close()

    h = {"Authorization": f"Bearer {token}"}
    client.post("/ingest/apple", json=PAYLOAD, headers=h)
    client.post("/ingest/apple", json=PAYLOAD, headers=h)

    con = db.connect(dbp)
    assert con.execute("SELECT COUNT(*) c FROM activities WHERE tg_id=1").fetchone()["c"] == 2
    assert con.execute("SELECT COUNT(*) c FROM daily WHERE tg_id=1").fetchone()["c"] == 1
    con.close()
