# tests/test_edit_db.py
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from tjbot import db as botdb
from tj.models import (Activity, Sport, StrengthWodDetails, WodPerformed,
                       WodPrescription)


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def _mk(day, *, sport=Sport.CROSSFIT, score="130 кг", source="manual",
        board_source="own", board_text="WOD", tg_id=1):
    a = Activity(source=source, sport=sport,
                 start=datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), 12,
                                tzinfo=timezone.utc),
                 activity_id=f"{source}-{tg_id}-{day}-{sport.value}")
    a.strength = StrengthWodDetails(WodPrescription(), WodPerformed(score=score, rpe=7))
    a.extra = {"board_text": board_text, "board_source": board_source}
    return a


def test_recent_manual_only_and_order():
    con = _con()
    botdb.insert_activity(con, _mk("2026-06-28"), tg_id=1)
    botdb.insert_activity(con, _mk("2026-06-30"), tg_id=1)
    botdb.insert_activity(con, _mk("2026-06-29", source="garmin"), tg_id=1)
    rows = botdb.recent_manual_workouts(con, tg_id=1)
    assert [r["day"] for r in rows] == ["2026-06-30", "2026-06-28"]   # garmin отсеян, новые сверху
    assert rows[0]["activity_id"] == "manual-1-2026-06-30-crossfit"
    assert rows[0]["board_source"] == "own"


def test_get_activity_board_source():
    con = _con()
    botdb.insert_activity(con, _mk("2026-06-30", board_source="gym", board_text="Фран"), tg_id=1)
    act = botdb.get_activity(con, "manual-1-2026-06-30-crossfit", tg_id=1)
    assert act["board_source"] == "gym" and act["board_text"] == "Фран"
    assert act["perf_score"] == "130 кг"
    assert botdb.get_activity(con, "нет-такого", tg_id=1) is None


def test_get_activity_defaults_own():
    con = _con()
    a = Activity(source="manual", sport=Sport.RUN,
                 start=datetime(2026, 6, 30, 12, tzinfo=timezone.utc),
                 activity_id="manual-1-2026-06-30-run")
    botdb.insert_activity(con, a, tg_id=1)
    act = botdb.get_activity(con, "manual-1-2026-06-30-run", tg_id=1)
    assert act["board_source"] == "own"      # extra пуст -> own


def test_update_activity_targeted():
    con = _con()
    botdb.insert_activity(con, _mk("2026-06-30", score="old"), tg_id=1)
    botdb.update_activity(con, "manual-1-2026-06-30-crossfit", tg_id=1, score="new")
    act = botdb.get_activity(con, "manual-1-2026-06-30-crossfit", tg_id=1)
    assert act["perf_score"] == "new" and act["perf_rpe"] == 7     # rpe не тронут


def test_set_activity_board_keeps_extra():
    con = _con()
    botdb.insert_activity(con, _mk("2026-06-30", board_source="own", board_text="old"), tg_id=1)
    botdb.set_activity_board(con, "manual-1-2026-06-30-crossfit", tg_id=1, raw_text="Фран 21-15-9", fmt="for-time")
    act = botdb.get_activity(con, "manual-1-2026-06-30-crossfit", tg_id=1)
    assert act["board_text"] == "Фран 21-15-9" and act["wod_format"] == "for-time"
    assert act["board_source"] == "own"       # другие ключи extra целы


def test_update_activity_clear_vs_skip_scaling():
    con = _con()
    botdb.insert_activity(con, _mk("2026-06-30"), tg_id=1)
    aid = "manual-1-2026-06-30-crossfit"
    botdb.update_activity(con, aid, tg_id=1, scaling="rx")
    assert botdb.get_activity(con, aid, tg_id=1)["perf_scaling"] == "rx"
    botdb.update_activity(con, aid, tg_id=1, scaling=None)              # None -> очистка в NULL
    assert botdb.get_activity(con, aid, tg_id=1)["perf_scaling"] is None
    botdb.update_activity(con, aid, tg_id=1, scaling="scaled")
    botdb.update_activity(con, aid, tg_id=1, score="x")                 # scaling не передан -> не тронут
    assert botdb.get_activity(con, aid, tg_id=1)["perf_scaling"] == "scaled"
