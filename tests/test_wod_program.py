from __future__ import annotations

from tj.analysis.wod_program import annotate, parse_program

BOARD = """Актив.
2 сета:
- 10 гиперэкстензий
- 1 мин кардио

2 ТА.
- Е2МОМх5х5х80%
приседание со штангой на спине
- Е1,5МОМх5х70%-80%
2 взятия на грудь + толчок в ножницы

3 WOD
3 сета:
- 20 прыжки через бокс
- 15 фронтальный присед с гантелью

4 AMRAP 3 мин х 5 / 1 мин отдых
- 16 рывков
- 8 подтягивания
- 4 челночный бег
"""


def _by_format(blocks, fmt):
    return [b for b in blocks if b["format"] == fmt]


def test_skips_warmup():
    blocks = parse_program(BOARD)
    joined = " ".join((b["header"] or "") + " ".join(m["name"] for m in b["movements"])
                      for b in blocks).lower()
    assert "гиперэкстенз" not in joined


def test_strength_blocks_per_movement():
    blocks = parse_program(BOARD)
    st = _by_format(blocks, "emom_strength")
    assert len(st) == 2
    sq = st[0]
    assert sq["rounds"] == 5 and sq["reps"] == 5
    assert sq["movements"][0]["canon"] == "back_squat"
    cj = st[1]
    assert cj["rounds"] == 5
    assert cj["movements"][0]["canon"] == "clean_and_jerk"


def test_wod_fixed_weighted_detection():
    blocks = parse_program(BOARD)
    wod = _by_format(blocks, "for_time")[0]
    weighted = [m for m in wod["movements"] if m["weighted"]]
    names = [m["canon"] for m in weighted]
    assert "front_squat" in names
    assert all(m["canon"] != "box_jump_over" or not m["weighted"] for m in wod["movements"])


def test_amrap_interval():
    blocks = parse_program(BOARD)
    am = _by_format(blocks, "amrap_interval")[0]
    assert am["rounds"] == 5 and am["work_min"] == 3.0 and am["rest_min"] == 1.0
    assert any(m["canon"] == "snatch" and m["weighted"] for m in am["movements"])
    assert any(m["canon"] == "pull_up" and not m["weighted"] for m in am["movements"])


def test_annotate_rounds():
    out = annotate("Е2МОМх5х5х80%\nприседание со штангой на спине")
    assert "(5 раундов по 5 повторений)" in out


def test_annotate_rounds_only():
    out = annotate("Е1,5МОМх5х70%-80%")
    assert "(5 раундов)" in out


def test_annotate_leaves_plain_lines():
    out = annotate("приседание со штангой на спине")
    assert out.strip() == "приседание со штангой на спине"


def test_movements_of():
    from tj.analysis.wod_program import parse_program, movements_of
    board = ("2 ТА.\n- Е2МОМх5х5х80%\nприседание со штангой на спине\n"
             "4 AMRAP 3 мин х 5\n- 16 рывков\n- 8 подтягивания\n")
    canon, unknown = movements_of(parse_program(board))
    assert "back_squat" in canon and "snatch" in canon and "pull_up" in canon
    assert canon == list(dict.fromkeys(canon))


def test_alternative_reps_line_keeps_both_movements():
    # «50 ДП или 75 ОП» — альтернатива: должны попасть оба движения
    from tj.analysis.wod_program import parse_program, movements_of
    board = "WOD N1\n10-8-6-4-2\nОверхед\n50 ДП или 75 ОП\n"
    canon, _ = movements_of(parse_program(board))
    assert "overhead_squat" in canon
    assert "double_under" in canon and "single_under" in canon


def test_ladder_block_no_junk_movement():
    board = "3 WOD\n21-15-9\n- становая тяга\n- гребля\n- бёрпи\n"
    blocks = parse_program(board)
    wod = [b for b in blocks if b["format"] == "ladder"][0]
    assert wod["scheme"] == [21, 15, 9] and wod["rounds"] == 3
    names = [m["name"] for m in wod["movements"]]
    assert "становая тяга" in names and "гребля" in names and "бёрпи" in names
    assert all("15-9" not in n for n in names)     # мусорного движения нет


def test_annotate_rep_scheme():
    out = annotate("21-15-9")
    assert "(3 раунда: 21, 15, 9)" in out


def test_annotate_emom_leading_rounds():
    out = annotate("EMOM 4х2х90%")
    assert out == "EMOM 4х2х90% (4 раунда по 2 повторения)"


def test_annotate_idempotent():
    once = annotate("2 сета:")
    assert once == "2 сета: (2 раунда)"
    assert annotate(once) == once
    assert annotate(annotate(once)) == once


def test_annotate_collapses_accumulated_notes():
    dirty = "2 сета: (2 раунда) (2 раунда) (2 раунда)"
    assert annotate(dirty) == "2 сета: (2 раунда)"
