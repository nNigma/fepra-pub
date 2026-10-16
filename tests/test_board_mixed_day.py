"""Смешанный день из жизни: силовая 5×5 без заголовка секции, лесенка с гантелями и
интервальный WOD «40 сек работа / 20 отдых» (баг 29.09: силовая пропала, второй WOD
слился с первым и получил схему 21-15-9)."""
from __future__ import annotations

import pytest

from pathlib import Path

from tj.analysis import wod_program as wp
from tj.analysis import wod_results
from tj.services import board

TEXT = (Path(__file__).parent / "data" / "board_mixed_day.txt").read_text(encoding="utf-8")


def _blocks():
    return wp.parse_program(TEXT, {})


def test_three_blocks_in_order():
    b = _blocks()
    assert [x["format"] for x in b] == ["strength", "ladder", "stations"]
    assert b[0]["movements"][0]["canon"] == "front_squat"
    assert (b[0]["rounds"], b[0]["reps"]) == (5, 5)
    assert b[1]["scheme"] == [21, 15, 9]
    assert [m["name"] for m in b[1]["movements"]] == [
        "Трастеры с гантелями", "Рывок гантели", "Берпи с подтягиванием"]


def test_second_wod_is_intervals_not_ladder():
    st = _blocks()[2]
    assert (st["work_sec"], st["rest_sec"]) == (40, 20)
    assert st["scheme"] is None
    assert len(st["movements"]) == 10
    assert st["movements"][0]["name"] == "Берпи на блин"
    tpl = wp.render_template(_blocks())
    assert "Wod#2 (40/20 сек)" in tpl
    wod2 = tpl.split("Wod#2")[1]
    assert "21 повт" not in wod2 and "раунд 1 -" not in wod2


def test_strength_form_has_five_sets_with_default_reps():
    form = board.result_form(_blocks())
    s = form["blocks"][0]
    assert s["kind"] == "strength" and len(s["fields"]) == 5
    assert all(f["type"] == "weight_reps" and f["reps_default"] == 5 for f in s["fields"])
    assert s["fields"][0]["movement"] == "Фронтальный присед"


def test_ladder_weight_field_takes_reps_and_defaults_to_scheme():
    form = board.result_form(_blocks())
    lad = form["blocks"][1]
    wf = [f for f in lad["fields"] if f["section"] == "Трастеры с гантелями"]
    assert [f["type"] for f in wf] == ["weight_reps"] * 3
    assert [f["reps_default"] for f in wf] == [21, 15, 9]
    # вес без повторов -> повторы по схеме; с повторами -> как ввёл атрибут
    assert board.normalize_value(wf[0], {"weight": 22.5}) == "22.5x21"
    assert board.normalize_value(wf[1], {"weight": 22.5, "reps": 12}) == "22.5x12"


def test_station_fields_by_kind():
    form = board.result_form(_blocks())
    by = {(f["section"], f["label"].split(",")[0]): f for f in form["blocks"][2]["fields"]}
    # кардио: ккал ИЛИ метры ИЛИ время — тип cardio, единицу выбирает атлет
    assert by[("Гребля", "кардио")]["type"] == "cardio" and by[("Гребля", "кардио")]["default_unit"] == "kcal"
    assert by[("Лыжи", "кардио")]["type"] == "cardio"
    # сани: вес И дистанция
    assert by[("Толкание саней", "вес и дистанция")]["type"] == "weight_distance"
    assert by[("Планка на руках", "удержание")]["unit"] == "сек"
    # снаряд с весом: вес × повторы (вес обязателен), без веса: повторы + вес по желанию
    assert by[("Махи гирей", "результат (вес×повторы)")]["type"] == "weight_reps"
    assert by[("Кластеры", "результат (вес×повторы)")]["type"] == "weight_reps"
    assert by[("Отжимания", "повторы")]["type"] == "reps_load"
    assert by[("Берпи на блин", "повторы")]["type"] == "reps_load"


def test_cardio_accepts_kcal_meters_or_time_in_sec_or_min():
    f = {"key": "k", "label": "кардио, ккал", "type": "cardio", "default_unit": "kcal"}
    assert board.normalize_value(f, 22) == "22 ккал"                     # без единицы — по умолчанию
    assert board.normalize_value(f, {"unit": "kcal", "value": 22}) == "22 ккал"
    assert board.normalize_value(f, {"unit": "m", "value": 250}) == "250 м"
    assert board.normalize_value(f, {"unit": "sec", "value": 40}) == "40 сек"
    assert board.normalize_value(f, {"unit": "min", "value": 1.5}) == "1.5 мин"
    assert board.normalize_value(f, {"unit": "time", "value": "0:40"}) == "0:40 время"   # прежний формат
    assert board.normalize_value(f, None) == ""
    try:
        board.normalize_value(f, {"unit": "km", "value": 1})
        raise AssertionError("нужна ошибка")
    except board.Invalid:
        pass


def test_sled_weight_distance_and_time():
    f = {"key": "s", "label": "вес и дистанция", "type": "weight_distance"}
    assert board.normalize_value(f, {"weight": 100, "meters": 20}) == "100 кг, 20 м"
    assert board.normalize_value(f, {"weight": 100, "meters": 20, "time": 45, "time_unit": "sec"}) == \
        "100 кг, 20 м, 45 сек"
    assert board.normalize_value(f, {"time": 2, "time_unit": "min"}) == "2 мин"
    assert board.normalize_value(f, {"time": 30}) == "30 сек"              # единица по умолчанию — секунды
    assert board.normalize_value(f, {"weight": 100}) == "100 кг"
    assert board.normalize_value(f, {"meters": 30}) == "30 м"
    assert board.normalize_value(f, {}) == ""
    try:
        board.normalize_value(f, {"time": 5, "time_unit": "hours"})
        raise AssertionError("нужна ошибка")
    except board.Invalid:
        pass


def test_reps_load_weight_optional():
    f = {"key": "r", "label": "повторы, вес по желанию", "type": "reps_load"}
    assert board.normalize_value(f, {"reps": 25}) == "25"
    assert board.normalize_value(f, {"reps": 18, "weight": 10}) == "10x18"
    assert board.normalize_value(f, "22.5x30") == "22.5x30"
    try:
        board.normalize_value(f, {"weight": 10})
        raise AssertionError("нужны повторы")
    except board.Invalid:
        pass


def _fill(form, spec):
    idx = {(f["section"], f["label"]): f["key"] for b in form["blocks"] for f in b["fields"]}
    return {idx[k]: v for k, v in spec.items()}


def test_filled_day_goes_through_parsers():
    blocks = _blocks()
    form = board.result_form(blocks)
    vals = _fill(form, {
        ("Фронтальный присед", "раунд 1 (вес×повторы)"): {"weight": 80, "reps": 5},
        ("Фронтальный присед", "раунд 2 (вес×повторы)"): {"weight": 85, "reps": 4},
        ("Берпи с подтягиванием", "время (мм:сс)"): "9:40",
        ("Wod#2 (40/20 сек)", "кругов"): 2,
        ("Гребля", "кардио, ккал"): {"unit": "m", "value": 250},
        ("Толкание саней", "вес и дистанция"): {"weight": 100, "meters": 20, "time": 45, "time_unit": "sec"},
        ("Отжимания", "повторы, вес по желанию"): {"reps": 25},
        ("Махи гирей", "результат (вес×повторы)"): {"weight": 24, "reps": 30},
    })
    text = board.fill_template(form, vals)
    assert wod_results.extract_maxes(blocks, text) == [
        {"movement": "Фронтальный присед", "weight_kg": 85.0, "reps": 4}]
    data, lines = wod_results.summarize_filled(blocks, text)
    assert data["times_sec"] == [580]                       # время лесенки не теряется
    assert any(l.startswith("Wod#1") and "9:40" in l for l in lines)
    assert data["stations"][0]["rounds"] == "2"
    assert any("Гребля 250 м" in l and "Толкание саней 100 кг, 20 м, 45 сек" in l
               and "Отжимания 25 повт" in l and "Махи гирей 24x30" in l for l in lines)


def test_strength_line_variants_and_non_barbell_ignored():
    for line in ("Присед 5x5", "- Фронтальный присед 3х8", "5×5 Становая тяга", "Жим лёжа 4×6 80%"):
        b = wp.parse_program(line, {})
        assert b and b[0]["format"] == "strength", line
    # блочное упражнение не с штангой и обычная схема не становятся силовым блоком
    assert not [x for x in wp.parse_program("Wall ball 4x15", {}) if x["format"] == "strength"]


def test_interval_header_variants():
    for h in ("Wod#2 (40 сек работа 20 отдых)", "Метабол 40 сек работы / 20 сек отдыха",
              "Интервалы 40/20 сек", "WOD 2: 40 on 20 off"):
        b = wp.parse_program(f"{h}\nБерпи\nГребля", {})
        assert b and b[0]["format"] == "stations" and (b[0]["work_sec"], b[0]["rest_sec"]) == (40, 20), h


def test_for_time_and_amrap_weight_is_weight_by_reps_with_optional_reps():
    for txt in ("3 раунда на время\nDevil press 22.5\nБерпи", "AMRAP 12 мин\nТрастеры 40 кг\nПодтягивания"):
        form = board.result_form(wp.parse_program(txt, {}))
        wf = [f for b in form["blocks"] for f in b["fields"] if f["label"].startswith("вес «")]
        assert wf and all(f["type"] == "weight_reps" and f["reps_optional"] for f in wf), txt
        f = wf[0]
        assert board.normalize_value(f, {"weight": 22.5}) == "22.5"          # повторы не ввели
        assert board.normalize_value(f, {"weight": 22.5, "reps": 12}) == "22.5x12"
        assert board.normalize_value(f, "30") == "30"


def test_sled_like_stations_all_get_weight_distance_time():
    names = ["Толкание саней", "Тяга саней", "Тяга санок", "Sled push", "Sled pull", "Sled drag",
             "Бег с санями", "Волокуши", "Farmer carry", "Прогулка фермера", "Yoke carry"]
    b = wp.parse_program("Wod (40 сек работа 20 отдых)\n" + "\n".join(names), {})
    sec = {f["section"]: f["type"] for f in board.result_form(b)["blocks"][0]["fields"]}
    assert all(sec[n] == "weight_distance" for n in names), {n: sec[n] for n in names}


def test_ordinary_stations_not_taken_for_sled():
    names = ["Санта берпи", "Гребля", "Отжимания", "Бег", "Присед со штангой"]
    b = wp.parse_program("Wod (40 сек работа 20 отдых)\n" + "\n".join(names), {})
    sec = {f["section"]: f["type"] for f in board.result_form(b)["blocks"][0]["fields"]}
    assert sec["Гребля"] == "cardio" and sec["Бег"] == "cardio" and sec["Отжимания"] == "reps_load"


LIST_BOARD = """Wod ×2
100 м толкание саней
Бег 400 м
200 м прогулка фермера
500 м гребля
40 берпи на блин

E12MOM x2
15 кал байк
15 метров выпады
25 НКП
20 взятий гантелей
15 кал байк
15 метров выпады
"""


def test_repeated_station_lists_become_stations_with_quantities():
    from tj.analysis import wod_program as wp
    from tj.services.board import result_form
    blocks = wp.parse_program(LIST_BOARD, {})
    assert [(b["format"], b["rounds"], b.get("emom_total")) for b in blocks] == [("stations", 2, None), ("stations", None, 2)]
    assert [m["name"] for m in blocks[0]["movements"]][:2] == ["100 м толкание саней", "Бег 400 м"]
    form = result_form(blocks)
    types = [f["type"] for b in form["blocks"] for f in b["fields"]]
    assert "weight_distance" in types and "cardio" in types       # сани и кардио спрашиваются
    assert not any(f["label"] == "раунд 1 (вес×повторы)" for b in form["blocks"] for f in b["fields"])


def test_single_movement_emom_stays_strength():
    from tj.analysis import wod_program as wp
    b = wp.parse_program("EMOM x5\nПрисед 80%\n", {})
    assert [x["format"] for x in b] == ["emom_strength"]


def test_emom_with_movement_list_has_one_field_per_movement_not_per_round():
    from tj.analysis import wod_program as wp
    from tj.services.board import result_form
    board = """Wod ×2:
Трастеры
Рывки
Запрыгивания на бокс

EMOM ×20:
- Рывки + запрыгивания на бокс
- Трастеры

Wod ×3
- бег
- тяга гантелей + берпи
- бег
- толкание саней
"""
    blocks = wp.parse_program(board, {})
    assert [b["format"] for b in blocks] == ["stations"] * 3
    assert [(b["rounds"], b.get("emom_total")) for b in blocks] == [(2, None), (None, 20), (3, None)]
    form = result_form(blocks)
    counts = [len(b["fields"]) for b in form["blocks"]]
    assert counts == [4, 2, 5]                 # EMOM: по полю на упражнение, а не 20 строк на раунд
    emom = [f["section"] for f in form["blocks"][1]["fields"]]
    assert emom == ["Рывки + запрыгивания на бокс (10 раундов)", "Трастеры (10 раундов)"]   # 20 интервалов / 2 строки


@pytest.mark.parametrize("board,fmt", [
    ("WOD\nТрастеры 10\nБерпи 10\n", "for_time"),
    ("WOD:\n- Трастеры\n- Берпи\n", "stations"),
    ("WOD: For time\n50 берпи\n50 трастеров\n", "for_time"),
    ("WOD x2\nТрастеры\n", "stations"),
    ("Wod ×2:\nТрастеры\nБерпи\n", "stations"),
    ("WOD 2 раунда\nТрастеры\nБерпи\n", "for_time"),
    ("Wod 21-15-9\nтрастеры\nберпи\n", "ladder"),
])
def test_wod_header_always_opens_a_block(board, fmt):
    from tj.analysis import wod_program as wp
    blocks = wp.parse_program(board, {})
    assert blocks and blocks[0]["format"] == fmt and blocks[0]["movements"]


def test_emom_alternates_movements_across_minutes():
    from tj.analysis import wod_program as wp
    from tj.services.board import result_form
    b = wp.parse_program("EMOM x20\nТрастеры\nБерпи\n", {})
    assert b[0]["emom_total"] == 20 and len(b[0]["movements"]) == 2
    secs = [f["section"] for f in result_form(b)["blocks"][0]["fields"]]
    assert secs == ["Трастеры (10 раундов)", "Берпи (10 раундов)"]    # строка = своя минута: 10 + 10
    one = wp.parse_program("EMOM x20\nТрастеры + берпи\n", {})
    assert [(x["format"], x["emom_total"]) for x in one] == [("stations", 20)]   # одна строка = одно поле, не 20 подходов
    five = wp.parse_program("EMOM x5\nПрисед 80%\n", {})
    assert [x["format"] for x in five] == ["emom_strength"]                    # короткий силовой EMOM как раньше


def test_typo_wood_and_station_list_without_quantities():
    from tj.analysis import wod_program as wp
    from tj.services.board import result_form
    board = "Wood#1:\n50 БМ\n50 становых\n100 ОП\n\nWod#2:\nБег\nТолкание саней\nБег\nОтжимания\n"
    b = wp.parse_program(board, {})
    assert [x["header"] for x in b] == ["Wood#1", "Wod#2"]
    assert b[1]["format"] == "stations"
    types = [f["type"] for f in result_form(b)["blocks"][1]["fields"]]
    assert types == ["cardio", "weight_distance", "cardio", "reps_load", "time"]
