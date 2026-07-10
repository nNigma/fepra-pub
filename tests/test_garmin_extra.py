from __future__ import annotations
import json, sqlite3
from datetime import date
from tj.models import DailyMetrics
from tjbot import db as botdb

def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con

def test_daily_extra_roundtrip():
    con = _con()
    m = DailyMetrics(day=date(2026, 6, 27), sleep_h=7.4, extra={"sleep_score": 78, "vo2max": 49})
    botdb.insert_daily(con, m, tg_id=1)
    row = con.execute('select extra from daily where day=?', ("2026-06-27",)).fetchone()
    assert json.loads(row["extra"])["sleep_score"] == 78

from tj.adapters.garmin import GarminAdapter
_A = GarminAdapter(email="x", password="y", tokenstore="/tmp/ts", tz="Asia/Almaty")

def test_map_daily_extra_fields():
    raw = {
        "date": "2026-06-27",
        "stats": {"restingHeartRate": 48, "averageStressLevel": 34,
                   "bodyBatteryHighestValue": 86, "bodyBatteryLowestValue": 12},
        "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 26640,
                                     "sleepScores": {"overall": {"value": 78}},
                                     "deepSleepSeconds": 4800, "remSleepSeconds": 6000},
                   "avgOvernightHrv": 62, "respiration": {"avgSleepRespirationValue": 14}},
        "hrv": {"hrvSummary": {"lastNightAvg": 62, "status": "BALANCED"}},
        "training_readiness": [{"score": 58}],
        "body_battery": [],
        "max_metrics": [{"generic": {"vo2MaxPreciseValue": 49.0}}],
        "training_status": {"latestTrainingStatusData": {"3168282": {"trainingStatus": 3, "trainingStatusFeedbackPhrase": "PRODUCTIVE_1"}}},
    }
    m = _A._map_daily(date(2026, 6, 27), raw)
    assert m.extra["sleep_score"] == 78
    assert m.extra["vo2max"] == 49.0
    assert m.extra["hrv_status"] == "BALANCED"
    assert m.extra["bb_charge"] == 74
    assert m.extra["respiration_rest"] == 14

def test_map_activity_extra_fields():
    item = {
        "activityId": 99, "activityType": {"typeKey": "strength_training"},
        "startTimeGMT": "2026-06-27 05:00:00", "duration": 5362,
        "averageHR": 118, "maxHR": 171, "calories": 628,
        "aerobicTrainingEffect": 2.8, "anaerobicTrainingEffect": 2.3,
        "trainingEffectLabel": "ANAEROBIC_CAPACITY", "activityTrainingLoad": 88,
        "activeKilocalories": 496, "bmrKilocalories": 132, "waterEstimated": 773,
        "avgRespirationRate": 25, "maxRespirationRate": 40,
        "moderateIntensityMinutes": 35, "vigorousIntensityMinutes": 28,
        "hrTimeInZone_1": 1720, "hrTimeInZone_2": 925, "hrTimeInZone_3": 539,
        "hrTimeInZone_4": 929, "hrTimeInZone_5": 118,
    }
    act = _A._map_activity(item)
    assert act.extra["te_aerobic"] == 2.8
    assert act.extra["primary_benefit"] == "ANAEROBIC_CAPACITY"
    assert act.extra["active_cal"] == 496
    assert act.extra["time_in_zones"] == [1720, 925, 539, 929, 118]
    assert act.extra["intensity_min"] == [35, 28]

def test_set_bodyweight_upsert():
    con = _con()
    botdb.set_bodyweight(con, "2026-06-27", 82.1, tg_id=1)
    row = con.execute('select weight_kg from daily where day=?', ("2026-06-27",)).fetchone()
    assert row["weight_kg"] == 82.1
    botdb.set_bodyweight(con, "2026-06-27", 81.8, tg_id=1)
    rows = con.execute('select count(*) c from daily where day=?', ("2026-06-27",)).fetchone()
    assert rows["c"] == 1


def test_map_activity_partial_zones_and_sentinels():
    item = {
        "activityId": 100, "activityType": {"typeKey": "strength_training"},
        "startTimeGMT": "2026-06-27 05:00:00", "duration": 600,
        "aerobicTrainingEffect": -1.0, "anaerobicTrainingEffect": -1.0,
        "hrTimeInZone_1": 1720,
    }
    act = _A._map_activity(item)
    assert act.extra["time_in_zones"] == [1720, 0, 0, 0, 0]
    assert "intensity_min" not in act.extra
    assert "te_aerobic" not in act.extra
    assert "te_anaerobic" not in act.extra


def test_map_daily_respiration_from_dailysleepdto():
    """Реальная структура Garmin: дыхание во сне в dailySleepDTO, не в sleep.respiration."""
    raw = {
        "date": "2026-07-10",
        "stats": {"restingHeartRate": 45},
        "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 21780,
                                     "averageRespirationValue": 13.0,
                                     "lowestRespirationValue": 9.0}},
    }
    m = _A._map_daily(date(2026, 7, 10), raw)
    assert m.extra["respiration_rest"] == 13
