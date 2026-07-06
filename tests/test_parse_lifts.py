from __future__ import annotations
from tjbot import vision


def test_parse_lifts_llm(monkeypatch):
    monkeypatch.setattr(vision.llm, "has_llm", lambda: True)
    monkeypatch.setattr(vision.llm, "complete",
        lambda *a, **k: '[{"movement":"становая","weight_kg":130,"reps":1}]')
    out = vision.parse_lifts("становая 100/110/130")
    assert out == [{"movement": "становая", "weight_kg": 130, "reps": 1}]


def test_parse_lifts_no_key(monkeypatch):
    monkeypatch.setattr(vision.llm, "has_llm", lambda: False)
    assert vision.parse_lifts("становая 130") is None


def test_parse_lifts_bad_json(monkeypatch):
    monkeypatch.setattr(vision.llm, "has_llm", lambda: True)
    monkeypatch.setattr(vision.llm, "complete", lambda *a, **k: "не json")
    assert vision.parse_lifts("становая 130") is None
