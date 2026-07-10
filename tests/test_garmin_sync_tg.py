from datetime import date
from tjbot import db as botdb
from tjbot import garmin_sync
from tj.models import DailyMetrics

def test_last_watch_date_per_owner(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    botdb.insert_daily(con, DailyMetrics(day=date(2026,7,3)), tg_id=botdb.OWNER_ID)
    botdb.insert_daily(con, DailyMetrics(day=date(2026,7,9)), tg_id=999)  # чужой, не считается
    assert garmin_sync.last_watch_date(con, tg_id=botdb.OWNER_ID) == "2026-07-03"
