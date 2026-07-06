from datetime import date, datetime
from zoneinfo import ZoneInfo
from tjbot import db as botdb
from tj.models import Activity, DailyMetrics, Sport
from tj.analysis.engine import analyze
from tj.analysis.workouts import recent_workouts

def _seed(con, tg, day, dur, ahr):
    botdb.insert_daily(con, DailyMetrics(day=date.fromisoformat(day), resting_hr=50), tg_id=tg)
    a = Activity(source="garmin", sport=Sport.CROSSFIT,
                 start=datetime.fromisoformat(day + "T12:00:00+00:00"),
                 activity_id=f"g-{tg}-{day}", duration_min=dur, avg_hr=ahr, max_hr=170)
    botdb.insert_activity(con, a, tg_id=tg)

def test_analyze_isolated(tmp_path):
    p = tmp_path / "t.db"; con = botdb.connect(p); botdb.init_schema(con)
    _seed(con, 111, "2026-07-01", 60, 150)
    _seed(con, 222, "2026-07-02", 60, 150)
    con.close()
    a1 = analyze(str(p), "sqlite", 184, "m", tg_id=111)
    assert a1["range"] == ("2026-07-01", "2026-07-01")
    assert recent_workouts(str(p), "sqlite", 30, tg_id=222)[0]["day"] == "2026-07-02"
    assert all(r["day"] != "2026-07-02" for r in recent_workouts(str(p), "sqlite", 30, tg_id=111))
