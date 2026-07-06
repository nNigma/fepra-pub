from __future__ import annotations
import sqlite3
from tjbot import db as botdb
from tj.analysis.levels import goals_screen_data


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_screen_shape_with_one_lift():
    con = _con()
    botdb.add_result(con, tg_id=1, discipline="deadlift", value=130, reps=1,
                     est_1rm=130, source="manual", day="2026-06-26")
    botdb.add_goal(con, tg_id=1, kind="numeric", discipline="deadlift",
                   target_value="140", metric="kg", title="Становая 140")
    data = goals_screen_data(con, tg_id=1, sex="m", bodyweight=79)
    assert data["overall"]["assessed"] == 1 and data["overall"]["total"] == 16
    dl = next(d for d in data["lifts"] if d["id"] == "deadlift")
    assert dl["has_data"] is True and dl["level"] == "Любитель"
    empty = next(d for d in data["lifts"] if d["id"] == "back_squat")
    assert empty["has_data"] is False
    assert len(data["benchmarks"]) == 5
    assert data["goals"][0]["progress"]["pct"] == 93


def test_screen_empty():
    con = _con()
    data = goals_screen_data(con, tg_id=1, sex="m", bodyweight=79)
    assert data["overall"]["level"] is None
    assert all(d["has_data"] is False for d in data["lifts"])
    assert data["goals"] == []
