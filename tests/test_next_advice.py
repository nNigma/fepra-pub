from __future__ import annotations

import sqlite3

from tjbot import db as botdb
from tj.analysis.llm_coach import parse_advice_line


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_put_get_rules_absent():
    con = _con()
    assert botdb.next_advice_get(con, 1) is None


def test_claude_beats_gemini():
    con = _con()
    botdb.next_advice_put(con, 1, "gemini", "гем-совет")
    assert botdb.next_advice_get(con, 1)["source"] == "gemini"
    botdb.next_advice_put(con, 1, "claude", "клод-совет")
    got = botdb.next_advice_get(con, 1)
    assert got["source"] == "claude" and got["text"] == "клод-совет"


def test_gemini_reput_does_not_touch_claude():
    con = _con()
    botdb.next_advice_put(con, 1, "claude", "клод")
    botdb.next_advice_put(con, 1, "gemini", "новый гем")
    got = botdb.next_advice_get(con, 1)
    assert got["source"] == "claude" and got["text"] == "клод"


def test_put_many_fans():
    con = _con()
    botdb.next_advice_put_many(con, [1, 2], "claude", "всем")
    assert botdb.next_advice_get(con, 1)["text"] == "всем"
    assert botdb.next_advice_get(con, 2)["text"] == "всем"


def test_parse_advice_line():
    assert parse_advice_line("бла бла\nСОВЕТ: добавь веса") == "добавь веса"
    assert parse_advice_line("**СОВЕТ:** отдохни") == "отдохни"
    assert parse_advice_line("нет маркера") is None
