"""Эндьюранс-метрики (дистанция/темп/мощность/набор) доходят до отчёта тренировки и ИИ."""
from __future__ import annotations
import datetime as dt
from tjbot import db as botdb
from tj.models import Activity, DailyMetrics, EnduranceDetails, Sport
from tj.analysis.workouts import workout_report
from tj.analysis import llm_coach


def _db(tmp_path):
    p = tmp_path / "e.db"
    con = botdb.connect(str(p)); botdb.init_schema(con)
    botdb.insert_daily(con, DailyMetrics(day=dt.date(2026, 7, 9), readiness=70), tg_id=1)
    a = Activity(source="garmin", sport=Sport.RUN,
                 start=dt.datetime(2026, 7, 9, 7, 0, tzinfo=dt.timezone.utc),
                 duration_min=42, avg_hr=150, calories=430,
                 endurance=EnduranceDetails(distance_km=8.2, avg_pace_s_per_km=307,
                                            avg_power_w=290, elevation_gain_m=64))
    botdb.insert_activity(con, a, tg_id=1)
    con.close()
    return str(p)


def test_workout_report_has_endurance(tmp_path):
    rep = workout_report(_db(tmp_path), "sqlite", 184, "m", "2026-07-09", tg_id=1)
    s = rep["sessions"][0]
    assert s["distance_km"] == 8.2
    assert s["avg_pace_s_per_km"] == 307
    assert s["avg_power_w"] == 290
    assert s["elevation_gain_m"] == 64


def test_workout_payload_has_endurance(tmp_path):
    rep = workout_report(_db(tmp_path), "sqlite", 184, "m", "2026-07-09", tg_id=1)
    p = llm_coach.workout_payload(rep)
    assert p["distance_km"] == 8.2
    assert p["avg_pace_s_per_km"] == 307
