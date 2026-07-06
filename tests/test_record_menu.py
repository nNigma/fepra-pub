from __future__ import annotations

def test_record_kb_layout():
    from tjbot.handlers.menu import record_kb, BTN_ADD_RESULT, BTN_ADD_WORKOUT, BTN_EDIT, BTN_BACK
    texts = [b.text for row in record_kb("ru").keyboard for b in row]
    for t in (BTN_ADD_RESULT, BTN_ADD_WORKOUT, BTN_EDIT, BTN_BACK):
        assert t in texts, t
