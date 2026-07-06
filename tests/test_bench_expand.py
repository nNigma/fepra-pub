from __future__ import annotations

from tj.analysis.benchmarks import expand
from tj.analysis.wod_program import parse_program, render_template, movements_of


def test_expand_fran_male():
    blocks = expand("Fran", sex="m")
    assert blocks and len(blocks) == 1
    b = blocks[0]
    assert b["benchmark"] == "fran"
    assert b["scheme"] == [21, 15, 9]
    assert [m["canon"] for m in b["movements"]] == ["thruster", "pull_up"]
    thr = b["movements"][0]
    assert thr["weighted"] and "43" in thr["name"]
    assert not b["movements"][1]["weighted"]


def test_expand_alias_cyrillic():
    assert expand("фрэн")[0]["benchmark"] == "fran"
    assert expand("не бенчмарк") is None


def test_expand_female_weight():
    assert "29" in expand("Fran", sex="f")[0]["movements"][0]["name"]


def test_parse_program_expands_fran_board():
    blocks = parse_program("Fran")
    assert len(blocks) == 1 and blocks[0]["benchmark"] == "fran"
    canon, _ = movements_of(blocks)
    assert canon == ["thruster", "pull_up"]
    tmpl = render_template(blocks)
    assert "21" in tmpl and "время" in tmpl.lower()


def test_parse_program_cindy_amrap():
    blocks = parse_program("Cindy")
    assert blocks[0]["benchmark"] == "cindy"
    assert blocks[0]["format"] == "amrap"
    assert blocks[0]["work_min"] == 20


def test_clean_move_keeps_leading_m_word():
    from tj.analysis.wod_program import _clean_move
    assert _clean_move("15 махи гирей") == "махи гирей"
    assert _clean_move("10 махи") == "махи"
    assert _clean_move("400 м бег") == "бег"
    assert _clean_move("20 кал гребля") == "гребля"
    assert _clean_move("15 pull ups") == "pull ups"
