from __future__ import annotations
import sqlite3
from tjbot import db as botdb
from tj.analysis.progression import epley_1rm


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_autopick_single_lift():
    con = _con()
    n = botdb.autopick_from_activity(con, tg_id=1, wod_name="Становая-волна + меткон",
                                     load_kg=130, day="2026-06-26", activity_id="A1")
    assert n == 1
    best = botdb.best_results(con, 1)
    assert "deadlift" in best and best["deadlift"]["est_1rm"] == epley_1rm(130, 1)
    assert best["deadlift"]["source"] == "auto"


def test_autopick_ambiguous_skipped():
    con = _con()
    n = botdb.autopick_from_activity(con, tg_id=1, wod_name="Становая + присед",
                                     load_kg=100, day="2026-06-26", activity_id="A2")
    assert n == 0


def test_autopick_no_load_or_no_movement():
    con = _con()
    assert botdb.autopick_from_activity(con, 1, "Меткон на дыхание", None, "2026-06-26", "A3") == 0
    assert botdb.autopick_from_activity(con, 1, "Becketon", 80, "2026-06-26", "A4") == 0


def test_autopick_multiword_clean_and_jerk():
    con = _con()
    n = botdb.autopick_from_activity(con, tg_id=1, wod_name="Clean and Jerk 100",
                                     load_kg=100, day="2026-06-26", activity_id="A5")
    assert n == 1
    assert "clean_and_jerk" in botdb.best_results(con, 1)
