from datetime import datetime
from zoneinfo import ZoneInfo
from tjbot import db as botdb
from tj.models import Activity, DailyMetrics, Sport

def _act(tg, day):
    return Activity(source="manual", sport=Sport.CROSSFIT,
                    start=datetime(*map(int, day.split("-")), 12, 0, tzinfo=ZoneInfo("UTC")),
                    activity_id=f"manual-{tg}-{day}-crossfit")

def test_two_users_same_day_isolated(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    botdb.insert_activity(con, _act(111, "2026-07-01"), tg_id=111)
    botdb.insert_activity(con, _act(222, "2026-07-01"), tg_id=222)
    n = con.execute('SELECT count(*) FROM activities').fetchone()[0]
    assert n == 2
    assert con.execute('SELECT count(*) FROM activities WHERE tg_id=?', (111,)).fetchone()[0] == 1

def test_daily_upsert_per_user(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    botdb.insert_daily(con, DailyMetrics(day=__import__("datetime").date(2026,7,1), resting_hr=50), tg_id=111)
    botdb.insert_daily(con, DailyMetrics(day=__import__("datetime").date(2026,7,1), resting_hr=60), tg_id=222)
    rows = dict(con.execute('SELECT tg_id, resting_hr FROM daily').fetchall())
    assert rows[111] == 50 and rows[222] == 60
