import re

from tj.analysis import state, levels

CYR = re.compile("[А-Яа-яЁё]")


def test_risk_flag_en_no_cyrillic():
    signals = {
        "rhr": ("above", True),
        "hrv": ("in", True),
        "bb_charge": ("below", True),
        "respiration_rest": ("in", True),
    }
    r = state.risk_flag(signals, lang="en")
    assert r["level"] == "amber"
    assert r["title"]
    assert not CYR.search(r["title"])


def test_risk_flag_en_red_no_cyrillic():
    signals = {
        "rhr": ("above", False),
        "hrv": ("below", True),
    }
    r = state.risk_flag(signals, lang="en")
    assert r["level"] == "red"
    assert not CYR.search(r["title"])


def test_goal_progress_level_en_no_cyrillic():
    g = {"kind": "level", "discipline": "deadlift", "target_value": "Продвинутый", "metric": "level"}
    tier = {"idx": 1, "level": "Любитель", "next_threshold": 158, "value": 130, "distance": 28, "unit": "kg"}
    p = levels.goal_progress(g, current_value=130, current_tier=tier, lang="en")
    assert p["done"] is False
    assert p.get("text")
    assert not CYR.search(p["text"])


def test_goal_progress_numeric_no_data_en_no_cyrillic():
    g = {"kind": "numeric", "discipline": "fran", "target_value": "240", "metric": "abs_sec"}
    p = levels.goal_progress(g, current_value=None, current_tier=None, lang="en")
    assert p.get("text")
    assert not CYR.search(p["text"])


def test_unit_label_en_no_cyrillic():
    assert levels._unit_label("kg", lang="en") == "kg"
    assert levels._unit_label("time", lang="en") == "s"
    assert not CYR.search(levels._unit_label("rounds", lang="en"))
