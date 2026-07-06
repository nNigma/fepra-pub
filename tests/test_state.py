from __future__ import annotations
from tj.analysis.state import baseline, classify

def test_baseline_band_and_classify():
    vals = [44, 45, 46, 45, 47, 44, 46]
    b = baseline(vals, window=7)
    assert b["mean"] == 45.3
    assert b["lo"] <= b["mean"] <= b["hi"]
    assert classify(50, b, higher_better=False) == "above"
    assert classify(45, b, higher_better=False) == "in"


def test_risk_flag_underrecovery():
    from tj.analysis.state import risk_flag
    signals = {
        "rhr": ("above", True),
        "hrv": ("in", True),
        "bb_charge": ("below", True),
        "respiration_rest": ("in", True),
    }
    f = risk_flag(signals)
    assert f["level"] == "amber"
    assert "восстанов" in f["title"].lower()

def test_risk_flag_ok():
    from tj.analysis.state import risk_flag
    signals = {"rhr": ("in", True), "hrv": ("in", True), "bb_charge": ("in", True)}
    assert risk_flag(signals)["level"] == "green"

def test_decompose_readiness():
    from tj.analysis.state import decompose_readiness
    parts = decompose_readiness(
        readiness=58, base=65,
        contribs={"Сон-качество": +6, "HRV vs база": +4, "Пульс покоя": -5, "Долг нагрузки": -8})
    assert parts["delta"] == -7
    assert parts["items"][0][0] in ("Сон-качество", "HRV vs база", "Пульс покоя", "Долг нагрузки")

def test_microcycle_streak():
    from tj.analysis.state import microcycle
    days = [("2026-06-22", 80, 58), ("2026-06-23", 30, 66), ("2026-06-24", 95, 49),
            ("2026-06-25", 0, 71), ("2026-06-26", 75, 52)]
    mc = microcycle(days, hard_threshold=70)
    assert mc["hard_count"] == 3
    assert mc["max_streak"] == 1
    assert len(mc["days"]) == 5


def test_summary_has_state_layer(tmp_path):
    import sqlite3
    from datetime import date, timedelta
    from tjbot import db as botdb
    from tj.models import DailyMetrics
    from tj.analysis.dashboard import summary_data
    p = tmp_path / "t.db"
    con = botdb.connect(str(p)); botdb.init_schema(con)
    base = date(2026, 6, 1)
    for i in range(40):
        rdy = 55 + (i % 15)
        rhr = 46 + (i % 4)
        hrv = 58 + (i % 8)
        slp = 7.0 + round((i % 5) * 0.2, 1)
        wt = round(82.0 + (i % 3) * 0.1, 1)
        ex = {"bb_charge": 50 + i % 10, "respiration_rest": 14, "vo2max": 49.0, "sleep_score": 78 + i % 5}
        botdb.insert_daily(con, DailyMetrics(day=base + timedelta(days=i),
            sleep_h=slp, resting_hr=rhr, hrv=hrv, readiness=rdy, stress_avg=30,
            weight_kg=wt, extra=ex), tg_id=1)
    con.close()
    data = summary_data(str(p), "sqlite", 184, "m", date(2026, 7, 10), tg_id=1)
    assert "state" in data and "microcycle" in data and "narrative30" in data
    st = data["state"]
    assert st["risk"]["level"] in ("green", "amber", "red")
    assert isinstance(st["readiness"]["items"], list)
    assert len(st["readiness"]["items"]) > 0
    item0 = st["readiness"]["items"][0]
    assert "name" in item0 and "weight" in item0
    mc = data["microcycle"]
    assert len(mc["days"]) == 7
    n30 = data["narrative30"]
    assert len(n30) > 0
    assert all("kind" in b and "title" in b and "body" in b for b in n30)


def test_workout_extras_passthrough(tmp_path):
    import sqlite3, datetime as dt
    from tjbot import db as botdb
    from tj.models import Activity, Sport
    from tj.analysis.workouts import workout_report
    p = tmp_path / "w.db"
    con = botdb.connect(str(p)); botdb.init_schema(con)
    extra_data = {
        "time_in_zones": [600, 1200, 900, 300, 60],
        "primary_benefit": "AEROBIC_BASE",
        "te_aerobic": 3.2,
        "te_anaerobic": 0.5,
    }
    a = Activity(
        source="garmin",
        sport=Sport.RUN,
        start=dt.datetime(2026, 6, 15, 7, 0, tzinfo=dt.timezone.utc),
        duration_min=45,
        avg_hr=148,
        max_hr=172,
        calories=450,
        extra=extra_data,
    )
    botdb.insert_activity(con, a, tg_id=1)
    con.close()
    rep = workout_report(str(p), "sqlite", 184, "m", "2026-06-15", tg_id=1)
    assert rep is not None
    s = rep["sessions"][0]
    assert "extra" in s
    assert s["extra"] == extra_data
    assert s["zones"] == extra_data["time_in_zones"]
    assert isinstance(s["narrative"], list)
    assert len(s["narrative"]) > 0
