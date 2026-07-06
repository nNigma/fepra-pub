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


def _mk(day, *, tg_id, score="130 кг"):
    a = Activity(source="manual", sport=Sport.CROSSFIT,
                 start=datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), 12,
                                tzinfo=timezone.utc),
                 activity_id=f"manual-{tg_id}-{day}-crossfit")
    a.strength = StrengthWodDetails(WodPrescription(), WodPerformed(score=score, rpe=7))
    a.extra = {"board_text": "WOD", "board_source": "own"}
    return a


def test_get_activity_scoped_by_tg_id():
    con = _con()
    botdb.insert_activity(con, _mk("2026-06-30", tg_id=111), tg_id=111)
    botdb.insert_activity(con, _mk("2026-06-30", tg_id=222), tg_id=222)
    assert botdb.get_activity(con, "manual-222-2026-06-30-crossfit", tg_id=111) is None
    assert botdb.get_activity(con, "manual-111-2026-06-30-crossfit", tg_id=111) is not None


def test_update_activity_does_not_leak_across_users():
    con = _con()
    botdb.insert_activity(con, _mk("2026-06-30", tg_id=111, score="own-111"), tg_id=111)
    botdb.insert_activity(con, _mk("2026-06-30", tg_id=222, score="own-222"), tg_id=222)
    botdb.update_activity(con, "manual-222-2026-06-30-crossfit", tg_id=111, score="X")
    act222 = botdb.get_activity(con, "manual-222-2026-06-30-crossfit", tg_id=222)
    assert act222["perf_score"] == "own-222"
