from __future__ import annotations
from tjbot import vision


def test_parse_stages(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision",
        lambda *a, **k: '[{"name":"Э1","prescription":"21-15-9 становая","format":"for-time","movements":["становая"]}]')
    out = vision.parse_stages(b"x")
    assert out and out[0]["format"] == "for-time"
    assert "deadlift" in out[0]["movements_canon"]


def test_parse_results(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision",
        lambda *a, **k: '{"athlete":"Иван","rows":[{"stage":1,"value":"13:54","place":9}]}')
    out = vision.parse_results(b"x", "Иван")
    assert out["athlete"] == "Иван" and out["rows"][0]["place"] == 9


def test_parse_stages_none_without_key(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision", lambda *a, **k: None)
    assert vision.parse_stages(b"x") is None
    assert vision.parse_results(b"x", "кто-то") is None
