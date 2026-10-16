from __future__ import annotations


def test_record_kb_layout():
    from tjbot.handlers.menu import (record_kb, BTN_ADD_RESULT, BTN_ADD_WORKOUT,
                                     BTN_EDIT, BTN_BACK, BTN_ENTER_PM)
    texts = [b.text for row in record_kb("ru").keyboard for b in row]
    for t in (BTN_ENTER_PM, BTN_ADD_RESULT, BTN_ADD_WORKOUT, BTN_EDIT, BTN_BACK):
        assert t in texts, t


def test_enter_pm_is_menu_key():
    from tjbot.handlers import menu
    assert "btn.enter_pm" in menu._MENU_KEYS
    assert "btn.result" not in menu._MENU_KEYS
