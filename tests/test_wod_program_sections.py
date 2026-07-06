from __future__ import annotations

from tj.analysis.wod_program import parse_program, render_template

PROG = """Программа Universe на 2026-07-04:
1. Суставная разминка
2. Активация
2 сета:
- 15 гиперэкстензия
- 10 приседаний гоблет с гирей медленных
3. Сила
ПСШНС с паузой в нижней точке 3 секунды
Е2МОМх4х2х80-83%
4. Комплекс
5 сетов:
- 1250м байк/500 м гребля/500 м лыжи
- 10 нкп
- 10 жимов лёжа штанги, 60-50 кг
3 минуты отдыха
5 сетов:
- 1000м байк/400 м гребля/400 м лыжи
- 10 прыжков через бокс
- 10 швунгов, 60-50 кг
3 минуты отдых
5 сетов:
- 750 м байк/300 м гребля/300 м лыжи
- 10 берпи через бокс
- 10 взятий с виса на грудь, 60-50 кг"""


def test_sections_split_into_strength_plus_three_metcons():
    b = parse_program(PROG)
    assert len(b) == 4
    assert b[0]["format"] == "emom_strength" and b[0]["rounds"] == 4 and b[0]["reps"] == 2
    metcons = b[1:]
    assert all(x["format"] == "for_time" and x["rounds"] == 5 for x in metcons)
    assert [x["header"] for x in metcons] == ["Комплекс 1", "Комплекс 2", "Комплекс 3"]


def test_warmup_activation_skipped():
    b = parse_program(PROG)
    joined = " ".join(m["name"] for x in b for m in x["movements"]).lower()
    assert "гиперэкстен" not in joined and "гоблет" not in joined


def test_strength_movement_before_notation_captured():
    b = parse_program(PROG)
    assert "ПСШНС" in b[0]["movements"][0]["name"]


def test_template_has_strength_rounds_metcon_time_and_weight():
    tmpl = render_template(parse_program(PROG))
    assert tmpl.count("раунд") == 4
    assert tmpl.count("время (мм:сс)") == 3
    assert "вес" in tmpl and "кг" in tmpl.lower()
