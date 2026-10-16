"""ИИ-тренер: сервис лимитов и роуты /api/coach/* (LLM мокается)."""
import pytest

from p5a_env import p5a, wait_job  # noqa: F401
from tj.analysis import coach as engine
from tj.services import coach as svc
from tjbot import access, db as botdb
from tjbot.handlers import coach as bot_coach


@pytest.fixture
def fake(monkeypatch):
    calls = []

    def ask(db_path, uid, q, lang="ru"):
        calls.append((uid, q, lang))
        return ("ответ: " + q, "claude") if q != "fail" else (None, None)
    monkeypatch.setattr(engine, "ask", ask)
    return calls


def test_limit_constant_matches_bot():
    assert svc.COACH_DAILY_LIMIT == bot_coach.COACH_DAILY_LIMIT


def test_pro_only(p5a, fake):
    p5a.user(1)                       # обычный
    p5a.user(2, pro=True)
    assert p5a.client(1).post("/api/coach/ask", json={"q": "как?"}).status_code == 403
    assert p5a.client(1).get("/api/coach/recent").status_code == 403
    assert p5a.client(2).post("/api/coach/ask", json={"q": "как?"}).status_code == 200


def test_ask_job_stores_answer(p5a, fake):
    p5a.user(2, pro=True)
    c = p5a.client(2)
    jid = c.post("/api/coach/ask", json={"q": "  что делать?  "}).json()["job_id"]
    j = wait_job(c, jid)
    assert j["status"] == "done" and j["result"]["answer"] == "ответ: что делать?"
    assert j["result"]["engine"] == "claude" and fake == [(2, "что делать?", "ru")]
    rec = c.get("/api/coach/recent").json()
    assert len(rec) == 1 and rec[0]["question"] == "что делать?" and rec[0]["answer"].startswith("ответ")


def test_recent_only_own(p5a, fake):
    p5a.user(2, pro=True)
    p5a.user(3, pro=True)
    c2, c3 = p5a.client(2), p5a.client(3)
    wait_job(c2, c2.post("/api/coach/ask", json={"q": "мой"}).json()["job_id"])
    assert c3.get("/api/coach/recent").json() == []


def test_llm_failure_is_job_error(p5a, fake):
    p5a.user(2, pro=True)
    c = p5a.client(2)
    j = wait_job(c, c.post("/api/coach/ask", json={"q": "fail"}).json()["job_id"])
    assert j["status"] == "error" and "тренер" in j["error"]
    assert c.get("/api/coach/recent").json() == []


def test_daily_limit_for_non_admin(p5a, fake):
    p5a.user(2, pro=True)
    c = p5a.client(2)
    for i in range(svc.COACH_DAILY_LIMIT):
        wait_job(c, c.post("/api/coach/ask", json={"q": f"q{i}"}).json()["job_id"])
    r = c.post("/api/coach/ask", json={"q": "ещё"})
    assert r.status_code == 429 and isinstance(r.json()["detail"], str)


def test_admin_has_no_limits(p5a, fake):
    p5a.user(1, admin=True)
    c = p5a.client(1)
    for i in range(svc.COACH_DAILY_LIMIT + 2):
        assert wait_job(c, c.post("/api/coach/ask", json={"q": f"q{i}"}).json()["job_id"])["status"] == "done"


def test_llm_quota_consumed(p5a, fake, monkeypatch):
    p5a.user(2, pro=True)
    monkeypatch.setattr(access, "LLM_DAILY_LIMIT", 7)
    c = p5a.client(2)
    wait_job(c, c.post("/api/coach/ask", json={"q": "q"}).json()["job_id"])
    assert access.llm_quota_remaining(2, p5a.con) == 6


def test_llm_quota_exhausted(p5a, fake):
    p5a.user(2, pro=True)
    from datetime import date
    botdb.llm_quota_bump(p5a.con, 2, date.today().isoformat(), access.LLM_DAILY_LIMIT)
    r = p5a.client(2).post("/api/coach/ask", json={"q": "q"})
    assert r.status_code == 429 and fake == []


def test_validation(p5a, fake):
    p5a.user(2, pro=True)
    c = p5a.client(2)
    assert c.post("/api/coach/ask", json={"q": ""}).status_code == 422
    assert c.post("/api/coach/ask", json={"q": "   "}).status_code == 422
    assert c.post("/api/coach/ask", json={"q": "x" * 2001}).status_code == 422
    assert c.post("/api/coach/ask", json={}).status_code == 422


def test_recent_limit_param(p5a, fake):
    p5a.user(1, admin=True)
    c = p5a.client(1)
    for i in range(3):
        wait_job(c, c.post("/api/coach/ask", json={"q": f"q{i}"}).json()["job_id"])
    assert len(c.get("/api/coach/recent?limit=2").json()) == 2
    assert c.get("/api/coach/recent?limit=0").status_code == 422
