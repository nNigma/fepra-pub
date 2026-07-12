import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_token_db(tmp_path, monkeypatch):
    dbp = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(dbp))
    from tjbot import db
    con = db.connect(dbp)
    db.init_schema(con)
    raw = db.issue_watch_token(con, 111, "samsung")
    con.close()
    from tjapp.api import app
    return TestClient(app), raw, dbp


def test_verify_and_ingest_idempotent(client_token_db):
    client, raw, dbp = client_token_db
    h = {"Authorization": f"Bearer {raw}"}
    assert client.post("/ingest/samsung/verify", headers=h).json() == {"ok": True}

    body = {"provider": "samsung",
            "days": [{"day": "2026-07-09", "sleep_h": 7.0, "resting_hr": 50}],
            "activities": [{"activity_id": "hc-1", "sport": "run",
                            "start": "2026-07-09T07:00:00+03:00", "duration_min": 30,
                            "hr_series": [[0, 120], [5, 130]]}]}
    r = client.post("/ingest/samsung", headers=h, json=body).json()
    assert r == {"days_written": 1, "activities_written": 1}

    from tjbot import db
    con = db.connect(dbp)
    assert con.execute("SELECT COUNT(*) c FROM daily WHERE tg_id=111").fetchone()["c"] == 1
    assert con.execute("SELECT COUNT(*) c FROM activities WHERE tg_id=111").fetchone()["c"] == 1
    row = con.execute("SELECT extra FROM activities WHERE tg_id=111").fetchone()
    assert json.loads(row["extra"]).get("hr_series_ref") == "data/hr_111_hc-1.json"
    assert con.execute("SELECT status FROM watch_accounts WHERE tg_id=111").fetchone()["status"] == "connected"
    con.close()

    assert (dbp.parent / "data" / "hr_111_hc-1.json").exists()

    # idempotent re-POST -> still one activity, one day
    client.post("/ingest/samsung", headers=h, json=body)
    con = db.connect(dbp)
    assert con.execute("SELECT COUNT(*) c FROM activities WHERE tg_id=111").fetchone()["c"] == 1
    assert con.execute("SELECT COUNT(*) c FROM daily WHERE tg_id=111").fetchone()["c"] == 1
    con.close()


def test_bad_token_401(client_token_db):
    client, raw, dbp = client_token_db
    assert client.post("/ingest/samsung/verify", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post("/ingest/samsung", headers={}, json={}).status_code == 401


def test_malformed_bearer_header_401(client_token_db):
    client, raw, dbp = client_token_db
    for hdr in ("Bearer ", "Bearer", "Basic xxx"):
        assert client.post("/ingest/samsung/verify",
                           headers={"Authorization": hdr}).status_code == 401


def test_bad_json_body_400(client_token_db):
    client, raw, dbp = client_token_db
    h = {"Authorization": f"Bearer {raw}"}
    assert client.post("/ingest/samsung", headers=h, content="not json").status_code == 400


def test_ingest_preserves_self_feel_and_weight(client_token_db):
    client, raw, dbp = client_token_db
    from tjbot import db
    con = db.connect(dbp)
    db.set_self_feel(con, "2026-07-09", 7, 111)
    db.set_bodyweight(con, "2026-07-09", 82.5, 111)
    con.close()

    h = {"Authorization": f"Bearer {raw}"}
    body = {"days": [{"day": "2026-07-09", "sleep_h": 7.0, "resting_hr": 50}]}
    assert client.post("/ingest/samsung", headers=h, json=body).status_code == 200

    con = db.connect(dbp)
    row = con.execute('SELECT * FROM daily WHERE tg_id=111 AND day="2026-07-09"').fetchone()
    con.close()
    import json as _json
    extra = _json.loads(row["extra"]) if row["extra"] else {}
    assert row["sleep_h"] == 7.0
    assert row["weight_kg"] == 82.5
    assert extra.get("self_feel") == 7
