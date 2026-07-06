from __future__ import annotations
import sqlite3
from tjbot import db as botdb
from tj.ontology import resolve


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_alias_roundtrip():
    con = _con()
    assert botdb.load_aliases(con) == {}
    botdb.add_alias(con, "Присед на ящик", "back_squat")
    assert botdb.load_aliases(con) == {"присед на ящик": "back_squat"}


def test_alias_upsert_no_dupes():
    con = _con()
    botdb.add_alias(con, "мах гирей", "kb_swing")
    botdb.add_alias(con, "мах гирей", "kb_swing_v2")
    assert botdb.load_aliases(con) == {"мах гирей": "kb_swing_v2"}


def test_alias_then_resolve():
    con = _con()
    botdb.add_alias(con, "бёрпи боком", "burpee")
    assert resolve("бёрпи боком", botdb.load_aliases(con)) == "burpee"


def test_last_program():
    con = _con()
    botdb.add_program(con, "2026-06-01", "Universe", "a", confirmed=1)
    botdb.add_program(con, "2026-06-05", "Universe", "b", confirmed=1)
    botdb.add_program(con, "2026-06-09", "Universe", "c", confirmed=0)
    assert botdb.last_program(con)["day"] == "2026-06-05"


def test_last_program_none():
    assert botdb.last_program(_con()) is None
