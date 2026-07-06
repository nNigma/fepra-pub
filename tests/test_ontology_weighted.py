from __future__ import annotations

from tj.ontology import is_weighted, category


def test_barbell_is_weighted():
    assert is_weighted("back_squat") is True
    assert is_weighted("snatch") is True
    assert is_weighted("clean_and_jerk") is True
    assert is_weighted("front_squat") is True


def test_gymnastics_and_cardio_not_weighted():
    assert is_weighted("pull_up") is False
    assert is_weighted("burpee") is False
    assert is_weighted("row") is False
    assert is_weighted("box_jump_over") is False


def test_unknown_not_weighted():
    assert is_weighted(None) is False
    assert is_weighted("челночный бег") is False


def test_category():
    assert category("row") == "cardio"
    assert category("pull_up") == "gymnastics"
    assert category("deadlift") == "barbell"
