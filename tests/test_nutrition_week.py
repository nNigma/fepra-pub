"""Недельная сводка питания week_summary: окно, суммы, средние, выводы, советы."""
from __future__ import annotations

import datetime

from tj.analysis import nutrition as nutr

TODAY = datetime.date(2026, 7, 18)
TGT = {"kcal": 2000, "protein_g": 140, "fat_g": 70, "carb_g": 293}
_MICRO_OK = {"fiber_g": 30.0, "sugar_g": 40.0, "sodium_mg": 2000.0,
             "iron_mg": 10.0, "calcium_mg": 1000.0, "magnesium_mg": 400.0,
             "potassium_mg": 3500.0}


def _day(day, kcal=2000, protein=140, fat=70, carb=290, **micro):
    row = {"day": day, "meals": 3, "kcal": kcal, "protein_g": protein,
           "fat_g": fat, "carb_g": carb}
    for k in nutr.MICRO:
        row[k] = micro.get(k, _MICRO_OK[k])
    return row


def test_window_excludes_today_and_old_days():
    rows = [_day("2026-07-18"), _day("2026-07-17"), _day("2026-07-11"),
            _day("2026-07-10")]
    out = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    assert out["range"] == ["2026-07-11", "2026-07-17"]
    assert out["days_recorded"] == 2
    assert [p[0] for p in out["metrics"]["kcal"]["series"]] == [
        "2026-07-11", "2026-07-17"]


def test_sums_targets_x7_and_avg():
    rows = [_day("2026-07-16", kcal=1800, protein=120),
            _day("2026-07-17", kcal=2200, protein=160)]
    out = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    k = out["kcal"]
    assert k["sum"] == 4000
    assert k["target_week"] == 14000
    assert k["target_day"] == 2000
    assert k["avg"] == 2000
    assert k["delta"] == -10000
    p = out["metrics"]["protein_g"]
    assert p["sum"] == 280
    assert p["target_week"] == 980
    assert p["avg"] == 140.0
    assert p["base"] == 140
    assert out["protein_per_kg_avg"] == 1.79


def test_empty_days_are_gap_not_zero_in_series():
    rows = [_day("2026-07-12"), _day("2026-07-15")]
    out = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    assert len(out["metrics"]["kcal"]["series"]) == 2
    assert out["days_recorded"] == 2


def test_none_without_recorded_days():
    assert nutr.week_summary([], {}, 78, TGT, "maintain", TODAY) is None
    assert nutr.week_summary([_day("2026-07-18")], {}, 78, TGT,
                             "maintain", TODAY) is None


def test_dirs_by_goal_and_limits():
    rows = [_day("2026-07-17")]
    cut = nutr.week_summary(rows, {}, 78, TGT, "cut", TODAY)
    assert cut["metrics"]["kcal"]["dir"] == "high_bad"
    assert cut["metrics"]["carb_g"]["dir"] == "high_bad"
    assert cut["metrics"]["protein_g"]["dir"] == "low_bad"
    mnt = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    assert mnt["metrics"]["kcal"]["dir"] == "low_bad"
    assert mnt["metrics"]["sugar_g"]["dir"] == "high_bad"
    assert mnt["metrics"]["sodium_mg"]["dir"] == "high_bad"
    assert mnt["metrics"]["fiber_g"]["dir"] == "low_bad"


def test_micro_targets_x7():
    rows = [_day("2026-07-17", fiber_g=10.0)]
    out = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    f = out["metrics"]["fiber_g"]
    assert f["base"] == 30
    assert f["target_week"] == 210
    assert f["sum"] == 10.0


def test_kcal_cls():
    ok = nutr.week_summary([_day(f"2026-07-{d}") for d in range(11, 18)],
                           {}, 78, TGT, "maintain", TODAY)
    assert ok["kcal"]["cls"] == "green"
    over = nutr.week_summary([_day(f"2026-07-{d}", kcal=2600)
                              for d in range(11, 18)], {}, 78, TGT, "cut", TODAY)
    assert over["kcal"]["cls"] == "red"
    under_cut = nutr.week_summary([_day(f"2026-07-{d}", kcal=1700)
                                   for d in range(11, 18)], {}, 78, TGT,
                                  "cut", TODAY)
    assert under_cut["kcal"]["cls"] == "amber"
    under_bulk = nutr.week_summary([_day(f"2026-07-{d}", kcal=1700)
                                    for d in range(11, 18)], {}, 78, TGT,
                                   "bulk", TODAY)
    assert under_bulk["kcal"]["cls"] == "red"


def test_no_targets_without_profile():
    out = nutr.week_summary([_day("2026-07-17")], {}, None, None,
                            "maintain", TODAY)
    assert out["kcal"]["target_week"] is None
    assert out["kcal"]["cls"] is None
    assert out["metrics"]["protein_g"]["base"] is None
    assert out["metrics"]["fiber_g"]["target_week"] == 210
    assert out["protein_per_kg_avg"] is None


def test_metric_flags_mark_bad_micro():
    rows = [_day(f"2026-07-{d}", fiber_g=5.0, sugar_g=90.0)
            for d in range(11, 18)]
    out = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    assert out["metrics"]["fiber_g"]["flag"] is True
    assert out["metrics"]["sugar_g"]["flag"] is True
    assert out["metrics"]["calcium_mg"]["flag"] is False
    assert out["metrics"]["kcal"]["flag"] is False


def test_protein_ok_follows_goal():
    rows = [_day(f"2026-07-{d}", protein=115) for d in range(11, 18)]
    assert nutr.week_summary(rows, {}, 78, TGT, "maintain",
                             TODAY)["protein_ok"] is True
    assert nutr.week_summary(rows, {}, 78, TGT, "cut",
                             TODAY)["protein_ok"] is False
    assert nutr.week_summary(rows, {}, None, TGT, "cut",
                             TODAY)["protein_ok"] is None


def test_conclusions_under_and_protein():
    rows = [_day(f"2026-07-{d}", kcal=1700, protein=100)
            for d in range(11, 18)]
    out = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    assert len(out["conclusions"]) == 2
    assert "2100" in out["conclusions"][0]
    assert "15%" in out["conclusions"][0]
    assert "1.28" in out["conclusions"][1]


def test_conclusions_ok():
    rows = [_day(f"2026-07-{d}") for d in range(11, 18)]
    out = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    assert any("в норме" in c for c in out["conclusions"])
    assert any("1.79" in c for c in out["conclusions"])


def test_conclusions_micro_flags():
    rows = [_day(f"2026-07-{d}", fiber_g=5.0) for d in range(11, 18)]
    out = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    assert any("клетчатка" in c for c in out["conclusions"])


def test_advice_few_days_first():
    rows = [_day("2026-07-16"), _day("2026-07-17")]
    out = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    assert "из 7" in out["advice"][0]


def test_advice_protein_threshold_by_goal():
    rows = [_day(f"2026-07-{d}", protein=115) for d in range(11, 18)]
    mnt = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    assert not any("г/кг" in a for a in mnt["advice"])
    cut = nutr.week_summary(rows, {}, 78, TGT, "cut", TODAY)
    assert any("1.47" in a for a in cut["advice"])


def test_advice_kcal_under_with_per_day():
    rows = [_day(f"2026-07-{d}", kcal=1500) for d in range(11, 18)]
    out = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY)
    assert any("500" in a and "ккал" in a for a in out["advice"])


def test_advice_kcal_under_ok_for_cut():
    rows = [_day(f"2026-07-{d}", kcal=1500) for d in range(11, 18)]
    out = nutr.week_summary(rows, {}, 78, TGT, "cut", TODAY)
    assert not any("добавь" in a for a in out["advice"])


def test_advice_micro_and_water_capped_at_4():
    water = {f"2026-07-{d}": 0.5 for d in range(11, 18)}
    rows = [_day(f"2026-07-{d}", kcal=1500, protein=80, fiber_g=4.0,
                 calcium_mg=100.0, magnesium_mg=50.0)
            for d in range(11, 18)]
    out = nutr.week_summary(rows, water, 78, TGT, "maintain", TODAY)
    assert len(out["advice"]) == 4


def test_en_locale():
    rows = [_day("2026-07-16"), _day("2026-07-17")]
    out = nutr.week_summary(rows, {}, 78, TGT, "maintain", TODAY, lang="en")
    assert any("logged" in a for a in out["advice"])
