from tj.ingest import health_connect as hc


def test_parse_day_and_activity():
    payload = {
        "provider": "samsung",
        "days": [{"day": "2026-07-09", "sleep_h": 7.2, "resting_hr": 52, "hrv": 41,
                  "spo2_avg": 96, "spo2_lowest": 91, "sleep_deep_h": 1.1, "sleep_rem_h": 1.4,
                  "respiration": 14, "steps": 8200, "vo2max": 48, "weight_kg": None}],
        "activities": [{"activity_id": "hc-1", "sport": "run", "start": "2026-07-09T07:12:00+03:00",
                        "duration_min": 42, "avg_hr": 150, "max_hr": 175, "calories": 430,
                        "distance_km": 7.1, "elevation_gain_m": 35,
                        "hr_series": [[0, 120], [5, 132]]}],
    }
    days, acts = hc.parse(payload)
    assert len(days) == 1
    d = days[0]
    assert d.day.isoformat() == "2026-07-09"
    assert d.sleep_h == 7.2 and d.resting_hr == 52 and d.hrv == 41
    assert d.readiness is None and d.body_battery is None
    assert d.extra["sleep_deep_h"] == 1.1
    assert d.extra["respiration_rest"] == 14
    assert d.extra["spo2_avg"] == 96 and d.extra["steps"] == 8200
    assert "respiration" not in d.extra

    assert len(acts) == 1
    a = acts[0]
    assert a.source == "samsung" and a.sport.value == "run"
    assert a.activity_id == "hc-1" and a.duration_min == 42
    assert a.endurance is not None and a.endurance.distance_km == 7.1
    assert a.extra["_hr_series"] == [[0, 120], [5, 132]]


def test_parse_skips_malformed_and_maps_other():
    days, acts = hc.parse({"days": [{"nope": 1}],
                           "activities": [{"sport": "strength", "activity_id": "x"}]})
    assert days == []
    assert acts == []


def test_non_endurance_has_no_endurance_block():
    payload = {"activities": [{"activity_id": "hc-2", "sport": "crossfit",
                               "start": "2026-07-09T18:00:00+03:00", "duration_min": 20}]}
    _, acts = hc.parse(payload)
    assert acts[0].sport.value == "other"
    assert acts[0].endurance is None


def test_rejects_naive_start():
    _, acts = hc.parse({"activities": [{"activity_id": "hc-3", "sport": "run",
                                        "start": "2026-07-09T07:00:00", "duration_min": 30}]})
    assert acts == []


def test_tolerates_non_list_and_non_dict_items():
    assert hc.parse({"days": 5, "activities": "x"}) == ([], [])
    assert hc.parse({"days": [1, "a"], "activities": [None]}) == ([], [])
    assert hc.parse({}) == ([], [])
