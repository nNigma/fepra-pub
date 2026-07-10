from __future__ import annotations

import sqlite3

from tjbot import db as botdb, vision
from tj.analysis.wod_program import movements_of, parse_program


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_normalize_validates_ids(monkeypatch):
    monkeypatch.setattr(vision.llm, "complete",
                        lambda *a, **k: '{"жимов лёжа штанги": "bench_press", "фигня": "не_канон"}')
    out = vision.normalize_movements(["жимов лёжа штанги", "фигня"])
    assert out == {"жимов лёжа штанги": "bench_press"}


def test_normalize_empty_without_llm(monkeypatch):
    called = {"n": 0}
    def _c(*a, **k):
        called["n"] += 1
        return "{}"
    monkeypatch.setattr(vision.llm, "complete", _c)
    assert vision.normalize_movements([], use_llm=True) == {}
    assert vision.normalize_movements(["x"], use_llm=False) == {}
    assert called["n"] == 0


def test_normalize_fallback_on_llm_none(monkeypatch):
    monkeypatch.setattr(vision.llm, "complete", lambda *a, **k: None)
    assert vision.normalize_movements(["швунгов"]) == {}


def test_alias_key_strips_weight():
    assert vision._alias_key("жимов лёжа штанги, 60-50 кг") == "жимов лёжа штанги"
    assert vision._alias_key("швунгов, 60 кг") == "швунгов"


def test_add_alias_lowercases_alias_and_canon():
    con = _con()
    botdb.add_alias(con, "Гуд Морнинг", "Good_Morning", source="manual")
    got = botdb.load_aliases(con)
    assert got.get("гуд морнинг") == "good_morning"


def test_enrich_aliases_learns_and_resolves(monkeypatch):
    con = _con()
    board = "4. Комплекс\n5 сетов:\n- 10 жимов гантелей сидя, 20 кг"
    # до обучения — движение не в каноне
    _, unknown = movements_of(parse_program(board, botdb.load_aliases(con)))
    assert any("гантел" in u for u in unknown)

    # enrich чистит вес перед отправкой, поэтому ключ — уже без «, 20 кг»
    monkeypatch.setattr(vision.llm, "complete",
                        lambda *a, **k: '{"жимов гантелей сидя": "shoulder_press"}')
    aliases = vision.enrich_aliases(con, board)
    canon, _ = movements_of(parse_program(board, aliases))
    assert "shoulder_press" in canon
    # алиас сохранён — второй прогон без LLM тоже резолвит
    canon2, _ = movements_of(parse_program(board, botdb.load_aliases(con)))
    assert "shoulder_press" in canon2
