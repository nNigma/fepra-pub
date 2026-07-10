from __future__ import annotations
from tj.analysis.wod_notation import parse_notation, parse_weight_reps

def test_emom_script_mix():
    for s, r in [("Е2МОМх5", 5), ("E2MOM x 5", 5), ("Е2МОМ x5", 5),
                 ("EMOM x 5 мин x 40%", 5), ("EMOM 15 мин", 15), ("емом 10 мин", 10),
                 ("E1.5MOM x 5", 5), ("ЕМОМ x 3 мин", 3)]:
        n = parse_notation(s)
        assert n and n["format"] == "emom_strength" and n["rounds"] == r, (s, n)

def test_emom_reps_preserved():
    n = parse_notation("Е2МОМх5х5х80%")
    assert n["rounds"] == 5 and n["reps"] == 5
    n2 = parse_notation("Е1,5МОМх5х70%-80%")
    assert n2["rounds"] == 5 and n2["reps"] is None

def test_amrap_script_mix():
    for s in ["AMRAP 12 мин", "АМРАП 12 мин", "amrap 12 min"]:
        n = parse_notation(s)
        assert n and n["format"] == "amrap", (s, n)
    for s in ["amrap 3 мин х 5 / 1 мин отдых", "AMRAP (5×3мин)"]:
        n = parse_notation(s)
        assert n and n["format"] == "amrap_interval" and n["rounds"] == 5, (s, n)

def test_sets_rounds_words():
    for s, r in [("3 сета", 3), ("3 раунда", 3), ("5 rounds", 5), ("3 round", 3), ("4 круга", 4)]:
        assert parse_notation(s)["rounds"] == r, s

def test_rep_scheme_dash_variants():
    assert parse_notation("21-15-9")["scheme"] == [21, 15, 9]
    assert parse_notation("50–40–30")["scheme"] == [50, 40, 30]   # en-dash

def test_weight_reps_variants():
    for s, exp in [("80х5",(80.0,5)),("80x5",(80.0,5)),("80×5",(80.0,5)),
                   ("80*5",(80.0,5)),("72,5 х 2",(72.5,2)),("100",(100.0,1))]:
        assert parse_weight_reps(s) == exp, s

def test_negatives_no_false_positive():
    assert parse_notation("е момент") is None
    assert parse_notation("рывок 6 см") is None
    assert parse_notation("становая 100-110-130") is None   # вес-раскладка, не схема

def test_cap_variants():
    from tj.analysis.wod_notation import has_cap
    assert has_cap("кэп 12 мин") and has_cap("time cap 10") and has_cap("лимит 8 мин")
    assert not has_cap("3 сета")
