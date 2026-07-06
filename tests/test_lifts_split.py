from __future__ import annotations

from tjbot import db


def test_split_specific_vs_ambiguous(tmp_path):
    con = db.connect(str(tmp_path / "t.db")); db.init_schema(con)
    parsed = [
        {"movement": "рывок в сед", "weight_kg": 60, "reps": 1},
        {"movement": "рывок", "weight_kg": 55, "reps": 1},
        {"movement": "взятие", "weight_kg": 80, "reps": 2},
        {"movement": "жим лёжа штанги", "weight_kg": 70, "reps": 3},
    ]
    resolved, ambiguous = db.split_lifts(con, parsed)
    rids = {r["discipline"] for r in resolved}
    assert "squat_snatch" in rids and "bench_press" in rids
    fams = sorted(a["family"] for a in ambiguous)
    assert fams == ["clean", "snatch"]
    a_snatch = next(a for a in ambiguous if a["family"] == "snatch")
    assert a_snatch["weight"] == 55 and a_snatch["reps"] == 1
