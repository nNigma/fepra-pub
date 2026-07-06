from __future__ import annotations

from datetime import date

from tjbot import access
from tjbot import db as botdb


def _con(tmp_path):
    con = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(con)
    return con


def test_quota_counter_roundtrip(tmp_path):
    con = _con(tmp_path)
    assert botdb.llm_quota_used(con, 5, "2026-07-01") == 0
    assert botdb.llm_quota_bump(con, 5, "2026-07-01") == 1
    assert botdb.llm_quota_bump(con, 5, "2026-07-01") == 2
    assert botdb.llm_quota_used(con, 5, "2026-07-01") == 2
    assert botdb.llm_quota_used(con, 5, "2026-07-02") == 0
    assert botdb.llm_quota_used(con, 6, "2026-07-01") == 0


def test_consume_limits_non_admin(tmp_path):
    con = _con(tmp_path)
    limit = access.LLM_DAILY_LIMIT
    assert access.llm_quota_remaining(1, con) == limit
    for i in range(limit):
        assert access.llm_quota_consume(1, con) is True
        assert access.llm_quota_remaining(1, con) == limit - i - 1
    assert access.llm_quota_remaining(1, con) == 0
    assert access.llm_quota_consume(1, con) is False
    assert botdb.llm_quota_used(con, 1, date.today().isoformat()) == limit


def test_admin_is_unlimited_and_uncounted(tmp_path, monkeypatch):
    con = _con(tmp_path)
    monkeypatch.setattr(access, "is_admin", lambda tg, path=None: True)
    assert access.llm_quota_remaining(9, con) is None
    for _ in range(10):
        assert access.llm_quota_consume(9, con) is True
    assert botdb.llm_quota_used(con, 9, date.today().isoformat()) == 0
