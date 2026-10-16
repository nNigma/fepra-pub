"""Онтология под каталог программ: толчок со стоек, силовое взятие, тяги; обратная совместимость."""
from __future__ import annotations

from tj import ontology as o


def test_jerk_aliases():
    for a in ("jerk", "split jerk", "push jerk", "power jerk", "толчок со стоек", "толчок с груди"):
        assert o.resolve(a) == "jerk", a


def test_tolchok_stays_clean_and_jerk():
    # в русской ТА «толчок» = взятие+толчок; ножницы/разножка — фаза того же упражнения
    for a in ("толчок", "толчок штанги", "толчок в ножницы", "толчок в разножку",
              "взятие и толчок", "взятие+толчок", "clean and jerk", "c&j"):
        assert o.resolve(a) == "clean_and_jerk", a


def test_push_press_stays_push_press():
    assert o.resolve("швунг") == "push_press"
    assert o.resolve("push press") == "push_press"


def test_power_clean_split_from_clean_floor():
    for a in ("pc", "power clean", "силовое взятие", "взятие в стойку"):
        assert o.resolve(a) == "power_clean", a
    # прочие взятия остаются в clean_floor
    for a in ("взятие с пола", "взятие на грудь", "взятие в сед"):
        assert o.resolve(a) == "clean_floor", a


def test_pulls_and_hang_snatch():
    assert o.resolve("тяга на рывок") == "snatch_pull"
    assert o.resolve("рывковая тяга") == "snatch_pull"
    assert o.resolve("тяга на взятие") == "clean_pull"
    assert o.resolve("классическая тяга") == "clean_pull"
    assert o.resolve("рывок с виса") == "hang_snatch"
    # старые алиасы не задеты
    assert o.resolve("становая тяга") == "deadlift"
    assert o.resolve("тяга на грудь") == "clean"


def test_new_canons_are_weighted_barbell():
    for c in ("jerk", "power_clean", "snatch_pull", "clean_pull", "hang_snatch"):
        assert o.category(c) == "barbell" and o.is_weighted(c), c


def test_phrase_search_with_new_canons():
    assert o.find("толчок со стоек") == ["jerk"]
    assert o.find("тяга на рывок") == ["snatch_pull"]
