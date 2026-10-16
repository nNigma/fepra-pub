from __future__ import annotations

from tj.analysis.wod_program import render_template


def test_weight_sets_per_round():
    blocks = [{"header": "ТА", "format": "emom_strength", "rounds": 5, "reps": 5,
               "work_min": None, "rest_min": None, "has_cap": False,
               "movements": [{"name": "приседание со штангой на спине",
                              "canon": "back_squat", "weighted": True}],
               "benchmark": None}]
    out = render_template(blocks)
    assert "приседание со штангой на спине:" in out
    assert out.count("(вес×повторы)") == 5
    assert "раунд 1 (вес×повторы):" in out
    assert "раунд 5 (вес×повторы):" in out


def test_for_time_fixed_weight_and_time():
    blocks = [{"header": "WOD", "format": "for_time", "rounds": 3, "reps": None,
               "work_min": None, "rest_min": None, "has_cap": False,
               "movements": [{"name": "прыжки через бокс", "canon": "box_jump_over", "weighted": False},
                             {"name": "фронтальный присед с гантелью", "canon": "front_squat", "weighted": True}],
               "benchmark": None}]
    out = render_template(blocks)
    assert "вес «фронтальный присед с гантелью»:" in out
    assert "время (мм:сс):" in out
    assert "прыжки через бокс" not in out.split("время")[0].replace("вес «", "")


def test_reps_at_cap():
    blocks = [{"header": "WOD", "format": "for_time", "rounds": 1, "reps": None,
               "work_min": None, "rest_min": None, "has_cap": True,
               "movements": [], "benchmark": None}]
    out = render_template(blocks)
    assert "не уложился в кэп — сделано повторов:" in out


def test_amrap_interval_rounds_and_weight_per_round():
    blocks = [{"header": "AMRAP", "format": "amrap_interval", "rounds": 5, "reps": None,
               "work_min": 3.0, "rest_min": 1.0, "has_cap": False,
               "movements": [{"name": "рывки", "canon": "snatch", "weighted": True},
                             {"name": "подтягивания", "canon": "pull_up", "weighted": False}],
               "benchmark": None}]
    out = render_template(blocks)
    assert "AMRAP (5×3мин):" in out
    assert out.count("круги, амрап") == 5
    assert out.count("вес «рывки»:") == 5
    assert "круги, амрап 5:" in out


def test_amrap_single_rounds_reps():
    blocks = [{"header": "AMRAP", "format": "amrap", "rounds": 1, "reps": None,
               "work_min": 20.0, "rest_min": None, "has_cap": False,
               "movements": [{"name": "подтягивания", "canon": "pull_up", "weighted": False}],
               "benchmark": None}]
    out = render_template(blocks)
    assert "кругов:" in out
    assert "повторов (неполный круг):" in out


def test_death_by():
    blocks = [{"header": "Death by", "format": "death_by", "rounds": None, "reps": None,
               "work_min": None, "rest_min": None, "has_cap": False,
               "movements": [{"name": "бёрпи", "canon": "burpee", "weighted": False}],
               "benchmark": None}]
    out = render_template(blocks)
    assert "дошёл до минуты:" in out
    assert "повторов в незавершённой:" in out


def _ladder(scheme):
    return [{"header": "WOD№1  12 мин", "format": "ladder", "scheme": scheme,
             "rounds": None, "reps": None, "work_min": None, "rest_min": None,
             "has_cap": False, "benchmark": None,
             "movements": [{"name": "Взятие и толчок", "canon": "clean_jerk",
                            "canons": ["clean_jerk"], "weighted": True}]}]


def test_ladder_string_scheme_not_split_into_chars():
    out = render_template(_ladder("7-5-3 Взятие и толчок / 4-3-2 Bar Muscle-Up"))
    assert len(out.splitlines()) <= 5
    assert "раунд 7 - В повт" not in out
    assert "7---5---3-" not in out
    assert "время (мм:сс):" in out


def test_ladder_numeric_string_scheme_renders_rounds():
    out = render_template(_ladder("10-8-6-4-2"))
    assert "WOD№1  12 мин (10-8-6-4-2):" in out
    assert "раунд 1 - 10 повт, вес:" in out
    assert "раунд 5 - 2 повт, вес:" in out


def test_ladder_empty_scheme_falls_back():
    out = render_template(_ladder([]))
    assert "раунд" not in out
    assert "время (мм:сс):" in out


def test_ladder_scheme_list_of_strings():
    out = render_template(_ladder(["7", "5"]))
    assert "раунд 1 - 7 повт, вес:" in out
    assert "раунд 2 - 5 повт, вес:" in out
    assert len(out.splitlines()) <= 5


def test_ladder_junk_scheme_falls_back():
    out = render_template(_ladder("80%"))
    assert "раунд" not in out
    assert "время (мм:сс):" in out


def _gym(name, canon):
    return [{"header": "Гимнастика", "format": "other", "rounds": None, "reps": None,
             "work_min": None, "rest_min": None, "has_cap": False, "scheme": None,
             "benchmark": None,
             "movements": [{"name": name, "canon": canon, "weighted": False}]}]


def test_gym_skill_asks_reps_not_result():
    # BUG 2026-07-23: скилл-блок из гимнастики спрашивал голое «результат»
    out = render_template(_gym("Bar Muscle-Up", "bar_muscle_up"))
    assert "выполнено выходов:" in out
    assert "результат:" not in out


def test_gym_skill_pushup_uses_reps_noun():
    out = render_template(_gym("отжимания", "push_up"))
    assert "выполнено повторов:" in out
    assert "выходов" not in out


def test_gym_skill_per_set_asks_rounds():
    out = render_template(_gym("Bar Muscle-Up ×5", "bar_muscle_up"))
    assert "кругов (по 5 выходов):" in out
    assert "выполнено выходов:" not in out


def test_non_gym_other_still_result():
    # защита: неопознанное движение в other-блоке по-прежнему «результат»
    out = render_template(_gym("растяжка на шпагат", None))
    assert "результат:" in out
    assert "выполнено" not in out


def test_gym_skill_multiple_movements_labeled():
    blocks = [{"header": "Скилл", "format": "other", "rounds": None, "reps": None,
               "work_min": None, "rest_min": None, "has_cap": False, "scheme": None,
               "benchmark": None,
               "movements": [{"name": "Bar Muscle-Up", "canon": "bar_muscle_up", "weighted": False},
                             {"name": "отжимания", "canon": "push_up", "weighted": False}]}]
    out = render_template(blocks)
    assert "Bar Muscle-Up — выполнено выходов:" in out
    assert "отжимания — выполнено повторов:" in out


def test_ladder_per_movement_per_round_units():
    blocks = [{"header": "WOD", "format": "ladder", "scheme": [21, 15, 9], "rounds": 3,
               "reps": None, "work_min": None, "rest_min": None, "has_cap": False,
               "benchmark": None,
               "movements": [{"name": "становая тяга", "canon": "deadlift", "weighted": True},
                             {"name": "гребля", "canon": "row", "weighted": False},
                             {"name": "бёрпи", "canon": "burpee", "weighted": False}]}]
    out = render_template(blocks)
    assert "становая тяга:" in out
    assert "раунд 1 - 21 повт, вес:" in out      # weighted -> вес
    assert "раунд 2 - 15 ккал:" in out            # cardio -> ккал
    assert "раунд 3 - 9 повт:" in out             # gymnastics -> повт
    assert "время (мм:сс):" in out
