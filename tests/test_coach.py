"""ИИ-тренер: хранение обращений, движок с фолбэком, Pro-гейт."""
from __future__ import annotations

from tj import llm
from tj.analysis import coach as engine
from tjbot import db


def _con(tmp_path):
    con = db.connect(str(tmp_path / "t.db"))
    db.init_schema(con)
    return con


def test_coach_qa_roundtrip(tmp_path):
    con = _con(tmp_path)
    db.add_coach_qa(con, 1, "2026-07-09T10:00:00", "вопрос 1", "ответ 1", "ru", "claude")
    db.add_coach_qa(con, 1, "2026-07-09T11:00:00", "вопрос 2", "ответ 2", "ru", "gemini")
    db.add_coach_qa(con, 2, "2026-07-09T12:00:00", "чужой", "чужой ответ")
    rows = db.coach_recent(con, 1)
    assert [r["question"] for r in rows] == ["вопрос 2", "вопрос 1"]
    assert rows[0]["engine"] == "gemini"
    assert all(r["question"] != "чужой" for r in rows)


def test_coach_recent_limit(tmp_path):
    con = _con(tmp_path)
    for i in range(7):
        db.add_coach_qa(con, 1, f"2026-07-09T0{i}:00:00", f"q{i}", f"a{i}")
    assert len(db.coach_recent(con, 1, limit=5)) == 5


def test_ask_claude_first(monkeypatch):
    monkeypatch.setattr(engine, "coach_payload", lambda *a, **k: {"athlete": {}})
    monkeypatch.setattr(llm, "claude_complete", lambda prompt, **k: "ответ клода")
    answer, used = engine.ask("x.db", 1, "как тренироваться?")
    assert answer == "ответ клода" and used == "claude"


def test_ask_gemini_fallback(monkeypatch):
    monkeypatch.setattr(engine, "coach_payload", lambda *a, **k: {"athlete": {}})
    monkeypatch.setattr(llm, "claude_complete", lambda prompt, **k: None)
    captured = {}

    def _complete(sys, user, **k):
        captured["sys"] = sys
        captured["user"] = user
        return "ответ gemini"

    monkeypatch.setattr(llm, "complete", _complete)
    answer, used = engine.ask("x.db", 1, "вопрос", lang="ru")
    assert answer == "ответ gemini" and used == "gemini"
    assert "ВОПРОС АТЛЕТА" in captured["user"]


def test_ask_both_fail(monkeypatch):
    monkeypatch.setattr(engine, "coach_payload", lambda *a, **k: {})
    monkeypatch.setattr(llm, "claude_complete", lambda prompt, **k: None)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: None)
    assert engine.ask("x.db", 1, "вопрос") == (None, None)


def test_coach_count_today(tmp_path):
    con = _con(tmp_path)
    db.add_coach_qa(con, 1, "2026-07-09T10:00:00", "q1", "a1")
    db.add_coach_qa(con, 1, "2026-07-09T22:00:00", "q2", "a2")
    db.add_coach_qa(con, 1, "2026-07-08T10:00:00", "вчерашний", "a")
    db.add_coach_qa(con, 2, "2026-07-09T10:00:00", "чужой", "a")
    assert db.coach_count_today(con, 1, "2026-07-09") == 2
    assert db.coach_count_today(con, 1, "2026-07-10") == 0


def test_coach_pro_gate(monkeypatch):
    from tjbot.handlers import coach as h
    monkeypatch.setattr(h.access, "is_admin", lambda tg_id, path=None: False)
    monkeypatch.setattr(h.access, "is_pro", lambda tg_id, path=None: tg_id == 7)
    assert h._pro_only(7) is False
    assert h._pro_only(8) is True
