from __future__ import annotations
import sqlite3
from tjbot import db as botdb


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_cache_hit_miss_and_replace():
    con = _con()
    assert botdb.llm_cache_get(con, 1, "workout", "2026-06-26", "h1") is None
    botdb.llm_cache_put(con, 1, "workout", "2026-06-26", "h1", "текст1", "gemini")
    assert botdb.llm_cache_get(con, 1, "workout", "2026-06-26", "h1") == "текст1"
    assert botdb.llm_cache_get(con, 1, "workout", "2026-06-26", "h2") is None
    botdb.llm_cache_put(con, 1, "workout", "2026-06-26", "h2", "текст2", "gemini")
    assert botdb.llm_cache_get(con, 1, "workout", "2026-06-26", "h2") == "текст2"
    n = con.execute("SELECT COUNT(*) FROM llm_cache WHERE tg_id=1 AND kind='workout' AND ref_key='2026-06-26'").fetchone()[0]
    assert n == 1
