from __future__ import annotations

from tj.analysis.wod_results import extract_maxes

BLOCKS = [
    {"header": "ТА", "format": "emom_strength", "rounds": 5, "reps": 5,
     "movements": [{"name": "приседание со штангой на спине", "canon": "back_squat", "weighted": True}]},
    {"header": "WOD", "format": "for_time", "rounds": 3,
     "movements": [{"name": "фронтальный присед с гантелью", "canon": "front_squat", "weighted": True}]},
]

FILLED = """приседание со штангой на спине:
  раунд 1 (вес×повторы): 80×5
  раунд 2 (вес×повторы): 82,5×5
  раунд 3 (вес×повторы): 85×3
  раунд 4 (вес×повторы): ___
  раунд 5 (вес×повторы): ___
WOD:
  вес «фронтальный присед с гантелью»: 20
  время (мм:сс): 8:36
"""


def test_extract_only_strength_best_set():
    maxes = extract_maxes(BLOCKS, FILLED)
    assert len(maxes) == 1
    m = maxes[0]
    assert m["movement"] == "приседание со штангой на спине"
    assert m["weight_kg"] == 85.0
    assert m["reps"] == 3


def test_wod_weight_not_in_maxes():
    maxes = extract_maxes(BLOCKS, FILLED)
    assert all("присед с гантелью" not in x["movement"] for x in maxes)
