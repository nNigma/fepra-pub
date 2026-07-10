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
    monkeypatch.setattr(api, "_sweep_unreviewed", lambda *a, **k: None)


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
    monkeypatch.setattr(api, "_sweep_unreviewed", lambda *a, **k: None)
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


def test_get_llm_persists_and_flags_stale(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=True)
    monkeypatch.setattr(api, "has_llm", lambda: True)
    seq = {"n": 0}
    def _payload(con, kind, ref, tg_id):
        seq["n"] += 1
        return {"k": ref, "v": seq["n"]}
    monkeypatch.setattr(api, "_llm_payload", _payload)
    import tjbot.db as botdb
    from tjapp.api import llm_coach
    con = botdb.connect(str(tmp_path / "t.db"))
    h0 = llm_coach.payload_hash({"k": "d1", "v": 0}, "ru", False)
    botdb.llm_cache_put(con, 1, "workout", "d1", h0, "разбор", "claude"); con.close()
    j = c.get("/api/llm/workout/d1").json()
    assert j["cached"] == {"text": "разбор", "engine": "claude"}
    assert j["stale"] is True
    app.dependency_overrides.clear()


def test_get_llm_not_stale_when_hash_matches(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=True)
    monkeypatch.setattr(api, "has_llm", lambda: True)
    monkeypatch.setattr(api, "_llm_payload", lambda con, kind, ref, tg_id: {"k": ref})
    import tjbot.db as botdb
    from tjapp.api import llm_coach
    con = botdb.connect(str(tmp_path / "t.db"))
    h = llm_coach.payload_hash({"k": "d1"}, "ru", False)
    botdb.llm_cache_put(con, 1, "workout", "d1", h, "разбор", "gemini"); con.close()
    j = c.get("/api/llm/workout/d1").json()
    assert j["cached"]["text"] == "разбор" and j["stale"] is False
    app.dependency_overrides.clear()


def test_post_reviewed_no_consume_even_if_stale(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch, pro=True)
    _stub_llm(monkeypatch)
    seq = {"n": 0}
    def _payload(con, kind, ref, tg_id):
        seq["n"] += 1
        return {"k": ref, "v": seq["n"]}
    monkeypatch.setattr(api, "_llm_payload", _payload)
    import tjbot.db as botdb
    con = botdb.connect(str(tmp_path / "t.db"))
    botdb.llm_cache_put(con, 1, "workout", "day1", "hSTALE", "готовый разбор", "claude"); con.close()
    consumed = {"n": 0}
    real = api.llm_quota_consume
    monkeypatch.setattr(api, "llm_quota_consume", lambda tg, con: (consumed.__setitem__("n", consumed["n"]+1) or real(tg, con)))
    r = c.post("/api/llm/workout/day1")
    assert r.status_code == 200 and r.json().get("cached") is True
    assert r.json().get("text") == "готовый разбор"
    assert consumed["n"] == 0
    app.dependency_overrides.clear()


def test_sweep_reviews_unreviewed_last7_skips_reviewed(tmp_path, monkeypatch):
    from datetime import date, timedelta
    c = _setup(tmp_path, monkeypatch, pro=True)
    import tjbot.db as botdb
    dbp = str(tmp_path / "t.db")
    monkeypatch.setattr(api, "_llm_payload", lambda con, kind, ref, tg_id: {"k": kind, "r": ref})
    monkeypatch.setattr(api.llm_coach, "coach", lambda kind, p, lang="ru", astro=False: ("разбор-"+kind, "gemini"))
    monkeypatch.setattr(api, "_finalize_llm", lambda con, tg, k, r, text, eng, lang: text)
    monkeypatch.setattr(api, "llm_quota_consume", lambda tg, con: (_ for _ in ()).throw(AssertionError("свип не тратит квоту")))
    today = date.today()
    d_in = today.isoformat()
    d_old = (today - timedelta(days=30)).isoformat()
    con = botdb.connect(dbp)
    con.execute('INSERT INTO activities ("note","day","sport","activity_id","source","tg_id") VALUES (?,?,?,?,?,?)', (None, d_in, "crossfit", "a-in", "manual", 1))
    con.execute('INSERT INTO activities ("note","day","sport","activity_id","source","tg_id") VALUES (?,?,?,?,?,?)', (None, d_old, "crossfit", "a-old", "manual", 1))
    con.execute('INSERT INTO meals ("tg_id","day","ts","foods","kcal","protein_g","fat_g","carb_g","quality") VALUES (?,?,?,?,?,?,?,?,?)', (1, d_in, "t", "[]", 500, 30, 10, 40, 3))
    botdb.llm_cache_put(con, 1, "workout", d_in, "hx", "СТАРЫЙ workout-разбор", "claude")
    con.commit(); con.close()
    monkeypatch.setattr(api, "_db", lambda: dbp)
    api._sweep_unreviewed(1, "ru", skip_kind="summary", skip_ref="30d")
    con = botdb.connect(dbp)
    def has(k, r): return botdb.llm_cache_get_latest(con, 1, k, r, "ru") is not None
    def txt(k, r): return botdb.llm_cache_get_latest(con, 1, k, r, "ru")["text"]
    assert has("competitions", "total")
    assert has("nutr_day", d_in)
    assert has("nutr_week", d_in)
    assert txt("workout", d_in) == "СТАРЫЙ workout-разбор"
    assert not has("workout", d_old)
    assert not has("summary", "30d")
    con.close()
    app.dependency_overrides.clear()
