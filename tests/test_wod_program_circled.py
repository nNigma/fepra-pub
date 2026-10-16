from __future__ import annotations

from tj.analysis.wod_program import movements_of, parse_program

MINIMAL = """Разминка
③WOD№1
3 раунда
10 приседания со штангой над головой"""

ALL_SECTIONS = """① Разминка
- 10 приседания без веса
② ТА
Е2МОМ х 5 х 80%
становая тяга
③ WOD EMOM
5 раундов
10 трастеры
④ WODNº2
3 раунда
15 подтягивания"""


def test_minimal_circled_glued_wod_recovers_movements():
    b = parse_program(MINIMAL)
    canon, unknown = movements_of(b)
    assert b, "непустой текст не должен давать 0 блоков"
    assert "back_squat" in canon


def test_all_sections_yield_movements():
    b = parse_program(ALL_SECTIONS)
    canon, unknown = movements_of(b)
    assert len(b) == 3
    assert b[0]["format"] == "emom_strength"
    assert b[1]["format"] == "for_time" and b[2]["format"] == "for_time"
    assert b[2]["header"].startswith("WODNº2")
    assert "deadlift" in canon and "thruster" in canon and "pull_up" in canon
    assert not any("WODNº2" in u for u in unknown)


def test_warmup_movement_excluded():
    b = parse_program(ALL_SECTIONS)
    joined = " ".join(m["name"] for x in b for m in x["movements"]).lower()
    assert "без веса" not in joined


def test_glued_wodnum_slitno():
    b = parse_program("① Актив\n③WOD№1\n3 раунда\n10 бёрпи")
    canon, _ = movements_of(b)
    assert b and "burpee" in canon


def test_start_warmup_plus_glued_wodnum():
    b = parse_program("Разминка\n④WODNº2\n2 раунда\n12 подтягивания")
    canon, _ = movements_of(b)
    assert b and "pull_up" in canon


def test_circled_tya_strength_closes_warmup():
    b = parse_program(
        "① Разминка\n- 10 приседания без веса\n② ТЯ\nЕ2МОМ х 4 х 75%\nприседания со штангой")
    canon, _ = movements_of(b)
    joined = " ".join(m["name"] for x in b for m in x["movements"]).lower()
    assert b and b[0]["format"] == "emom_strength" and "back_squat" in canon
    assert "без веса" not in joined


def test_glued_circle_equals_spaced():
    spaced = ("Разминка\n- 10 без веса\n① Сила\nЕ2МОМ х 5 х 80%\n"
              "приседания со штангой\n② WOD\n3 раунда\n10 трастеры")
    glued = spaced.replace("① ", "①").replace("② ", "②")
    bs, bg = parse_program(spaced), parse_program(glued)
    assert bg and len(bg) == len(bs) == 2
    assert movements_of(bg)[0] == movements_of(bs)[0]


def test_failopen_trapped_content_not_lost():
    b = parse_program("Разминка\nнепонятная штука тут\n3 раунда\n10 бёрпи")
    canon, _ = movements_of(b)
    assert b and "burpee" in canon


def test_failopen_pure_garbage_stays_empty():
    assert parse_program("asdf jkl qwe") == []
    assert parse_program("") == []
