from __future__ import annotations
from tjbot import vision


def test_valid_meal_passes_quality():
    data = {"foods": [{"name": "греча с курицей", "kcal": 500}],
            "quality": 1, "quality_note": "цельная еда, белок на месте"}
    out = vision._valid_meal(data)
    assert out["quality"] == 1
    assert out["quality_note"] == "цельная еда, белок на месте"


def test_valid_meal_bad_quality_dropped():
    data = {"foods": [{"name": "x", "kcal": 500}], "quality": 9, "quality_note": 5}
    out = vision._valid_meal(data)
    assert out["quality"] is None and out["quality_note"] is None


def test_valid_meal_bool_quality_dropped():
    data = {"foods": [{"name": "x", "kcal": 500}], "quality": True, "quality_note": "y"}
    out = vision._valid_meal(data)
    assert out["quality"] is None
