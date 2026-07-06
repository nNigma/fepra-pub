from __future__ import annotations
from tjbot import vision


def test_standardize_known_and_unknown():
    canon, unknown = vision.standardize(["становая", "трастер", "зюзюка"])
    assert canon == ["deadlift", "thruster"]
    assert unknown == ["зюзюка"]


def test_standardize_passthrough_canon_id():
    canon, unknown = vision.standardize(["clean_and_jerk", "становая"])
    assert canon == ["clean_and_jerk", "deadlift"]
    assert unknown == []


def test_standardize_dedupes():
    canon, _ = vision.standardize(["становая", "становая тяга"])
    assert canon == ["deadlift"]


def test_standardize_uses_aliases():
    canon, unknown = vision.standardize(["мах гирей"], {"мах гирей": "kb_swing"})
    assert canon == ["kb_swing"] and unknown == []


def test_scan_movements_free_text():
    out = vision.scan_movements("5 раундов: становая тяга 100 кг, берпи через штангу")
    assert "deadlift" in out and "burpee_over_bar" in out


def test_scan_movements_empty():
    assert vision.scan_movements("") == []


def test_parse_text_with_llm(monkeypatch):
    monkeypatch.setattr(vision.llm, "has_llm", lambda: True)
    monkeypatch.setattr(vision.llm, "complete",
        lambda *a, **k: '{"raw_text":"Фран 21-15-9","format":"for-time","movements":["трастер","подтягивания"]}')
    out = vision.parse_text("фран")
    assert out["format"] == "for-time"
    assert "трастер" in out["movements"]


def test_parse_text_fallback_scans(monkeypatch):
    monkeypatch.setattr(vision.llm, "has_llm", lambda: False)
    out = vision.parse_text("становая тяга 5x5")
    assert out["format"] == "other"
    assert out["raw_text"] == "становая тяга 5x5"
    assert "deadlift" in out["movements"]


def test_parse_text_bad_json_falls_back(monkeypatch):
    monkeypatch.setattr(vision.llm, "has_llm", lambda: True)
    monkeypatch.setattr(vision.llm, "complete", lambda *a, **k: "не json")
    out = vision.parse_text("берпи через штангу")
    assert out["raw_text"] == "берпи через штангу"
    assert "burpee_over_bar" in out["movements"]
