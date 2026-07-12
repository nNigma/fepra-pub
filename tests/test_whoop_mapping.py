from tj.adapters import whoop


SLEEP = {
    "id": "s-1", "nap": False, "start": "2026-07-08T21:10:00.000Z",
    "end": "2026-07-09T04:32:00.000Z", "timezone_offset": "+03:00",
    "score_state": "SCORED",
    "score": {
        "stage_summary": {
            "total_light_sleep_time_milli": 14400000,
            "total_slow_wave_sleep_time_milli": 5400000,
            "total_rem_sleep_time_milli": 6300000,
        },
        "sleep_performance_percentage": 88,
        "respiratory_rate": 14.2,
    },
}
RECOVERY = {
    "sleep_id": "s-1", "score_state": "SCORED",
    "score": {"recovery_score": 67, "hrv_rmssd_milli": 41.3,
              "resting_heart_rate": 52, "spo2_percentage": 96.4,
              "skin_temp_celsius": 33.1},
}
WORKOUT = {
    "id": "w-1", "sport_name": "running", "score_state": "SCORED",
    "start": "2026-07-09T05:00:00.000Z", "end": "2026-07-09T05:42:00.000Z",
    "timezone_offset": "+03:00",
    "score": {"strain": 10.5, "average_heart_rate": 150, "max_heart_rate": 175,
              "kilojoule": 1800.0, "distance_meter": 7100.0,
              "altitude_gain_meter": 35.0},
}


def test_renorm_bands():
    assert whoop.renorm_recovery(0) == 0
    assert whoop.renorm_recovery(33) == 44
    assert whoop.renorm_recovery(34) == 45
    assert whoop.renorm_recovery(66) == 64
    assert whoop.renorm_recovery(67) == 65
    assert whoop.renorm_recovery(100) == 100
    assert whoop.renorm_recovery(None) is None


def test_map_daily_joins_recovery_wake_day():
    days = whoop.map_daily([SLEEP], [RECOVERY])
    assert len(days) == 1
    m = days[0]
    assert m.day.isoformat() == "2026-07-09"
    assert m.sleep_h == 7.2
    assert m.readiness == 65
    assert m.hrv == 41 and m.resting_hr == 52
    assert m.extra["recovery_pct"] == 67
    assert m.extra["sleep_deep_h"] == 1.5 and m.extra["sleep_rem_h"] == 1.8
    assert m.extra["sleep_score"] == 88
    assert m.extra["respiration_rest"] == 14.2
    assert m.extra["spo2_avg"] == 96.4


def test_map_daily_skips_nap_and_unscored():
    nap = dict(SLEEP, id="s-2", nap=True)
    pending = dict(SLEEP, id="s-3", score_state="PENDING_SCORE")
    days = whoop.map_daily([nap, pending], [])
    assert len(days) == 1
    assert days[0].sleep_h is None
    assert days[0].readiness is None


def test_map_workouts():
    acts = whoop.map_workouts([WORKOUT])
    assert len(acts) == 1
    a = acts[0]
    assert a.source == "whoop" and a.activity_id == "whoop-w-1"
    assert a.sport.value == "run"
    assert a.start.date().isoformat() == "2026-07-09"
    assert a.duration_min == 42.0
    assert a.avg_hr == 150 and a.max_hr == 175
    assert a.calories == 430
    assert a.endurance.distance_km == 7.1
    assert a.endurance.elevation_gain_m == 35
    assert a.extra["strain"] == 10.5


def test_map_workouts_zone_durations():
    w = dict(WORKOUT, id="w-3", score={**WORKOUT["score"],
             "zone_durations": {"zone_zero_milli": 60000, "zone_one_milli": 120000,
                                "zone_two_milli": 300000, "zone_three_milli": 600000,
                                "zone_four_milli": 900000, "zone_five_milli": 60000}})
    a = whoop.map_workouts([w])[0]
    assert a.extra["time_in_zones"] == [120, 300, 600, 900, 60]


def test_map_workouts_no_zone_durations_omits_field():
    a = whoop.map_workouts([WORKOUT])[0]
    assert "time_in_zones" not in a.extra


def test_map_workouts_other_sport_no_endurance():
    w = dict(WORKOUT, id="w-2", sport_name="functional fitness")
    a = whoop.map_workouts([w])[0]
    assert a.sport.value == "other" and a.endurance is None


def test_map_workouts_skips_broken():
    assert whoop.map_workouts([{"id": "x"}, "junk", None]) == []
