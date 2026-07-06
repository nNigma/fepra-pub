from __future__ import annotations
from tj.analysis.levels import tier, overall_level


def test_tier_lift_bw_ratio_male():
    t = tier("deadlift", value=130, sex="m", bodyweight=79)
    assert t["level"] == "Любитель" and t["idx"] == 1
    assert round(t["next_threshold"]) == 148 and round(t["distance"]) == 18


def test_tier_lift_top_level():
    t = tier("deadlift", value=250, sex="m", bodyweight=79)
    assert t["level"] == "Элита" and t["idx"] == 4
    assert t["next_threshold"] is None and t["distance"] is None


def test_tier_below_first():
    t = tier("deadlift", value=50, sex="m", bodyweight=79)
    assert t["level"] == "Новичок" and t["idx"] == 0


def test_tier_benchmark_lower_better():
    t = tier("fran", value=252, sex="m", bodyweight=79)
    assert t["level"] == "Средний" and t["idx"] == 2
    assert t["next_threshold"] == 240 and t["distance"] == 12


def test_tier_benchmark_amrap_higher():
    t = tier("cindy", value=18, sex="m", bodyweight=79)
    assert t["level"] == "Средний" and t["idx"] == 2


def test_overall_level_partial_data():
    tiers = [{"idx": 1}, {"idx": 2}, {"idx": 2}]
    ov = overall_level(tiers, assessed=3, total=13)
    assert ov["level"] == "Любитель" and ov["idx"] == 1
    assert ov["assessed"] == 3 and ov["total"] == 13
    assert 0 < ov["progress"] < 1


def test_overall_level_no_data():
    ov = overall_level([], assessed=0, total=13)
    assert ov["level"] is None and ov["assessed"] == 0
