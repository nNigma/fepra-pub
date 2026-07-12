from tjbot.handlers import record_workout as rw
from tjbot.handlers import club


def test_no_engine_choice_when_claude_off(monkeypatch):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "0")
    assert rw._offer_engine_choice() is False
    assert club._offer_engine_choice() is False


def test_engine_choice_when_claude_on(monkeypatch):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    from tjbot import vision
    monkeypatch.setattr(vision, "has_claude", lambda: True)
    assert rw._offer_engine_choice() is True
    assert club._offer_engine_choice() is True
