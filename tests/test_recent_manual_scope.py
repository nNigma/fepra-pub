from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from tjbot import db as botdb
from tj.models import Activity, Sport, StrengthWodDetails, WodPerformed, WodPrescription


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def _mk(tg_id, day):
    a = Activity(source="manual", sport=Sport.CROSSFIT,
                 start=datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), 12,
                                tzinfo=timezone.utc),
                 activity_id=f"manual-{tg_id}-{day}-crossfit")
    a.strength = StrengthWodDetails(WodPrescription(), WodPerformed(score="130 кг", rpe=7))
    return a


def test_recent_manual_workouts_scoped_by_tg_id():
    con = _con()
    botdb.insert_activity(con, _mk(111, "2026-06-28"), tg_id=111)
    botdb.insert_activity(con, _mk(222, "2026-06-29"), tg_id=222)
    rows = botdb.recent_manual_workouts(con, tg_id=111)
    assert [r["activity_id"] for r in rows] == ["manual-111-2026-06-28-crossfit"]
