from __future__ import annotations

import sqlite3

from tj.ontology import resolve, find, is_weighted
from tjbot import db as botdb


def test_pushpress_and_hang_clean():
    assert resolve("швунг") == "push_press"
    assert resolve("швунгов") == "push_press"
    assert is_weighted("push_press")
    assert (resolve("взятие с виса") or (find("взятие с виса") or [None])[-1]) == "hang_clean"
    assert (resolve("взятий с виса на грудь")
            or (find("взятий с виса на грудь") or [None])[-1]) == "hang_clean"


def test_next_advice_stores_date():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    botdb.next_advice_put(con, 1, "claude", "совет")
    row = botdb.next_advice_get(con, 1)
    assert row["text"] == "совет"
    assert row["created_at"] and row["created_at"][:4].isdigit()
