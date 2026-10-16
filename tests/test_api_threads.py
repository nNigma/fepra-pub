"""Регресс: синхронные зависимости роутов выполняются в другом потоке, чем хендлер
(SQLite ProgrammingError: objects created in a thread…). Параллельные запросы к
API не должны давать 500."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from tjapp import api
from tjapp.deps import require_user
from tjbot import db as botdb


def test_parallel_requests_no_thread_errors(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    con = botdb.connect(p)
    botdb.init_schema(con)
    con.close()
    api.app.dependency_overrides[require_user] = lambda: {"id": 1}
    try:
        with TestClient(api.app) as c:
            def hit(_):
                return c.get("/api/programs/tree").status_code
            with ThreadPoolExecutor(8) as ex:
                codes = list(ex.map(hit, range(80)))
        assert set(codes) == {200}, set(codes)
    finally:
        api.app.dependency_overrides.pop(require_user, None)
