from datetime import date
from tj.models import DailyMetrics
from tjbot import db


def _con(tmp_path):
    con = db.connect(tmp_path / "t.db")
    db.init_schema(con)
    return con


def test_whoop_tokens_crud(tmp_path):
    con = _con(tmp_path)
    assert db.whoop_tokens_get(con, 111) is None
    db.whoop_tokens_set(con, 111, access_token="a1", refresh_token="r1",
                        expires_at="2026-07-11T10:00:00+00:00", whoop_user_id="u9")
    t = db.whoop_tokens_get(con, 111)
    assert t["access_token"] == "a1" and t["refresh_token"] == "r1"
    assert t["whoop_user_id"] == "u9"
    db.whoop_tokens_set(con, 111, access_token="a2", refresh_token="r2",
                        expires_at="2026-07-11T11:00:00+00:00")
    t = db.whoop_tokens_get(con, 111)
    assert t["refresh_token"] == "r2" and t["whoop_user_id"] == "u9"
    db.whoop_tokens_delete(con, 111)
    assert db.whoop_tokens_get(con, 111) is None


def test_oauth_state_issue_consume(tmp_path):
    con = _con(tmp_path)
    st = db.oauth_state_issue(con, 111, "whoop")
    assert isinstance(st, str) and len(st) > 10
    assert db.oauth_state_consume(con, st) == (111, "whoop")
    assert db.oauth_state_consume(con, st) is None
    assert db.oauth_state_consume(con, "nope") is None


def test_oauth_state_expired(tmp_path):
    con = _con(tmp_path)
    st = db.oauth_state_issue(con, 111, "whoop", ttl_min=0)
    import time
    time.sleep(0.01)
    assert db.oauth_state_consume(con, st) is None


def test_watch_account_ensure_and_by_provider(tmp_path):
    con = _con(tmp_path)
    db.watch_account_ensure(con, 111, "whoop", "connected")
    db.watch_account_ensure(con, 222, "whoop", "connected")
    db.watch_account_ensure(con, 222, "whoop", "revoked")
    assert db.watch_accounts_by_provider(con, "whoop") == [111]
    assert db.watch_account_get(con, 222, "whoop")["status"] == "revoked"


def test_upsert_daily_merge_preserves(tmp_path):
    con = _con(tmp_path)
    db.set_self_feel(con, "2026-07-09", 7, 111)
    db.set_bodyweight(con, "2026-07-09", 82.5, 111)
    m = DailyMetrics(day=date(2026, 7, 9), sleep_h=7.0, readiness=70)
    db.upsert_daily_merge(con, m, 111)
    row = con.execute('SELECT * FROM daily WHERE tg_id=111 AND day="2026-07-09"').fetchone()
    import json
    extra = json.loads(row["extra"]) if row["extra"] else {}
    assert row["sleep_h"] == 7.0 and row["readiness"] == 70
    assert row["weight_kg"] == 82.5 and extra.get("self_feel") == 7
