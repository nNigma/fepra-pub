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


def test_parse_results_rows_not_list(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision",
        lambda *a, **k: '{"athlete":"Алексей","rows":"13:54"}')
    out = vision.parse_results(b"x", "Алексей")
    assert out is None or out.get("rows") == []


def test_parse_results_rows_of_scalars(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision",
        lambda *a, **k: '{"athlete":"Алексей","rows":[1,2,3]}')
    out = vision.parse_results(b"x", "Алексей")
    assert (out or {}).get("rows") == []


def test_parse_results_row_field_types(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision",
        lambda *a, **k: '{"athlete":"Алексей","rows":[{"stage":2.0,"value":42,"place":"3"}]}')
    out = vision.parse_results(b"x", "Алексей")
    r = out["rows"][0]
    assert r["stage"] == 2 and r["value"] == "42" and r["place"] == 3


def test_parse_results_nonfinite_place_no_crash(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision",
        lambda *a, **k: '{"athlete":"Н","rows":[{"stage":NaN,"value":"x","place":Infinity}]}')
    out = vision.parse_results(b"x", "Н")
    r = out["rows"][0]
    assert r["stage"] is None and r["place"] is None


def test_parse_stages_movements_not_list(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision",
        lambda *a, **k: '[{"name":"Э1","prescription":"текст","format":"amrap","movements":"становая, присед"}]')
    out = vision.parse_stages(b"x")
    assert out and out[0]["movements"] == [] and out[0]["movements_canon"] == []


def test_parse_stages_skips_non_dict(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision",
        lambda *a, **k: '["Э1", {"name":"Э2","prescription":"21-15-9 становая","format":"for-time","movements":["становая"]}]')
    out = vision.parse_stages(b"x")
    assert len(out) == 1 and "deadlift" in out[0]["movements_canon"]
