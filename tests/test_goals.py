from __future__ import annotations
import sqlite3
from tjbot import db as botdb
from tj.analysis.levels import goal_progress


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_goal_crud():
    con = _con()
    gid = botdb.add_goal(con, tg_id=1, kind="numeric", discipline="deadlift",
                         target_value="140", metric="kg", title="Становая 140")
    goals = botdb.active_goals(con, 1)
    assert len(goals) == 1 and goals[0]["id"] == gid
    botdb.archive_goal(con, gid)
    assert botdb.active_goals(con, 1) == []


def test_goal_progress_numeric_higher():
    g = {"kind": "numeric", "discipline": "deadlift", "target_value": "140", "metric": "kg"}
    p = goal_progress(g, current_value=130, current_tier=None)
    assert p["pct"] == 93 and p["done"] is False and p["remaining"] == 10


def test_goal_progress_numeric_lower():
    g = {"kind": "numeric", "discipline": "fran", "target_value": "240", "metric": "abs_sec"}
    p = goal_progress(g, current_value=252, current_tier=None)
    assert p["done"] is False and p["remaining"] == 12
    p2 = goal_progress(g, current_value=235, current_tier=None)
    assert p2["done"] is True


def test_goal_progress_level():
    g = {"kind": "level", "discipline": "deadlift", "target_value": "Продвинутый", "metric": "level"}
    tier = {"idx": 1, "level": "Любитель", "next_threshold": 158, "value": 130, "distance": 28}
    p = goal_progress(g, current_value=130, current_tier=tier)
    assert p["done"] is False and "Продвинутый" in p["text"]
    tier_hi = {"idx": 3, "level": "Продвинутый", "next_threshold": None, "value": 200, "distance": None}
    p2 = goal_progress(g, current_value=200, current_tier=tier_hi)
    assert p2["done"] is True
