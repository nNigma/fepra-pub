"""
Юнит-тесты маппинга Garmin -> канон (SPEC §5, §8) — без сети и тяжёлых зависимостей.
Проверяют чистую логику: таймзона/привязка дня, темп, расщепление кроссфита,
сборка дневной биометрии, frontmatter и пер-полевой мёрдж.

Запуск:  PYTHONPATH=src python tests/test_garmin_mapping.py   (или: pytest)
"""
from __future__ import annotations

from datetime import date

from tj.adapters.base import merge_daily
from tj.adapters.garmin import GarminAdapter
from tj.models import DailyMetrics, Sport
from tj.vault import templates as tpl

_A = GarminAdapter(email="x", password="y", tokenstore="/tmp/ts", tz="Asia/Almaty")


def test_activity_run_tz_day_and_pace():
    run = _A._map_activity({
        "activityId": 123, "activityType": {"typeKey": "running"},
        "startTimeGMT": "2026-06-23 20:00:00",
        "duration": 1830.0, "averageHR": 150, "maxHR": 172, "calories": 300,
        "distance": 5000.0, "averageSpeed": 2.78, "elevationGain": 30,
    })
    assert run.sport is Sport.RUN
    assert str(run.start) == "2026-06-24 01:00:00+05:00"
    assert run.start.date() == date(2026, 6, 24)
    assert run.duration_min == 30.5
    assert run.endurance.distance_km == 5.0
    assert run.endurance.avg_pace_s_per_km == 359.7


def test_activity_crossfit_splits_to_strength():
    wod = _A._map_activity({
        "activityId": 456, "activityType": {"typeKey": "strength_training"},
        "startTimeGMT": "2026-06-24 05:00:00", "duration": 3600,
        "averageHR": 130, "maxHR": 160, "calories": 250,
    })
    assert wod.sport is Sport.CROSSFIT
    assert wod.strength is not None
    assert wod.endurance is None


def test_daily_metrics_mapping():
    dm = _A._map_daily(date(2026, 6, 24), {
        "stats": {"restingHeartRate": 48, "averageStressLevel": 25,
                  "weight": 81000, "bodyBatteryHighestValue": 90},
        "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 27000}},
        "hrv": {"hrvSummary": {"lastNightAvg": 62}},
        "training_readiness": [{"score": 78}],
        "body_battery": [],
    })
    assert (dm.sleep_h, dm.resting_hr, dm.hrv, dm.body_battery,
            dm.readiness, dm.stress_avg, dm.weight_kg) == (7.5, 48, 62, 90, 78, 25, 81.0)


def test_workout_frontmatter_keeps_manual():
    run = _A._map_activity({
        "activityId": 123, "activityType": {"typeKey": "running"},
        "startTimeGMT": "2026-06-23 20:00:00", "duration": 1830.0,
        "averageHR": 150, "maxHR": 172, "calories": 300,
        "distance": 5000.0, "averageSpeed": 2.78,
    })
    base, owned = tpl.workout_frontmatter(run)
    assert base == {"date": "2026-06-24", "type": "workout", "sport": "run"}
    assert owned["watch"]["calories"] == 300
    assert owned["endurance"]["distance_km"] == 5.0
    assert "wod" not in owned and "performed" not in owned


def test_daily_drops_garmin_sentinels():
    dm = _A._map_daily(date(2025, 7, 19), {
        "stats": {"restingHeartRate": None, "averageStressLevel": -2},
        "hrv": {"hrvSummary": {"lastNightAvg": 65}},
        "training_readiness": [{"score": 74}],
    })
    assert dm.stress_avg is None
    assert dm.resting_hr is None
    assert dm.hrv == 65 and dm.readiness == 74


def test_merge_daily_per_field_priority():
    g = DailyMetrics(day=date(2026, 6, 24), hrv=60, resting_hr=48)
    ap = DailyMetrics(day=date(2026, 6, 24), hrv=55, sleep_h=7.0)
    m = merge_daily(
        [("garmin", g), ("apple_health", ap)],
        {"hrv": ["garmin", "apple_health"],
         "hr": ["apple_health", "garmin"],
         "sleep": ["garmin", "apple_health"]},
    )
    assert (m.hrv, m.resting_hr, m.sleep_h) == (60, 48, 7.0)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} тестов прошло")
