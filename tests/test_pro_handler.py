from __future__ import annotations
from tjbot.handlers.pro import handler, BTN_PRO


def test_pro_handler_builds():
    assert handler() is not None and BTN_PRO == "Pro"
