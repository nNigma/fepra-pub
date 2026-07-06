import json
from datetime import date
from tjbot import db as botdb
from tj.models import DailyMetrics

def test_set_self_feel_creates_row(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    botdb.set_self_feel(con, "2026-07-05", 7, tg_id=111)
    r = con.execute('SELECT extra FROM daily WHERE tg_id=? AND day=?', (111, "2026-07-05")).fetchone()
    assert json.loads(r["extra"])["self_feel"] == 7

def test_set_self_feel_upsert_keeps_biometrics(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    botdb.insert_daily(con, DailyMetrics(day=date(2026,7,5), readiness=60, extra={"bb_charge": 80}), tg_id=111)
    botdb.set_self_feel(con, "2026-07-05", 8, tg_id=111)
    r = con.execute('SELECT readiness, extra FROM daily WHERE tg_id=? AND day=?', (111, "2026-07-05")).fetchone()
    ex = json.loads(r["extra"])
    assert r["readiness"] == 60 and ex["bb_charge"] == 80 and ex["self_feel"] == 8

def test_set_self_feel_isolated(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    botdb.set_self_feel(con, "2026-07-05", 5, tg_id=111)
    assert con.execute('SELECT count(*) FROM daily WHERE tg_id=?', (222,)).fetchone()[0] == 0
