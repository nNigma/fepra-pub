"""Нормы КБЖУ/воды от цели. Референс владельца: м, 36, 183 см, 78 кг, recomp."""
import sqlite3

from tj.analysis import nutrition_goals as ng


def test_bmr_reference():
    assert round(ng.bmr("m", 36, 183, 78.0)) == 1749
    assert round(ng.bmr("f", 30, 165, 60.0)) == 1320


def test_targets_recomp_reference():
    t = ng.targets("m", 36, 183, 78.0, "recomp")
    assert t["kcal"] == round(1748.75 * 1.35)
    assert t["protein_g"] == round(78 * 2.2)
    assert t["fat_g"] == round(78 * 0.9)
    assert t["carb_g"] == round((t["kcal"] - t["protein_g"] * 4 - t["fat_g"] * 9) / 4)


def test_targets_goals_shift_kcal():
    base = ng.targets("m", 36, 183, 78.0, "maintain")["kcal"]
    assert ng.targets("m", 36, 183, 78.0, "cut")["kcal"] == round(1748.75 * 1.35 * 0.85)
    assert ng.targets("m", 36, 183, 78.0, "bulk")["kcal"] == round(1748.75 * 1.35 * 1.10)
    assert ng.targets("m", 36, 183, 78.0, "cut")["protein_g"] == round(78 * 2.0)
    assert base == round(1748.75 * 1.35)


def test_targets_carb_never_negative():
    t = ng.targets("f", 60, 150, 45.0, "cut")
    assert t["carb_g"] >= 0


def test_targets_incomplete_profile():
    assert ng.targets("m", None, 183, 78.0, "maintain") is None
    assert ng.targets("m", 36, None, 78.0, "maintain") is None
    assert ng.targets("m", 36, 183, None, "maintain") is None


def test_targets_unknown_goal_falls_to_maintain():
    assert ng.targets("m", 36, 183, 78.0, "bogus") == ng.targets("m", 36, 183, 78.0, "maintain")


def test_water_target():
    assert ng.water_target_l(0) == 2.2
    assert ng.water_target_l(1100) == 3.3
    assert ng.water_target_l(None) == 2.2


def test_burned_and_sweat(tmp_path):
    con = sqlite3.connect(str(tmp_path / "t.db"))
    con.row_factory = sqlite3.Row
    con.execute('CREATE TABLE activities ("activity_id" TEXT, "tg_id" INTEGER, '
                '"day" TEXT, "calories" INTEGER, "extra" TEXT)')
    con.execute("INSERT INTO activities VALUES ('a1', 1, '2026-07-08', 500, "
                "'{\"sweat_loss_ml\": 800}')")
    con.execute("INSERT INTO activities VALUES ('a2', 1, '2026-07-08', 120, NULL)")
    con.execute("INSERT INTO activities VALUES ('a3', 2, '2026-07-08', 999, NULL)")
    con.execute("INSERT INTO activities VALUES ('a4', 1, '2026-07-07', NULL, 'мусор')")
    assert ng.burned(con, 1, "2026-07-08") == 620
    assert ng.sweat_ml(con, 1, "2026-07-08") == 800
    assert ng.burned(con, 1, "2026-07-01") == 0
    assert ng.sweat_ml(con, 1, "2026-07-07") == 0
