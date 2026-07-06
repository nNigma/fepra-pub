import sqlite3
from tjbot import db as botdb

def test_daily_composite_pk_and_tg_id(tmp_path):
    con = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(con)
    cols = [r[1] for r in con.execute('PRAGMA table_info(daily)')]
    assert "tg_id" in cols
    pk = [r[1] for r in con.execute('PRAGMA table_info(daily)') if r[5]]
    assert set(pk) == {"tg_id", "day"}
    acols = [r[1] for r in con.execute('PRAGMA table_info(activities)')]
    assert "tg_id" in acols
