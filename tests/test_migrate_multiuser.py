import sqlite3
from tjbot import db as botdb
from tjbot.migrate_multiuser import migrate

def _old_schema(p):
    con = sqlite3.connect(p)
    con.execute('CREATE TABLE daily ("day" TEXT PRIMARY KEY, "resting_hr" INTEGER, "extra" TEXT)')
    con.execute('CREATE TABLE activities ("day" TEXT, "activity_id" TEXT, "source" TEXT, "extra" TEXT)')
    con.execute('INSERT INTO daily VALUES ("2026-07-01", 50, "{}")')
    con.execute('INSERT INTO activities VALUES ("2026-07-01","g-1","garmin","{}")')
    con.commit(); con.close()

def test_migrate_backfills_owner(tmp_path):
    p = str(tmp_path / "t.db"); _old_schema(p)
    migrate(p, owner_id=botdb.OWNER_ID)
    con = sqlite3.connect(p)
    assert con.execute('SELECT tg_id FROM daily').fetchone()[0] == botdb.OWNER_ID
    assert con.execute('SELECT tg_id FROM activities').fetchone()[0] == botdb.OWNER_ID
    pk = [r[1] for r in con.execute('PRAGMA table_info(daily)') if r[5]]
    assert set(pk) == {"tg_id", "day"}
    con.close()

def test_migrate_idempotent(tmp_path):
    p = str(tmp_path / "t.db"); _old_schema(p)
    migrate(p, owner_id=botdb.OWNER_ID)
    migrate(p, owner_id=botdb.OWNER_ID)
    con = sqlite3.connect(p)
    assert con.execute('SELECT count(*) FROM daily').fetchone()[0] == 1
    con.close()
