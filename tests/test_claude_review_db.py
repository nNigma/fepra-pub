from __future__ import annotations

import sqlite3

from tjbot import db as botdb


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def _add_activity(con, day, sport="crossfit", tg_id=111):
    con.execute(
        'INSERT INTO activities ("tg_id","day","sport","activity_id","source") VALUES (?,?,?,?,?)',
        (tg_id, day, sport, f"manual-{day}-{sport}", "manual"))
    con.commit()


def test_put_get_roundtrip():
    con = _con()
    assert botdb.claude_review_get(con, 111, "2026-07-01") is None
    botdb.claude_review_put(con, 111, "2026-07-01", "# разбор\nтело")
    assert botdb.claude_review_get(con, 111, "2026-07-01") == "# разбор\nтело"


def test_put_upsert_overwrites():
    con = _con()
    botdb.claude_review_put(con, 111, "2026-07-01", "старый")
    botdb.claude_review_put(con, 111, "2026-07-01", "новый")
    assert botdb.claude_review_get(con, 111, "2026-07-01") == "новый"


def test_put_many_fans_to_all():
    con = _con()
    botdb.claude_review_put_many(con, [111, 222], "2026-07-01", "текст")
    assert botdb.claude_review_get(con, 111, "2026-07-01") == "текст"
    assert botdb.claude_review_get(con, 222, "2026-07-01") == "текст"
    assert botdb.claude_review_get(con, 333, "2026-07-01") is None


def test_pending_lists_days_without_review():
    con = _con()
    _add_activity(con, "2026-07-01")
    _add_activity(con, "2026-07-02")
    botdb.claude_review_put(con, 111, "2026-07-01", "есть")
    pending = botdb.claude_reviews_pending(con, 111)
    days = [p["day"] for p in pending]
    assert days == ["2026-07-02"]
    assert pending[0]["sport"] == "crossfit"


def test_pending_empty_when_all_reviewed():
    con = _con()
    _add_activity(con, "2026-07-01")
    botdb.claude_review_put(con, 111, "2026-07-01", "есть")
    assert botdb.claude_reviews_pending(con, 111) == []
