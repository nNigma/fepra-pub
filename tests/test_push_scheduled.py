"""Плановые пуши: программа на сегодня, отдых закончен, часовой проход."""
import pytest

from tj.services import notices, push
from tjbot import db as botdb


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("FEPRA_VAPID_PRIVATE", "p")
    monkeypatch.setenv("FEPRA_VAPID_PUBLIC", "q")
    c = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(c)
    yield c
    c.close()


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(push, "_webpush", lambda info, payload, cfg: out.append(payload))
    return out


def _programs(con, status="active"):
    """Схема — настоящая миграция 0030 (её применил init_schema)."""
    con.execute("INSERT INTO program_enrollments (id,uid,program_slug,template_version,start_day,status) "
                "VALUES ('e1',1,'bulgarian-adaptation',1,'2026-09-28',?)", (status,))
    con.execute("INSERT INTO program_sessions (id,enrollment_id,planned_day,week,idx) "
                "VALUES ('s1','e1','2026-09-28',1,1)")
    con.commit()


def test_no_program_tables_is_quiet(con, sent):
    push.subscribe(con, 1, "https://p/1", "k", "a")
    assert push.program_sessions_today(con, 1, "2026-09-28") == 0
    assert push.run_daily(con, "2026-09-28", 9) == {"checked": 1, "sent": []}
    assert sent == []


def test_program_today_once_per_day(con, sent):
    _programs(con)
    push.subscribe(con, 1, "https://p/1", "k", "a")
    r = push.run_daily(con, "2026-09-28", 9)
    assert r["sent"] == [1] and len(sent) == 1
    assert "program_today" in [n["kind"] for n in notices.list_notices(con, 1)]
    assert push.run_daily(con, "2026-09-28", 10)["sent"] == []      # уже слали
    assert len(sent) == 1


def test_not_before_from_hour_and_no_session_other_day(con, sent):
    _programs(con)
    push.subscribe(con, 1, "https://p/1", "k", "a")
    assert push.run_daily(con, "2026-09-28", 5)["checked"] == 0
    assert push.run_daily(con, "2026-09-29", 9)["sent"] == []


def test_done_session_or_inactive_enrollment_skipped(con, sent):
    _programs(con, status="paused")
    assert push.program_sessions_today(con, 1, "2026-09-28") == 0
    con.execute("UPDATE program_enrollments SET status='active'")
    con.execute("UPDATE program_sessions SET activity_id='act'")
    assert push.program_sessions_today(con, 1, "2026-09-28") == 0


def test_only_subscribed_users(con, sent):
    _programs(con)
    assert push.run_daily(con, "2026-09-28", 9)["checked"] == 0


def test_rest_over_push_only(con, sent):
    push.subscribe(con, 1, "https://p/1", "k", "a")
    r = push.notify_rest_over(con, 1, "Приседания")
    assert r["sent"] == 1 and "Приседания" in sent[0]
    assert notices.list_notices(con, 1) == []
