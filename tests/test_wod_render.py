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
    assert "раунд 1 (вес×повторы): ___" in out
    assert "раунд 5 (вес×повторы): ___" in out


def test_for_time_fixed_weight_and_time():
    blocks = [{"header": "WOD", "format": "for_time", "rounds": 3, "reps": None,
               "work_min": None, "rest_min": None, "has_cap": False,
               "movements": [{"name": "прыжки через бокс", "canon": "box_jump_over", "weighted": False},
                             {"name": "фронтальный присед с гантелью", "canon": "front_squat", "weighted": True}],
               "benchmark": None}]
    out = render_template(blocks)
    assert "вес «фронтальный присед с гантелью»: ___" in out
    assert "время (мм:сс): ___" in out
    assert "прыжки через бокс" not in out.split("время")[0].replace("вес «", "")


def test_reps_at_cap():
    blocks = [{"header": "WOD", "format": "for_time", "rounds": 1, "reps": None,
               "work_min": None, "rest_min": None, "has_cap": True,
               "movements": [], "benchmark": None}]
    out = render_template(blocks)
    assert "не уложился в кэп — сделано повторов: ___" in out


def test_amrap_interval_rounds_and_weight_per_round():
    blocks = [{"header": "AMRAP", "format": "amrap_interval", "rounds": 5, "reps": None,
               "work_min": 3.0, "rest_min": 1.0, "has_cap": False,
               "movements": [{"name": "рывки", "canon": "snatch", "weighted": True},
                             {"name": "подтягивания", "canon": "pull_up", "weighted": False}],
               "benchmark": None}]
    out = render_template(blocks)
    assert "AMRAP (5×3мин):" in out
    assert out.count("круги, амрап") == 5
    assert out.count("вес «рывки»: ___") == 5
    assert "круги, амрап 5: ___" in out


def test_amrap_single_rounds_reps():
    blocks = [{"header": "AMRAP", "format": "amrap", "rounds": 1, "reps": None,
               "work_min": 20.0, "rest_min": None, "has_cap": False,
               "movements": [{"name": "подтягивания", "canon": "pull_up", "weighted": False}],
               "benchmark": None}]
    out = render_template(blocks)
    assert "кругов: ___" in out
    assert "повторов (неполный круг): ___" in out


def test_death_by():
    blocks = [{"header": "Death by", "format": "death_by", "rounds": None, "reps": None,
               "work_min": None, "rest_min": None, "has_cap": False,
               "movements": [{"name": "бёрпи", "canon": "burpee", "weighted": False}],
               "benchmark": None}]
    out = render_template(blocks)
    assert "дошёл до минуты: ___" in out
    assert "повторов в незавершённой: ___" in out


def test_ladder_per_movement_per_round_units():
    blocks = [{"header": "WOD", "format": "ladder", "scheme": [21, 15, 9], "rounds": 3,
               "reps": None, "work_min": None, "rest_min": None, "has_cap": False,
               "benchmark": None,
               "movements": [{"name": "становая тяга", "canon": "deadlift", "weighted": True},
                             {"name": "гребля", "canon": "row", "weighted": False},
                             {"name": "бёрпи", "canon": "burpee", "weighted": False}]}]
    out = render_template(blocks)
    assert "становая тяга:" in out
    assert "раунд 1 - 21 повт, вес: ___" in out
    assert "раунд 2 - 15 ккал: ___" in out
    assert "раунд 3 - 9 повт: ___" in out
    assert "время (мм:сс): ___" in out
