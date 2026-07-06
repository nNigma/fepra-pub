from __future__ import annotations
import sqlite3
from tjbot import db as botdb
from tj.analysis import standards
from tj.analysis.progression import epley_1rm


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_lifts_to_results_scans_descriptive_phrases():
    con = _con()
    parsed = [
        {"movement": "приседание со штангой на спине", "weight_kg": 100, "reps": 1},
        {"movement": "взятие на грудь + толчок в ножницы", "weight_kg": 80, "reps": 1},
        {"movement": "фронтальный присед с гантелью", "weight_kg": 20, "reps": 15},
    ]
    discs = {r["discipline"] for r in botdb.lifts_to_results(con, parsed)}
    assert "back_squat" in discs
    assert "clean_and_jerk" in discs
    assert "front_squat" in discs


def test_maps_movement_to_lift_and_epley():
    con = _con()
    res = botdb.lifts_to_results(con, [{"movement": "становая", "weight_kg": 130, "reps": 1}])
    assert len(res) == 1
    assert standards.disciplines()[res[0]["discipline"]]["ontology"] == "deadlift"
    assert res[0]["est_1rm"] == epley_1rm(130, 1)
    assert res[0]["weight"] == 130 and res[0]["reps"] == 1 and res[0]["name"]


def test_guards_bad_values():
    con = _con()
    assert botdb.lifts_to_results(con, [{"movement": "становая", "weight_kg": 0, "reps": 1}]) == []
    assert botdb.lifts_to_results(con, [{"movement": "становая", "weight_kg": 100, "reps": 0}]) == []
    assert botdb.lifts_to_results(con, [{"movement": "становая", "weight_kg": "abc", "reps": 1}]) == []
    assert botdb.lifts_to_results(con, [{"movement": "зюзюка", "weight_kg": 100, "reps": 1}]) == []


def test_uses_runtime_alias():
    con = _con()
    botdb.add_alias(con, "тяга с пола", "deadlift")
    res = botdb.lifts_to_results(con, [{"movement": "тяга с пола", "weight_kg": 120, "reps": 2}])
    assert len(res) == 1
    assert standards.disciplines()[res[0]["discipline"]]["ontology"] == "deadlift"


def test_record_lift_results_dedup():
    con = _con()
    res = botdb.lifts_to_results(con, [{"movement": "становая", "weight_kg": 130, "reps": 1}])
    botdb.record_lift_results(con, 1, res, "2026-06-30", "A1")
    botdb.record_lift_results(con, 1, res, "2026-06-30", "A1")
    n = con.execute("SELECT COUNT(*) c FROM discipline_results WHERE activity_id='A1'").fetchone()["c"]
    assert n == 1
    assert res[0]["discipline"] in botdb.best_results(con, 1)
