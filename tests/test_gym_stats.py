from __future__ import annotations
import sqlite3
from tjbot import db as botdb
from tj.analysis import gym


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_frequency_counts_confirmed_only():
    con = _con()
    botdb.add_program(con, "2026-06-01", "Universe", "wod",
                      movements=["deadlift", "thruster"], confirmed=1)
    botdb.add_program(con, "2026-06-02", "Universe", "wod",
                      movements=["deadlift"], confirmed=1)
    botdb.add_program(con, "2026-06-03", "Universe", "wod",
                      movements=["burpee"], confirmed=0)
    by = {canon: n for canon, n, _ in gym.movement_frequency(con)}
    assert by["deadlift"] == 2
    assert by["thruster"] == 1
    assert "burpee" not in by


def test_frequency_human_name():
    con = _con()
    botdb.add_program(con, "2026-06-01", "Universe", "wod",
                      movements=["deadlift"], confirmed=1)
    canon, n, name = gym.movement_frequency(con)[0]
    assert canon == "deadlift" and n == 1 and name and name != ""


def test_frequency_empty():
    assert gym.movement_frequency(_con()) == []
