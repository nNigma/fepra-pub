import pytest
from tjbot import db, whoop_sync


SLEEP = {
    "id": "s-1", "nap": False, "start": "2026-07-08T21:10:00.000Z",
    "end": "2026-07-09T04:32:00.000Z", "timezone_offset": "+03:00",
    "score_state": "SCORED",
    "score": {"stage_summary": {"total_light_sleep_time_milli": 14400000,
                                "total_slow_wave_sleep_time_milli": 5400000,
                                "total_rem_sleep_time_milli": 6300000}},
}
RECOVERY = {"sleep_id": "s-1", "score_state": "SCORED",
            "score": {"recovery_score": 80, "hrv_rmssd_milli": 45.0,
                      "resting_heart_rate": 50}}
WORKOUT = {"id": "w-1", "sport_name": "running", "score_state": "SCORED",
           "start": "2026-07-09T05:00:00.000Z", "end": "2026-07-09T05:42:00.000Z",
           "timezone_offset": "+03:00",
           "score": {"strain": 9.0, "average_heart_rate": 145,
                     "max_heart_rate": 170, "kilojoule": 1500.0,
                     "distance_meter": 6000.0}}


class _FakeClient:
    def __init__(self, fail=False):
        self.fail = fail
    def collection(self, path, start, end):
        if self.fail:
            import httpx
            req = httpx.Request("GET", "http://x")
            raise httpx.HTTPStatusError("401", request=req,
                                        response=httpx.Response(401, request=req))
        if "sleep" in path:
            return [SLEEP]
        if "recovery" in path:
            return [RECOVERY]
        return [WORKOUT]


def _setup(tmp_path, monkeypatch, fail=False):
    dbp = tmp_path / "t.db"
    con = db.connect(dbp)
    db.init_schema(con)
    db.whoop_tokens_set(con, 111, access_token="A", refresh_token="R",
                        expires_at="2026-07-11T12:00:00+00:00")
    db.watch_account_ensure(con, 111, "whoop", "connected")
    con.close()
    monkeypatch.setattr(whoop_sync, "_client", lambda db_path, tg_id: _FakeClient(fail))
    return dbp


def test_sync_recent_writes_and_merges(tmp_path, monkeypatch):
    dbp = _setup(tmp_path, monkeypatch)
    con = db.connect(dbp)
    db.set_bodyweight(con, "2026-07-09", 82.5, 111)
    con.close()
    res = whoop_sync.sync_recent(str(dbp), 111)
    assert res == {"days": 1, "activities": 1}
    con = db.connect(dbp)
    row = con.execute('SELECT * FROM daily WHERE tg_id=111 AND day="2026-07-09"').fetchone()
    assert row["readiness"] == 79
    assert row["weight_kg"] == 82.5
    act = con.execute('SELECT * FROM activities WHERE tg_id=111').fetchone()
    assert act["source"] == "whoop" and act["activity_id"] == "whoop-w-1"
    assert db.watch_account_get(con, 111, "whoop")["last_sync_at"] is not None
    con.close()
    whoop_sync.sync_recent(str(dbp), 111)
    con = db.connect(dbp)
    assert con.execute("SELECT COUNT(*) c FROM activities WHERE tg_id=111").fetchone()["c"] == 1
    con.close()


def test_sync_recent_401_sets_error(tmp_path, monkeypatch):
    dbp = _setup(tmp_path, monkeypatch, fail=True)
    res = whoop_sync.sync_recent(str(dbp), 111)
    assert "error" in res
    con = db.connect(dbp)
    assert db.watch_account_get(con, 111, "whoop")["status"] == "error"
    con.close()


def test_sync_all(tmp_path, monkeypatch):
    dbp = _setup(tmp_path, monkeypatch)
    out = whoop_sync.sync_all(str(dbp))
    assert out == {111: {"days": 1, "activities": 1}}
