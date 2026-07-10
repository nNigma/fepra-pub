from __future__ import annotations

import sqlite3

from tjbot import db as botdb


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_data_version_absent_then_set():
    con = _con()
    assert botdb.data_version(con) is None
    botdb.mark_data_changed(con)
    assert botdb.data_version(con)


def test_advice_created_at_full_timestamp():
    con = _con()
    botdb.next_advice_put(con, 1, "claude", "совет")
    created = botdb.next_advice_get(con, 1)["created_at"]
    assert "T" in created  # полный ISO-таймстамп, не только дата


def test_stale_when_data_newer_than_advice():
    con = _con()
    botdb.next_advice_put(con, 1, "claude", "совет",
                          created_at="2026-07-04T10:00:00+00:00")
    con.execute('INSERT OR REPLACE INTO meta ("key","value") VALUES (?,?)',
                ("data_version", "2026-07-04T12:00:00+00:00"))
    con.commit()
    created = botdb.next_advice_get(con, 1)["created_at"]
    dv = botdb.data_version(con)
    assert dv > created  # данные новее → совет устарел

    con.execute('INSERT OR REPLACE INTO meta ("key","value") VALUES (?,?)',
                ("data_version", "2026-07-04T09:00:00+00:00"))
    con.commit()
    assert botdb.data_version(con) < created  # данные старше → не устарел
