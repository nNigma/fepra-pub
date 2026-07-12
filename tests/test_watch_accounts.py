from tjbot import db


def _con(tmp_path):
    con = db.connect(tmp_path / "t.db")
    db.init_schema(con)
    return con


def test_issue_and_resolve_token(tmp_path):
    con = _con(tmp_path)
    raw = db.issue_watch_token(con, 111, "samsung")
    assert isinstance(raw, str) and len(raw) > 10
    assert db.resolve_watch_token(con, raw) == (111, "samsung")
    assert db.resolve_watch_token(con, "nope") is None
    assert db.resolve_watch_token(con, "") is None


def test_status_touch_and_revoke(tmp_path):
    con = _con(tmp_path)
    raw = db.issue_watch_token(con, 111, "samsung")
    assert db.watch_account_get(con, 111, "samsung")["status"] == "pending"
    db.watch_account_set_status(con, 111, "samsung", "connected")
    assert db.watch_account_get(con, 111, "samsung")["status"] == "connected"
    db.touch_watch_sync(con, 111, "samsung")
    assert db.watch_account_get(con, 111, "samsung")["last_sync_at"] is not None
    db.watch_account_set_status(con, 111, "samsung", "revoked")
    assert db.resolve_watch_token(con, raw) is None
    assert db.watch_account_get(con, 111, "samsung")["status"] == "revoked"
