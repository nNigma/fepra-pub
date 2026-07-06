from datetime import date
from tjbot import db as botdb
from tj.analysis.dashboard import readiness_source, summary_data
from tj.models import DailyMetrics

def test_readiness_source_priority():
    assert readiness_source(60, 7) == (60, "garmin")
    assert readiness_source(None, 7) == (70, "self")
    assert readiness_source(None, None) == (None, None)

def test_summary_self_source(tmp_path):
    p = tmp_path / "t.db"; con = botdb.connect(p); botdb.init_schema(con)
    botdb.set_self_feel(con, date.today().isoformat(), 7, tg_id=111)
    con.close()
    data = summary_data(str(p), "sqlite", 184, "m", date.today(), tg_id=111)
    assert data["verdict"]["source"] == "self"

def test_summary_garmin_source(tmp_path):
    p = tmp_path / "t.db"; con = botdb.connect(p); botdb.init_schema(con)
    botdb.insert_daily(con, DailyMetrics(day=date.today(), readiness=62), tg_id=111)
    botdb.set_self_feel(con, date.today().isoformat(), 3, tg_id=111)
    con.close()
    data = summary_data(str(p), "sqlite", 184, "m", date.today(), tg_id=111)
    assert data["verdict"]["source"] == "garmin"
