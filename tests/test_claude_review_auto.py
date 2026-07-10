"""tjbot.claude_review: авторазборы Месье Клода через claude -p (крон)."""
from __future__ import annotations

import json

from tj import llm
from tjbot import claude_review as cr
from tjbot import db as botdb


def _con(tmp_path):
    con = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(con)
    return con


def _llm_answer():
    nar = [{"kind": "verdict", "title": "Что развивает", "body": "б"},
           {"kind": "section", "title": "Зоны", "body": "б"},
           {"kind": "section", "title": "Интенсивные минуты", "body": "б"},
           {"kind": "risk", "title": "Риск", "body": "б"},
           {"kind": "advice", "title": "Совет", "body": "б"}]
    return json.dumps({"review_md": "## Как ты подошёл\nтекст", "narrative": nar},
                      ensure_ascii=False)


def test_valid_narrative():
    assert cr._valid_narrative(json.loads(_llm_answer())["narrative"]) is True
    assert cr._valid_narrative([]) is False
    assert cr._valid_narrative([{"kind": "x"}]) is False
    assert cr._valid_narrative("не список") is False


def test_extract_obj_fenced():
    raw = "```json\n" + _llm_answer() + "\n```"
    obj = cr._extract_obj(raw)
    assert obj and "review_md" in obj


def test_review_day_saves(tmp_path, monkeypatch):
    con = _con(tmp_path)
    monkeypatch.setattr(cr, "workout_report",
                        lambda *a, **k: {"trimp": 42, "history": []})
    monkeypatch.setattr(cr.llm_coach, "workout_payload",
                        lambda rep: {"board": "доска", "work": {"strength": [1]}})
    monkeypatch.setattr(llm, "claude_complete", lambda p, **k: _llm_answer())
    res = cr.review_day(con, 111, "2026-07-08", "crossfit")
    assert res.get("ok") is True and res.get("narrative") is True
    row = con.execute('SELECT "text" FROM claude_review WHERE "tg_id"=111').fetchone()
    assert row and "Как ты подошёл" in row["text"]
    nar = con.execute('SELECT * FROM wk_narrative WHERE "tg_id"=111').fetchone()
    assert nar is not None
    con.close()


def test_review_day_skips_crossfit_without_board(tmp_path, monkeypatch):
    con = _con(tmp_path)
    monkeypatch.setattr(cr, "workout_report", lambda *a, **k: {"trimp": 1})
    monkeypatch.setattr(cr.llm_coach, "workout_payload",
                        lambda rep: {"board": None, "work": None})
    called = []
    monkeypatch.setattr(llm, "claude_complete",
                        lambda p, **k: called.append(1) or _llm_answer())
    res = cr.review_day(con, 111, "2026-07-08", "crossfit")
    assert "skip" in res and not called
    con.close()


def test_review_day_llm_fail(tmp_path, monkeypatch):
    con = _con(tmp_path)
    monkeypatch.setattr(cr, "workout_report",
                        lambda *a, **k: {"trimp": 1, "history": []})
    monkeypatch.setattr(cr.llm_coach, "workout_payload",
                        lambda rep: {"board": "доска", "work": {}})
    monkeypatch.setattr(llm, "claude_complete", lambda p, **k: None)
    res = cr.review_day(con, 111, "2026-07-08", "crossfit")
    assert res.get("error") == "llm"
    assert con.execute('SELECT COUNT(*) c FROM claude_review').fetchone()["c"] == 0
    con.close()


def test_run_all_without_claude(monkeypatch):
    monkeypatch.setattr(llm, "has_claude_vision", lambda: False)
    out = cr.run_all()
    assert out and "error" in out[0]


def test_latest_weight(tmp_path):
    con = _con(tmp_path)
    assert botdb.latest_weight(con, 111) is None
    botdb.set_bodyweight(con, "2026-07-05", 82.5, 111)
    botdb.set_bodyweight(con, "2026-07-08", 83.0, 111)
    assert botdb.latest_weight(con, 111) == 83.0
    assert botdb.latest_weight(con, 111, "2026-07-06") == 82.5   # не позже дня
    assert botdb.latest_weight(con, 222) is None                 # чужой вес не течёт
    con.close()


def test_review_day_includes_bodyweight(tmp_path, monkeypatch):
    con = _con(tmp_path)
    botdb.set_bodyweight(con, "2026-07-07", 83.0, 111)
    monkeypatch.setattr(cr, "workout_report",
                        lambda *a, **k: {"trimp": 1, "history": []})
    monkeypatch.setattr(cr.llm_coach, "workout_payload",
                        lambda rep: {"board": "доска", "work": {}})
    prompts = []
    monkeypatch.setattr(llm, "claude_complete",
                        lambda p, **k: prompts.append(p) or _llm_answer())
    cr.review_day(con, 111, "2026-07-08", "crossfit")
    assert '"bodyweight_kg": 83.0' in prompts[0]
    con.close()


def test_admin_review_report():
    from tjbot.handlers import admin
    res = [{"tg_id": 111, "days": [{"ok": True}, {"skip": "x"}, {"error": "llm"}],
            "summary": True, "advice": True}]
    text = admin._review_report(res, "ru")
    assert "111" in text and "разобрано 1" in text and "пропущено 1" in text
    assert "ошибок 1" in text and "✅" in text
    fail = admin._review_report([{"error": "claude CLI недоступен"}], "ru")
    assert "упал" in fail


def test_admin_kb_has_review_button():
    from tjbot.handlers import admin
    from tj import i18n
    kb = admin.admin_kb("ru")
    texts = [b.text if hasattr(b, "text") else b for row in kb.keyboard for b in row]
    assert i18n.t("btn.admin_review", "ru") in texts
