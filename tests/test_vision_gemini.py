from __future__ import annotations
from tjbot import vision


def test_parse_board_uses_llm(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision",
        lambda *a, **k: '{"raw_text":"Становая 5x5","format":"rounds","movements":["становая"]}')
    out = vision.parse_board(b"\xff\xd8imgbytes")
    assert out and out["format"] == "rounds"
    assert "deadlift" in (out.get("movements_canon") or [])


def test_parse_board_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision", lambda *a, **k: None)
    assert vision.parse_board(b"x") is None


def test_has_vision_follows_llm(monkeypatch):
    monkeypatch.setattr(vision.llm, "has_llm", lambda: True)
    assert vision.has_vision() is True
