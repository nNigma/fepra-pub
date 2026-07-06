from datetime import date, datetime
from tjbot import db as botdb
from tj.models import Activity, Sport

def _act(con, tg, day):
    a = Activity(source="manual", sport=Sport.CROSSFIT,
                 start=datetime.fromisoformat(day+"T12:00:00+00:00"),
                 activity_id=f"manual-{tg}-{day}-crossfit")
    botdb.insert_activity(con, a, tg_id=tg)

def test_pending_scoped_by_user(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    _act(con, 111, "2026-07-01")
    _act(con, 222, "2026-07-02")
    botdb.claude_review_put(con, 111, "2026-07-01", "готов")
    pend111 = botdb.claude_reviews_pending(con, 111)
    pend222 = botdb.claude_reviews_pending(con, 222)
    assert pend111 == []
    assert [p["day"] for p in pend222] == ["2026-07-02"]
