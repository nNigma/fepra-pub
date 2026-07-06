from __future__ import annotations

import sqlite3

from tjbot import db as botdb
from tj.analysis.llm_coach import parse_workout_blocks, strip_workout_blocks


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


_TEXT = (
    "Глубокий разбор в три раздела...\n\n"
    "РАЗБОР:\n"
    "Что развивает: анаэробная мощность, силовой день.\n"
    "Зоны: 25 мин в Z4-Z5, средний занижен паузами.\n"
    "Интенсивные минуты: 57 умеренной + 19 интенсивной.\n"
    "Риск: макс 174, но флаг - сон 6.9ч под штангу.\n"
    "Совет: ACWR 0.98, пробуй 82.5 в сингле.\n"
)


def test_parse_five_blocks():
    b = parse_workout_blocks(_TEXT)
    assert len(b) == 5
    assert b[0] == {"kind": "verdict", "title": "Что развивает",
                    "body": "анаэробная мощность, силовой день."}
    assert b[3]["kind"] == "risk"
    assert b[4]["kind"] == "advice"


def test_strip_removes_recap():
    disp = strip_workout_blocks(_TEXT)
    assert "РАЗБОР" not in disp
    assert "Что развивает:" not in disp
    assert "Глубокий разбор" in disp


def test_parse_tolerates_bold_and_bullets():
    b = parse_workout_blocks("- **Риск:** высокий\n* Совет: отдохни")
    kinds = {x["kind"] for x in b}
    assert "risk" in kinds and "advice" in kinds


def test_wk_narrative_claude_beats_gemini():
    con = _con()
    gem = [{"kind": "verdict", "title": "Что развивает", "body": "гем"}]
    cld = [{"kind": "verdict", "title": "Что развивает", "body": "клод"}]
    botdb.wk_narrative_put(con, 1, "2026-06-29", "gemini", gem)
    assert botdb.wk_narrative_get(con, 1, "2026-06-29")["source"] == "gemini"
    botdb.wk_narrative_put(con, 1, "2026-06-29", "claude", cld)
    got = botdb.wk_narrative_get(con, 1, "2026-06-29")
    assert got["source"] == "claude" and got["blocks"][0]["body"] == "клод"


def test_wk_narrative_absent():
    con = _con()
    assert botdb.wk_narrative_get(con, 1, "2026-06-29") is None
