from __future__ import annotations
from tj.analysis.workouts import _merged_rows


def _act(day, sport, *, dur=None, ahr=None, mhr=None, cal=None, wod_name=None,
         wod_fmt=None, scaling=None, load_kg=None, score=None, rpe=None,
         extra=None, source=None):
    return (day, sport, dur, ahr, mhr, cal, wod_name, wod_fmt, scaling,
            load_kg, score, rpe, extra, source)


def test_manual_and_garmin_same_session_merge():
    acts = [
        _act("2026-06-29", "crossfit", wod_name="Fran", score="7:20", source="manual"),
        _act("2026-06-29", "crossfit", ahr=150, mhr=178, cal=480, source="garmin"),
    ]
    rows = _merged_rows(acts)
    assert len(rows) == 1
    assert rows[0]["wod_name"] == "Fran"
    assert rows[0]["avg_hr"] == 150
    assert rows[0]["calories"] == 480


def test_two_garmin_sessions_same_day_stay_separate():
    acts = [
        _act("2026-06-11", "swim", dur=30, ahr=130, source="garmin"),
        _act("2026-06-11", "swim", dur=45, ahr=140, source="garmin"),
    ]
    rows = _merged_rows(acts)
    assert len(rows) == 2
    assert {r["duration_min"] for r in rows} == {30, 45}


def test_two_manual_sessions_same_day_stay_separate():
    acts = [
        _act("2026-06-11", "crossfit", wod_name="Fran", source="manual"),
        _act("2026-06-11", "crossfit", wod_name="Grace", source="manual"),
    ]
    rows = _merged_rows(acts)
    assert len(rows) == 2
    assert {r["wod_name"] for r in rows} == {"Fran", "Grace"}


def test_two_garmin_plus_one_manual_merges_only_one_pair():
    acts = [
        _act("2026-06-11", "swim", dur=30, source="garmin"),
        _act("2026-06-11", "swim", dur=45, source="garmin"),
        _act("2026-06-11", "swim", wod_name="drills", source="manual"),
    ]
    rows = _merged_rows(acts)
    assert len(rows) == 2
