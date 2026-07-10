from __future__ import annotations
import sqlite3
from datetime import date
from fastapi.testclient import TestClient
from tjbot import db as botdb
from tjapp import api
from tjapp.api import app, require_auth


def _setup(tmp_path, monkeypatch, pro: bool):
    dbp = tmp_path / "t.db"
    con = botdb.connect(dbp); botdb.init_schema(con)
    con.execute('INSERT OR REPLACE INTO users ("tg_id","sex","weight_kg") VALUES (1,?,?)', ("m", 79)); con.commit(); con.close()
    monkeypatch.setattr(api, "_db", lambda: str(dbp))
    monkeypatch.setattr(api, "is_pro", lambda tg: pro)
    app.dependency_overrides[require_auth] = lambda: {"id": 1}
    return TestClient(app)


def test_post_llm_forbidden_for_non_pro(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=False)
    r = c.post("/api/llm/workout/2026-06-26")
    assert r.status_code == 403
    app.dependency_overrides.clear()


def test_get_llm_available_flag(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=True)
    monkeypatch.setattr(api, "has_llm", lambda: True)
    r = c.get("/api/llm/workout/2026-06-26")
    assert r.status_code == 200 and r.json()["available"] is True
    app.dependency_overrides.clear()


def _stub_llm(monkeypatch):
    monkeypatch.setattr(api, "_llm_payload", lambda con, kind, ref, tg_id: {"k": ref})
    monkeypatch.setattr(api.llm_coach, "coach",
                        lambda kind, p, lang="ru", astro=False: ("разбор", "claude"))
    monkeypatch.setattr(api, "_refresh_other_llm", lambda *a, **k: None)


def test_post_llm_quota_blocks_after_limit(tmp_path, monkeypatch):
    from tjbot.access import LLM_DAILY_LIMIT
    c = _setup(tmp_path, monkeypatch, pro=True)  # id 1 не админ → под лимитом
    _stub_llm(monkeypatch)
    # refresh=1 форсирует реальный вызов мимо кэша → каждое списывает
    for i in range(LLM_DAILY_LIMIT):
        assert c.post(f"/api/llm/workout/d{i}?refresh=1").status_code == 200
    assert c.post("/api/llm/workout/dX?refresh=1").status_code == 429
    app.dependency_overrides.clear()


def test_post_llm_cache_hit_does_not_consume(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=True)
    _stub_llm(monkeypatch)
    r1 = c.post("/api/llm/workout/day1")  # реальный вызов → списание 1, генерация в фоне
    assert r1.status_code == 200 and r1.json().get("pending") is True
    # TestClient гоняет background-таски синхронно → кэш уже наполнен
    for _ in range(5):
        r = c.post("/api/llm/workout/day1")  # кэш-хит → без списания
        j = r.json()
        assert r.status_code == 200 and j["cached"] is True
        assert j["text"] == "разбор" and j["engine"] == "claude"
    con = botdb.connect(tmp_path / "t.db")
    try:
        assert botdb.llm_quota_used(con, 1, date.today().isoformat()) == 1
    finally:
        con.close()
    app.dependency_overrides.clear()


def test_refresh_clears_stale_cache(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=True)
    monkeypatch.setattr(api, "has_llm", lambda: True)
    monkeypatch.setattr(api, "_llm_payload", lambda con, kind, ref, tg_id: {"k": ref})
    monkeypatch.setattr(api, "_refresh_other_llm", lambda *a, **k: None)
    monkeypatch.setattr(api.llm_coach, "coach",
                        lambda kind, p, lang="ru", astro=False: ("старый разбор", "claude"))
    c.post("/api/llm/summary/30d")
    assert c.get("/api/llm/summary/30d").json()["cached"]["text"] == "старый разбор"
    # регенерация падает -> старый кэш не должен остаться (иначе поллинг покажет старое)
    monkeypatch.setattr(api.llm_coach, "coach",
                        lambda kind, p, lang="ru", astro=False: (None, "gemini"))
    c.post("/api/llm/summary/30d?refresh=1")
    assert c.get("/api/llm/summary/30d").json()["cached"] is None
    app.dependency_overrides.clear()
