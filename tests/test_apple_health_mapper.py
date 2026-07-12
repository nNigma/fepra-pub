from __future__ import annotations

from tj.ingest import apple_health as ah
from tj.models import Sport

PAYLOAD = {"data": {"metrics": [
    {"name": "sleep_analysis", "units": "hr", "data": [
        {"date": "2026-07-12 00:00:00 +0300", "asleep": 7.4, "deep": 1.1, "rem": 1.6}]},
    {"name": "resting_heart_rate", "units": "count/min", "data": [
        {"date": "2026-07-12 00:00:00 +0300", "qty": 47}]},
    {"name": "heart_rate_variability", "units": "ms", "data": [
        {"date": "2026-07-12 00:00:00 +0300", "qty": 52.3}]},
    {"name": "vo2_max", "units": "ml/(kg*min)", "data": [
        {"date": "2026-07-12 00:00:00 +0300", "qty": 43.1}]},
    {"name": "blood_oxygen_saturation", "units": "%", "data": [
        {"date": "2026-07-12 00:00:00 +0300", "qty": 0.97}]},
    {"name": "step_count", "units": "count", "data": [
        {"date": "2026-07-12 00:00:00 +0300", "qty": 8421}]},
    {"name": "weight_body_mass", "units": "kg", "data": [
        {"date": "2026-07-12 00:00:00 +0300", "qty": 78.2}]},
    {"name": "unknown_metric", "data": [
        {"date": "2026-07-12 00:00:00 +0300", "qty": 1}]},
], "workouts": [
    {"id": "ABC-123", "name": "Outdoor Run",
     "start": "2026-07-12 08:00:00 +0300", "end": "2026-07-12 08:40:00 +0300",
     "distance": {"qty": 7.2, "units": "km"},
     "activeEnergyBurned": {"qty": 420, "units": "kcal"},
     "heartRateData": [
         {"date": "2026-07-12 08:00:30 +0300", "Avg": 120},
         {"date": "2026-07-12 08:20:00 +0300", "Avg": 150},
         {"date": "2026-07-12 08:39:00 +0300", "Avg": 160}]},
    {"name": "Functional Strength Training",
     "start": "2026-07-11T18:00:00+03:00", "duration": 3600,
     "heartRate": {"average": {"qty": 132}, "maximum": {"qty": 171}}},
    {"name": "No TZ", "start": "2026-07-10 08:00:00"},
]}}


def test_daily_metrics_bucketed():
    days, _ = ah.parse(PAYLOAD)
    assert len(days) == 1
    d = days[0]
    assert d.day.isoformat() == "2026-07-12"
    assert d.sleep_h == 7.4
    assert d.resting_hr == 47
    assert d.hrv == 52
    assert d.weight_kg == 78.2
    assert d.extra["sleep_deep_h"] == 1.1
    assert d.extra["sleep_rem_h"] == 1.6
    assert d.extra["vo2max"] == 43.1
    assert d.extra["spo2_avg"] == 97.0
    assert d.extra["steps"] == 8421
    assert "unknown_metric" not in d.extra


def test_run_workout():
    _, acts = ah.parse(PAYLOAD)
    run = [a for a in acts if a.sport == Sport.RUN]
    assert len(run) == 1
    a = run[0]
    assert a.source == "apple"
    assert a.activity_id == "apple-ABC-123"
    assert a.duration_min == 40.0
    assert a.calories == 420
    assert a.endurance and a.endurance.distance_km == 7.2
    assert a.endurance.avg_pace_s_per_km == round(2400 / 7.2)
    assert a.avg_hr == 143 and a.max_hr == 160
    assert a.extra["_hr_series"] == [[30, 120], [1200, 150], [2340, 160]]


def test_strength_workout_duration_seconds():
    _, acts = ah.parse(PAYLOAD)
    st = [a for a in acts if a.sport == Sport.OTHER]
    assert len(st) == 1
    a = st[0]
    assert a.duration_min == 60.0
    assert a.avg_hr == 132 and a.max_hr == 171
    assert a.endurance is None
    assert a.activity_id.startswith("apple-2026-07-11T18:00:00")


def test_workout_without_tz_skipped():
    _, acts = ah.parse(PAYLOAD)
    assert all("No TZ" not in (a.activity_id or "") for a in acts)
    assert len(acts) == 2


def test_sleep_segments_summed_within_day():
    payload = {"data": {"metrics": [{"name": "sleep_analysis", "data": [
        {"date": "2026-07-12 00:00:00 +0300", "asleep": 4.0, "deep": 0.8, "rem": 1.0},
        {"date": "2026-07-12 05:30:00 +0300", "asleep": 2.5, "deep": 0.4, "rem": 0.5},
    ]}], "workouts": []}}
    days, _ = ah.parse(payload)
    assert len(days) == 1
    assert days[0].sleep_h == 6.5
    assert days[0].extra["sleep_deep_h"] == 1.2
    assert days[0].extra["sleep_rem_h"] == 1.5


def test_empty_and_garbage():
    assert ah.parse({}) == ([], [])
    assert ah.parse({"data": {"metrics": "x", "workouts": None}}) == ([], [])
    days, acts = ah.parse({"data": {"metrics": [{"name": "resting_heart_rate",
                                                 "data": [{"date": "мусор", "qty": 47}]}],
                           "workouts": [{"name": "Run"}]}})
    assert days == [] and acts == []
