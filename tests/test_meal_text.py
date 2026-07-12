from __future__ import annotations

import json

from tjbot import vision

PAYLOAD = json.dumps({
    "foods": [{"name": "овощной суп", "grams": 300, "kcal": 150,
               "protein_g": 5, "fat_g": 5, "carb_g": 20}],
    "confidence": "medium", "question": None,
    "quality": 2, "quality_note": "лёгкий суп"}, ensure_ascii=False)


def test_parse_meal_text_gemini(monkeypatch):
    seen = {}

    def fake_complete(system, user, **kw):
        seen["user"] = user
        return PAYLOAD

    monkeypatch.setattr(vision.llm, "complete", fake_complete)
    out = vision.parse_meal_text("стандартный овощной суп")
    assert out["totals"]["kcal"] == 150
    assert out["foods"][0]["name"] == "овощной суп"
    assert out["quality"] == 2
    assert "стандартный овощной суп" in seen["user"]
    assert "ОПИСАНИЕ ЕДЫ" in seen["user"]


def test_parse_meal_text_correction(monkeypatch):
    seen = {}

    def fake_complete(system, user, **kw):
        seen["user"] = user
        return PAYLOAD

    monkeypatch.setattr(vision.llm, "complete", fake_complete)
    vision.parse_meal_text("суп", correction="без масла; с хлебом")
    assert "Уточнение пользователя (учти как факт): без масла; с хлебом" in seen["user"]


def test_parse_meal_text_claude_first(monkeypatch):
    seen = {}

    def fake_claude(prompt, **kw):
        seen["model"] = kw.get("model")
        return PAYLOAD

    def fail_gemini(*a, **k):
        raise AssertionError("gemini не должен вызываться")

    monkeypatch.setattr(vision.llm, "claude_complete", fake_claude)
    monkeypatch.setattr(vision.llm, "complete", fail_gemini)
    out = vision.parse_meal_text("суп", engine="claude")
    assert out["totals"]["kcal"] == 150
    assert seen["model"] == "opus"


def test_parse_meal_text_claude_fallback(monkeypatch):
    monkeypatch.setattr(vision.llm, "claude_complete", lambda *a, **k: None)
    monkeypatch.setattr(vision.llm, "complete", lambda *a, **k: PAYLOAD)
    out = vision.parse_meal_text("суп", engine="claude")
    assert out["totals"]["kcal"] == 150


def test_parse_meal_text_garbage(monkeypatch):
    monkeypatch.setattr(vision.llm, "complete", lambda *a, **k: "не понял вопроса")
    assert vision.parse_meal_text("суп") is None


def test_parse_meal_text_llm_dead(monkeypatch):
    monkeypatch.setattr(vision.llm, "complete", lambda *a, **k: None)
    assert vision.parse_meal_text("суп") is None
