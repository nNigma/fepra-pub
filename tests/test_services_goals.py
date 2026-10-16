from __future__ import annotations

from datetime import date

import pytest

from svc_common import make_con
from tj.analysis import standards
from tj.services import goals as G
from tj.services.errors import Invalid, NotFound
from tjbot import db as botdb

A, B = 201, 202
TODAY = date(2026, 9, 1)


def test_add_numeric_lift_goal_and_list(tmp_path):
    con = make_con(tmp_path)
    g = G.add(con, A, "numeric", "back_squat", "140")
    assert g["tg_id"] == A and g["status"] == "active" and g["metric"] == "kg"
    assert float(g["target_value"]) == 140 and g["exercise"] == "back_squat" and g["title"]
    assert [x["id"] for x in G.list_goals(con, A)] == [g["id"]]
    assert G.list_goals(con, B) == []
    g2 = G.add(con, A, "numeric", "deadlift", 180)                 # число тоже принимается
    assert float(g2["target_value"]) == 180
    scr = G.screen(con, A)
    assert {x["id"] for x in scr["goals"]} == {g["id"], g2["id"]}
    assert all("progress" in x for x in scr["goals"])
    assert G.screen(con, B)["goals"] == []


def test_add_benchmark_and_level_goals(tmp_path):
    con = make_con(tmp_path)
    bench = next(d for d in standards.disciplines().values() if d["kind"] != "lift" and d["unit"] == "time")
    g = G.add(con, A, "numeric", bench["id"], "4:30")
    assert float(g["target_value"]) == 270 and g["metric"] == bench["basis"]
    lvl = standards.tiers("ru")[2]
    g = G.add(con, A, "level", "back_squat", lvl)
    assert g["metric"] == "level" and g["target_value"] == lvl
    en = standards.tiers("en")[2]
    assert G.add(con, A, "level", "back_squat", en, lang="en")["target_value"] == lvl   # в БД канон — русский


@pytest.mark.parametrize("args", [
    ("numeric", "нет_такой", "100"), ("numeric", "back_squat", "много"), ("numeric", "back_squat", 0),
    ("numeric", "back_squat", None), ("level", "back_squat", "Бог"), ("weird", "back_squat", "100")])
def test_add_rejects_bad_input(tmp_path, args):
    con = make_con(tmp_path)
    with pytest.raises(Invalid):
        G.add(con, A, *args)
    assert G.list_goals(con, A) == []


def test_owner_checks_for_archive_and_complete(tmp_path):
    con = make_con(tmp_path)
    g = G.add(con, A, "numeric", "back_squat", 140)
    for fn in (G.archive, G.complete):
        with pytest.raises(NotFound):
            fn(con, B, g["id"])                          # чужая
    with pytest.raises(NotFound):
        G.archive(con, A, 99999)
    with pytest.raises(NotFound):
        G.archive(con, A, "abc")
    assert botdb.active_goals(con, A)[0]["status"] == "active"      # чужие попытки ничего не сломали
    assert G.complete(con, A, g["id"])["status"] == "done"
    g2 = G.add(con, A, "numeric", "deadlift", 180)
    assert G.archive(con, A, g2["id"])["status"] == "archived"
    assert G.list_goals(con, A) == []


def test_enter_pm_lift_with_tier(tmp_path):
    con = make_con(tmp_path)
    botdb.save_user(con, A, nick="a", height_cm=180, weight_kg=80, sex="m", age=30,
                    gym="Universe", level="beginner")
    r = G.enter_pm(con, A, "back_squat", "100x3", today=TODAY)
    assert r["tier"] and r["tier"]["level"] and r["tier"]["value"] == 100
    assert r["value"] == 100 and r["reps"] == 3 and r["est_1rm"] == round(100 * (1 + 3 / 30), 1)
    assert r["day"] == "2026-09-01" and r["name"]
    row = con.execute("SELECT * FROM discipline_results WHERE tg_id=?", (A,)).fetchone()
    assert row["source"] == "manual" and row["est_1rm"] == r["est_1rm"] and row["activity_id"] is None
    r = G.enter_pm(con, A, "deadlift", 180, today=TODAY)          # вес числом = 1 повтор
    assert r["reps"] == 1 and r["est_1rm"] == 180
    r = G.enter_pm(con, A, "deadlift", 150, reps=5, today=TODAY)
    assert r["reps"] == 5 and r["est_1rm"] == round(150 * (1 + 5 / 30), 1)
    assert botdb.best_results(con, A)["deadlift"]["value"] == 180


def test_enter_pm_benchmark_and_errors(tmp_path):
    con = make_con(tmp_path)
    bench = next(d for d in standards.disciplines().values() if d["kind"] != "lift" and d["unit"] == "time")
    r = G.enter_pm(con, A, bench["id"], "5:10", today=TODAY)
    assert r["value"] == 310 and r["reps"] is None and r["est_1rm"] is None
    for did, val in (("back_squat", "abc"), ("back_squat", 0), ("back_squat", None), ("nope", "100"),
                     (bench["id"], "5:99")):
        with pytest.raises(Invalid):
            G.enter_pm(con, A, did, val, today=TODAY)
    n = con.execute("SELECT COUNT(*) FROM discipline_results WHERE tg_id=?", (A,)).fetchone()[0]
    assert n == 1                                                   # ошибки ничего не записали


def test_handler_reexports_still_work():
    """Хендлеры бота импортируют парсеры из прежних мест — реэкспорт из tj.analysis.parse_input."""
    from tj.analysis import parse_input as P
    from tjbot.handlers import record_result, record_workout
    assert record_result.parse_lift is P.parse_lift
    assert record_result.parse_benchmark is P.parse_benchmark
    assert record_result.est_1rm_for is P.est_1rm_for
    assert record_workout._parse_lift_lines is P.parse_lift_lines
    assert P.parse_rpe("итого RPE: 8") == 8 and P.parse_rpe("без") is None
    assert P.detect_scaling("Scaled.") .value == "scaled" and P.detect_scaling("скейл").value == "scaled"
    assert P.detect_scaling("RX").value == "rx" and P.detect_scaling("ничего") is None
    assert P.parse_lift_lines("Присед 100x3\nмусор\n5 нет") == [
        {"movement": "Присед", "weight_kg": 100.0, "reps": 3}]
    from tjbot.handlers import lift_disambig
    from tj.services.workouts import FAMILY_VARIANTS
    assert lift_disambig.FAMILY_VARIANTS is FAMILY_VARIANTS
