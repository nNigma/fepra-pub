"""verify_result_blocks: Claude-сверка шаблона результатов + персист блоков программы."""
from __future__ import annotations

import json

from tj import llm
from tjbot import db as botdb
from tjbot import vision


def _blocks():
    return [{"header": "ТА", "format": "emom_strength", "rounds": 4, "reps": 4,
             "work_min": None, "rest_min": None, "has_cap": False,
             "movements": [{"name": "фронтальный присед", "canon": "front_squat",
                            "canons": ["front_squat"], "weighted": True}],
             "benchmark": None, "scheme": None}]


def _corrected_json():
    return json.dumps([{
        "header": "ТА", "format": "emom_strength", "rounds": 4, "reps": 4,
        "work_min": None, "rest_min": None, "has_cap": False, "scheme": None,
        "movements": ["фронтальный присед", "швунг жимовой 50 кг"],
    }], ensure_ascii=False)


def test_verify_happy_path(monkeypatch):
    monkeypatch.setattr(llm, "has_claude_vision", lambda: True)
    monkeypatch.setattr(llm, "claude_complete", lambda p, **k: _corrected_json())
    out, verified = vision.verify_result_blocks("доска", _blocks())
    assert verified is True
    assert len(out) == 1
    names = [m["name"] for m in out[0]["movements"]]
    assert names == ["фронтальный присед", "швунг жимовой 50 кг"]
    # канон перемаплен детерминированно через онтологию, не взят у Claude
    assert out[0]["movements"][0]["canon"] == "front_squat"


def test_verify_no_claude(monkeypatch):
    monkeypatch.setattr(llm, "has_claude_vision", lambda: False)
    src = _blocks()
    out, verified = vision.verify_result_blocks("доска", src)
    assert out is src and verified is False


def test_verify_broken_json(monkeypatch):
    monkeypatch.setattr(llm, "has_claude_vision", lambda: True)
    monkeypatch.setattr(llm, "claude_complete", lambda p, **k: "не json совсем")
    src = _blocks()
    out, verified = vision.verify_result_blocks("доска", src)
    assert out is src and verified is False


def test_verify_bad_format_rejected(monkeypatch):
    monkeypatch.setattr(llm, "has_claude_vision", lambda: True)
    bad = json.dumps([{"header": "X", "format": "придуманный",
                       "movements": ["присед"]}], ensure_ascii=False)
    monkeypatch.setattr(llm, "claude_complete", lambda p, **k: bad)
    src = _blocks()
    out, verified = vision.verify_result_blocks("доска", src)
    assert out is src and verified is False


def test_verify_empty_movements_rejected(monkeypatch):
    monkeypatch.setattr(llm, "has_claude_vision", lambda: True)
    bad = json.dumps([{"header": "X", "format": "for_time", "movements": []}])
    monkeypatch.setattr(llm, "claude_complete", lambda p, **k: bad)
    src = _blocks()
    out, verified = vision.verify_result_blocks("доска", src)
    assert out is src and verified is False


def test_verify_benchmark_blocks_untouched(monkeypatch):
    monkeypatch.setattr(llm, "has_claude_vision", lambda: True)
    called = []
    monkeypatch.setattr(llm, "claude_complete",
                        lambda p, **k: called.append(1) or _corrected_json())
    src = _blocks()
    src[0]["benchmark"] = "fran"
    out, verified = vision.verify_result_blocks("доска", src)
    assert out is src and verified is False and not called


def test_claude_complete_envelope(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "1")
    monkeypatch.setattr(llm, "_claude_bin", lambda: "claude")

    class _Proc:
        returncode = 0
        stdout = json.dumps({"is_error": False, "result": "ответ", "usage": {}})

    captured = {}

    def _run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return _Proc()

    monkeypatch.setattr(llm.subprocess, "run", _run)
    assert llm.claude_complete("ПРОМПТ") == "ответ"
    assert captured["cmd"][2] == "ПРОМПТ" and captured["cwd"]


def test_claude_complete_no_binary(monkeypatch):
    monkeypatch.setattr(llm, "_claude_bin", lambda: None)
    assert llm.claude_complete("p") is None


def test_program_blocks_roundtrip(tmp_path):
    con = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(con)
    blocks = _blocks()
    botdb.add_program(con, "2026-07-09", "Universe", "текст доски",
                      confirmed=1, blocks=blocks)
    prog = botdb.get_program(con, "2026-07-09", "Universe")
    assert prog is not None
    stored = json.loads(prog["blocks"])
    assert stored[0]["movements"][0]["canon"] == "front_squat"
    # без блоков — NULL
    botdb.add_program(con, "2026-07-10", "Universe", "текст", confirmed=1)
    prog2 = botdb.get_program(con, "2026-07-10", "Universe")
    assert prog2["blocks"] is None
    con.close()
