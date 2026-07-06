import shutil
from datetime import date
from tjbot import db as botdb
from tjbot.handlers.menu import disconnect_garmin
from tj.models import DailyMetrics

def test_disconnect_removes_link_keeps_data(tmp_path, monkeypatch):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    botdb.insert_daily(con, DailyMetrics(day=date(2026,7,1), resting_hr=50), tg_id=111)
    botdb.garmin_account_set(con, 111, "a@b.c")
    ts = tmp_path / "tok"; ts.mkdir()
    monkeypatch.setattr(botdb, "garmin_tokenstore", lambda tg: ts)
    disconnect_garmin(con, 111)
    assert botdb.garmin_account_get(con, 111) is None
    assert not ts.exists()
    assert con.execute('SELECT count(*) FROM daily WHERE tg_id=111').fetchone()[0] == 1
