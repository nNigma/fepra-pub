from __future__ import annotations

from tj.analysis.wod_notation import parse_notation, has_cap, parse_weight_reps


def test_emom_rounds_and_reps():
    n = parse_notation("Е2МОМх5х5х80%")
    assert n["format"] == "emom_strength"
    assert n["rounds"] == 5 and n["reps"] == 5


def test_emom_plain_with_duration():
    assert parse_notation("EMOM x 5 мин x 40%")["rounds"] == 5
    assert parse_notation("EMOM 15 мин")["rounds"] == 15
    assert parse_notation("E2MOM x 5")["rounds"] == 5
    assert parse_notation("е момент") is None


def test_emom_interval_digit_glyph():
    n = parse_notation("EZMOM x 5 x 5 x 65%")
    assert n["format"] == "emom_strength" and n["rounds"] == 5 and n["reps"] == 5
    assert parse_notation("EZ MOM x 5 x 5")["rounds"] == 5
    assert parse_notation("ESMOM x 3")["rounds"] == 3


def test_emom_rounds_only_percent_second():
    n = parse_notation("Е1,5МОМх5х70%-80%")
    assert n["format"] == "emom_strength"
    assert n["rounds"] == 5 and n["reps"] is None


def test_emom_rounds_only_dalee():
    n = parse_notation("Е1,5МОМх5х далее 80%")
    assert n["rounds"] == 5 and n["reps"] is None


def test_amrap_interval():
    n = parse_notation("AMRAP 3 мин х 5 / 1 мин отдых")
    assert n["format"] == "amrap_interval"
    assert n["rounds"] == 5 and n["work_min"] == 3.0 and n["rest_min"] == 1.0


def test_amrap_single():
    n = parse_notation("AMRAP в 20 минут")
    assert n["format"] == "amrap" and (n["rounds"] in (None, 1))


def test_sets():
    n = parse_notation("3 сета")
    assert n["rounds"] == 3


def test_not_notation():
    assert parse_notation("приседание со штангой на спине") is None


def test_has_cap():
    assert has_cap("для времени, кэп 12 мин") is True
    assert has_cap("3 сета") is False


def test_parse_weight_reps():
    assert parse_weight_reps("80×5") == (80.0, 5)
    assert parse_weight_reps("80x3") == (80.0, 3)
    assert parse_weight_reps("72,5*2") == (72.5, 2)
    assert parse_weight_reps("100") == (100.0, 1)
    assert parse_weight_reps("___") is None
    assert parse_weight_reps("") is None


def test_parse_weight_reps_cyrillic_x():
    assert parse_weight_reps("75 х 5") == (75.0, 5)
    assert parse_weight_reps("77.5 х 1") == (77.5, 1)
    assert parse_weight_reps("80×5") == (80.0, 5)
    assert parse_weight_reps("80x3") == (80.0, 3)


def test_rep_scheme():
    n = parse_notation("21-15-9")
    assert n["format"] == "ladder" and n["scheme"] == [21, 15, 9] and n["rounds"] == 3
    assert parse_notation("50-40-30-20-10")["scheme"] == [50, 40, 30, 20, 10]


def test_rep_scheme_with_block_marker():
    assert parse_notation("3 21-15-9")["scheme"] == [21, 15, 9]
    assert parse_notation("(3) 21-15-9")["scheme"] == [21, 15, 9]


def test_percent_range_is_not_scheme():
    assert parse_notation("Е1,5МОМх5х70%-80%")["format"] == "emom_strength"


def test_weight_ramp_line_is_not_scheme():
    assert parse_notation("становая 100-110-130") is None
