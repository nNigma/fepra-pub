from __future__ import annotations
from datetime import date
from zoneinfo import ZoneInfo
from tj.models import Sport
from tjbot.handlers.record_workout import _build_activity


def test_build_activity_persists_board():
    ud = {"date": date(2026, 6, 30), "sport": Sport.CROSSFIT, "result": "130 кг RPE 7",
          "board_text": "Фран", "board_source": "gym"}
    act = _build_activity(ud, ZoneInfo("UTC"), tg_id=1)
    assert act.extra["board_text"] == "Фран"
    assert act.extra["board_source"] == "gym"


def test_build_activity_default_own():
    ud = {"date": date(2026, 6, 30), "sport": Sport.CROSSFIT, "result": "x",
          "board_text": "WOD"}
    act = _build_activity(ud, ZoneInfo("UTC"), tg_id=1)
    assert act.extra["board_source"] == "own"


def test_build_activity_run_no_board():
    ud = {"date": date(2026, 6, 30), "sport": Sport.RUN, "result": "10 км"}
    act = _build_activity(ud, ZoneInfo("UTC"), tg_id=1)
    assert "board_text" not in (act.extra or {})


def test_field_menu_rights():
    from tjbot.handlers import edit_workout as ew
    own = [b.text for row in ew.field_menu("own").inline_keyboard for b in row]
    gym = [b.text for row in ew.field_menu("gym").inline_keyboard for b in row]
    assert "Доска" in own and "Доска" not in gym
    assert "Результат" in own and "Максы" in own and "Готово" in own


def test_label():
    from tjbot.handlers import edit_workout as ew
    s = ew._label({"day": "2026-06-30", "sport": "crossfit", "perf_score": "130 кг"})
    assert "06-30" in s and "crossfit" in s and "130" in s


def test_edit_handler_builds():
    from tjbot.handlers import edit_workout as ew
    assert ew.handler() is not None
    assert ew.BTN_EDIT == "✏️ Редактировать тренировку"


def test_edit_recompute_uses_core():
    from tjbot.handlers.edit_workout import recompute
    board = "2 ТА.\n- Е2МОМх5х5х80%\nприседание со штангой на спине\n"
    result = ("приседание со штангой на спине:\n"
              "  раунд 1 (вес×повторы): 100×3\n  раунд 2 (вес×повторы): 90×5\n")
    mdata, lines, maxes = recompute(board, result, None)
    assert maxes and maxes[0]["movement"] == "приседание со штангой на спине"
    assert maxes[0]["weight_kg"] in (100.0, 90.0)
