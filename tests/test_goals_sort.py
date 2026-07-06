from __future__ import annotations

from tjbot import db
from tj.analysis.levels import goals_screen_data


def test_lifts_filled_desc_then_empty(tmp_path):
    con = db.connect(str(tmp_path / "t.db")); db.init_schema(con)
    db.save_user(con, 1, nick="a", height_cm=180, weight_kg=80, sex="m", gym="G")
    db.add_result(con, tg_id=1, discipline="deadlift", value=130, reps=1, est_1rm=130, source="auto", day="2026-07-01", activity_id="a1")
    db.add_result(con, tg_id=1, discipline="back_squat", value=88, reps=1, est_1rm=88, source="auto", day="2026-07-01", activity_id="a2")
    data = goals_screen_data(con, 1, "m", 80.0)
    lifts = data["lifts"]
    filled = [c for c in lifts if c["has_data"]]
    assert [c["id"] for c in filled[:2]] == ["deadlift", "back_squat"]
    first_empty = next(i for i, c in enumerate(lifts) if not c["has_data"])
    assert all(lifts[j]["has_data"] for j in range(first_empty))
