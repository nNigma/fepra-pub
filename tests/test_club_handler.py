from __future__ import annotations
import sqlite3
from tj import i18n
from tjbot import db as botdb
from tjbot.handlers import club


def _texts(kb):
    return [b.text for row in kb.keyboard for b in row]


def _cbs(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row]


def test_confirm_kb_add_move_when_nothing_recognized():
    kb = club._confirm_kb({"canon": [], "unknown": []}, "ru")
    assert "cmv" in _cbs(kb)


def test_confirm_kb_add_move_when_unknown_present():
    kb = club._confirm_kb({"canon": ["back_squat"], "unknown": ["бчб"]}, "ru")
    assert "cmv" in _cbs(kb)


def test_confirm_kb_no_add_move_when_all_recognized():
    kb = club._confirm_kb({"canon": ["back_squat"], "unknown": []}, "ru")
    assert "cmv" not in _cbs(kb)


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_club_kb_admin_vs_regular():
    a = _texts(club.club_kb(True))
    r = _texts(club.club_kb(False))
    assert club.BTN_CLUB_ADD in a and club.BTN_CLUB_ADD not in r
    assert club.BTN_CLUB_EDIT in a and club.BTN_CLUB_EDIT not in r
    assert club.BTN_CLUB_DATE in r and club.BTN_CLUB_STATS in r
    assert i18n.t("btn.back", "ru") in r


def test_is_menu_text_blocks_buttons():
    assert club._is_menu_text("Программа зала")
    assert club._is_menu_text("📊 Стата зала")
    assert club._is_menu_text("← Назад")
    assert not club._is_menu_text("Становая 5х5, трастеры 30")


def test_parse_alias_lines():
    out = club._parse_alias_lines("Мах гирей = kb_swing\nкривая строка\nВыпады боком= walking_lunge")
    assert out == [("мах гирей", "kb_swing"), ("выпады боком", "walking_lunge")]


def test_fmt_program_and_empty():
    assert club._fmt_program(None) == ""
    row = {"day": "2026-06-10", "raw_text": "Фран 21-15-9", "gym": "Universe"}
    s = club._fmt_program(row)
    assert "2026-06-10" in s and "Фран" in s and "Universe" in s


def test_fmt_stats():
    assert "нет" in club._fmt_stats([]).lower()
    s = club._fmt_stats([("deadlift", 3, "Становая"), ("thruster", 1, "Трастер")])
    assert "Становая ×3" in s and "Трастер ×1" in s


def test_register_callable():
    assert callable(club.register)
    assert club.BTN_CLUB == "Программа зала"


def test_register_builds_handlers():
    captured = []

    class App:
        def add_handler(self, h):
            captured.append(h)

    club.register(App())
    assert len(captured) == 5


def test_restandardize_resolves_after_alias():
    con = _con()
    draft = {"raw_text": "3 WOD\n3 сета:\n- 15 становая тяга\n- 10 зашагивания на тумбу\n"}
    club._restandardize(con, draft)
    assert "deadlift" in draft["canon"]
    assert "зашагивания на тумбу" in draft["unknown"]
    botdb.add_alias(con, "зашагивания на тумбу", "kb_swing")
    club._restandardize(con, draft)
    assert "kb_swing" in draft["canon"] and draft["unknown"] == []


def test_edit_entry_shares_add_conversation():
    conv = club._add_conv()
    entry_texts = []
    for h in conv.entry_points:
        entry_texts.extend(h.filters.strings)
    assert club.BTN_CLUB_ADD in entry_texts
    assert club.BTN_CLUB_EDIT in entry_texts
    handlers_for_edit = [h for h in conv.entry_points if club.BTN_CLUB_EDIT in h.filters.strings]
    assert len(handlers_for_edit) == 1
    assert handlers_for_edit[0].callback is club.edit_entry


def test_slug_lowercases_and_normalizes():
    assert club._slug("Гуд Морнинг") == "гуд_морнинг"
    assert club._slug("Оверхед-присед!") == "оверхед_присед"
    assert club._slug("  ") == ""


def test_register_canon_resolves_and_shows_in_dict():
    con = _con()
    club._register_canon(con, "гуд_морнинг")
    botdb.add_alias(con, "гудморнингов со штангой", "гуд_морнинг")
    from tj import ontology
    aliases = botdb.load_aliases(con)
    assert ontology.resolve("гудморнингов со штангой", aliases) == "гуд_морнинг"
    text = club._dictionary_text(con)
    assert "гуд_морнинг: гудморнингов со штангой" in text
    assert "back_squat:" in text  # статические каноны тоже в словаре


def test_add_move_state_registered():
    conv = club._add_conv()
    assert club.ADD_MOVE in conv.states
    patterns = [h.pattern.pattern for h in conv.states[club.ADD_MOVE]
                if hasattr(h, "pattern") and h.pattern]
    assert any("mv:dict" in p for p in patterns)
    assert any("mv:new" in p for p in patterns)
    assert any("mv:skip" in p for p in patterns)
    cmv = [h for h in conv.states[club.ADD_CONFIRM]
           if hasattr(h, "pattern") and h.pattern and "cmv" in h.pattern.pattern]
    assert cmv and cmv[0].callback is club.mv_start


def test_add_input_uses_block_parser():
    from tj.analysis.wod_program import movements_of, parse_program
    board = ("2 ТА.\n- Е2МОМх5х5х80%\nприседание со штангой на спине\n"
             "4 AMRAP 3 мин х 5\n- 16 рывков\n- 8 подтягивания\n")
    blocks = parse_program(board)
    canon, unknown = movements_of(blocks)
    assert "back_squat" in canon and "snatch" in canon and "pull_up" in canon
    fmt = "+".join(dict.fromkeys(b["format"] for b in blocks))
    assert "emom_strength" in fmt and "amrap_interval" in fmt
