"""Карта мышц: словарь канон->группы, агрегация по тренировке и неделе."""
from __future__ import annotations

from tj import ontology
from tj.analysis import muscles


def _mv(name, canon):
    return {"name": name, "canon": canon, "canons": [canon] if canon else [],
            "weighted": ontology.is_weighted(canon)}


def _strength_block(name, canon):
    return {"header": name, "format": "strength", "movements": [_mv(name, canon)]}


def _wod_block(*moves):
    return {"header": "WOD", "format": "for_time",
            "movements": [_mv(n, c) for n, c in moves]}


def _session(blocks=None, score=None, sport="crossfit"):
    extra = {"result_blocks": blocks} if blocks is not None else {}
    return {"sport": sport, "score": score, "extra": extra}


def test_map_covers_all_ontology_canons():
    missing = [c for c in ontology.MOVEMENTS if c not in muscles.MUSCLE_MAP]
    assert missing == []


def test_map_values_are_known_groups_and_disjoint():
    for canon, m in muscles.MUSCLE_MAP.items():
        prim, sec = set(m["primary"]), set(m["secondary"])
        assert prim, canon
        assert prim <= muscles.GROUPS, canon
        assert sec <= muscles.GROUPS, canon
        assert not (prim & sec), canon


def test_primary_wins_over_secondary():
    s = _session(blocks=[_wod_block(("присед", "back_squat"), ("бёрпи", "burpee"))])
    m = muscles.workout_muscles([s])
    assert "quads" in m["primary"]
    assert "quads" not in m["secondary"]
    assert "hamstrings" in m["secondary"]


def test_tonnage_weighting_scales_intensity():
    blocks = [_strength_block("присед", "back_squat"),
              _strength_block("жим лёжа", "bench_press")]
    score = "присед:\n  раунд 1: 100x5\nжим лёжа:\n  раунд 1: 20x5\n"
    m = muscles.workout_muscles([_session(blocks=blocks, score=score)])
    assert m["intensity"]["quads"] == 1.0
    assert m["intensity"]["chest"] < 0.5


def test_metcon_movement_weighs_as_top_strength():
    blocks = [_strength_block("присед", "back_squat"),
              _wod_block(("подтягивания", "pull_up"))]
    score = "присед:\n  раунд 1: 100x5\n"
    m = muscles.workout_muscles([_session(blocks=blocks, score=score)])
    assert m["intensity"]["quads"] == m["intensity"]["upper_back"] == 1.0


def test_cardio_fallback_secondary_half_intensity():
    m = muscles.workout_muscles([_session(sport="run")])
    assert m["primary"] == []
    assert set(m["secondary"]) == {"quads", "hamstrings", "glutes", "calves"}
    assert all(v == 0.5 for v in m["intensity"].values())


def test_unknown_sport_without_blocks_gives_none():
    assert muscles.workout_muscles([_session(sport="other")]) is None
    assert muscles.workout_muscles([]) is None


def test_unknown_movements_only_gives_none():
    s = _session(blocks=[_wod_block(("загадка", None))])
    assert muscles.workout_muscles([s]) is None


def test_week_aggregates_and_reports_idle():
    s1 = _session(blocks=[_wod_block(("присед", "back_squat"))])
    s2 = _session(sport="run")
    m = muscles.week_muscles([s1, s2])
    assert "quads" in m["primary"]
    assert m["intensity"]["quads"] == 1.0
    assert "forearms" in m["idle"]
    assert "quads" not in m["idle"]


def test_week_without_data_gives_none():
    assert muscles.week_muscles([_session(sport="other")]) is None


def _db_with_activity(tmp_path, day, sport, extra):
    import datetime as dt
    from tjbot import db as botdb
    from tj.models import Activity, DailyMetrics, Sport
    p = tmp_path / "m.db"
    con = botdb.connect(str(p)); botdb.init_schema(con)
    y, mo, d = (int(x) for x in day.split("-"))
    botdb.insert_daily(con, DailyMetrics(day=dt.date(y, mo, d), readiness=60), tg_id=1)
    a = Activity(source="manual", sport=Sport(sport),
                 start=dt.datetime(y, mo, d, 10, 0, tzinfo=dt.timezone.utc),
                 duration_min=60, extra=extra)
    botdb.insert_activity(con, a, tg_id=1)
    con.close()
    return str(p)


def test_workout_report_has_muscles(tmp_path):
    from tj.analysis.workouts import workout_report
    extra = {"result_blocks": [_wod_block(("присед", "back_squat"))]}
    p = _db_with_activity(tmp_path, "2026-07-08", "crossfit", extra)
    rep = workout_report(p, "sqlite", 184, "m", "2026-07-08", tg_id=1)
    assert rep["muscles"]["primary"] and "quads" in rep["muscles"]["primary"]


def test_summary_has_muscles_week(tmp_path):
    import datetime as dt
    from tj.analysis.dashboard import summary_data
    extra = {"result_blocks": [_wod_block(("присед", "back_squat"))]}
    p = _db_with_activity(tmp_path, "2026-07-08", "crossfit", extra)
    data = summary_data(p, "sqlite", 184, "m", dt.date(2026, 7, 10), tg_id=1)
    mw = data["muscles_week"]
    assert "quads" in mw["primary"]
    assert "forearms" in mw["idle"]


def test_summary_muscles_week_outside_window(tmp_path):
    import datetime as dt
    from tj.analysis.dashboard import summary_data
    extra = {"result_blocks": [_wod_block(("присед", "back_squat"))]}
    p = _db_with_activity(tmp_path, "2026-06-01", "crossfit", extra)
    data = summary_data(p, "sqlite", 184, "m", dt.date(2026, 7, 10), tg_id=1)
    assert data["muscles_week"] is None
