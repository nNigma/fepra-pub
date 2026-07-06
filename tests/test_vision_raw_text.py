"""Gemini иногда отдаёт raw_text/prescription массивом строк — не должны падать."""
from __future__ import annotations

import json

from tjbot import vision


def test_as_text_coerces_list():
    assert vision._as_text(["a", "b"]) == "a\nb"
    assert vision._as_text("x") == "x"
    assert vision._as_text(None) == ""


def test_parse_board_raw_text_list_to_str(monkeypatch):
    payload = {"raw_text": ["WOD 1", "21-15-9", "трастеры"], "format": "for-time",
               "movements": ["трастеры"]}
    monkeypatch.setattr(vision.llm, "vision", lambda *a, **k: json.dumps(payload))
    draft = vision.parse_board(b"jpegbytes")
    assert isinstance(draft["raw_text"], str)
    assert draft["raw_text"][:900] == "WOD 1\n21-15-9\nтрастеры"


def test_parse_text_raw_text_list_to_str(monkeypatch):
    payload = {"raw_text": ["строка 1", "строка 2"], "format": "amrap", "movements": []}
    monkeypatch.setattr(vision.llm, "has_llm", lambda: True)
    monkeypatch.setattr(vision.llm, "complete", lambda *a, **k: json.dumps(payload))
    draft = vision.parse_text("что-то")
    assert isinstance(draft["raw_text"], str)
    assert draft["raw_text"] == "строка 1\nстрока 2"


def test_parse_stages_prescription_list_to_str(monkeypatch):
    payload = [{"name": ["Этап", "1"], "prescription": ["10 берпи", "20 приседов"],
                "format": "for-time", "movements": []}]
    monkeypatch.setattr(vision.llm, "vision", lambda *a, **k: json.dumps(payload))
    stages = vision.parse_stages(b"jpegbytes")
    assert isinstance(stages[0]["prescription"], str)
    assert isinstance(stages[0]["name"], str)
