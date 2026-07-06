from __future__ import annotations
from tjbot.handlers.goal import handler, BTN_GOAL


def test_goal_handler_builds():
    h = handler()
    assert h is not None and BTN_GOAL == "🎯 Цель"
