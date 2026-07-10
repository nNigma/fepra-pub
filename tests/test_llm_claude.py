"""claude_vision: JSON-конверт CLI, роутер vision(engine=) и ролевая развилка."""
from __future__ import annotations

import json

import pytest

from tj import llm
from tjbot import vision as botvision

FLASH = [("k", "gemini-2.5-flash")]


@pytest.fixture(autouse=True)
def _enable_claude(monkeypatch):
    monkeypatch.setenv("KUZ_USE_CLAUDE", "1")


class _Proc:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = ""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _envelope(result: str, is_error: bool = False) -> str:
    return json.dumps({"type": "result", "is_error": is_error, "result": result,
                       "usage": {"input_tokens": 100, "output_tokens": 50}})


def test_claude_vision_success(monkeypatch, tmp_path):
    captured = {}

    def _run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return _Proc(_envelope('{"raw_text": "доска"}'))

    monkeypatch.setattr(llm, "_claude_bin", lambda: "/usr/local/bin/claude")
    monkeypatch.setattr(llm.subprocess, "run", _run)
    out = llm.claude_vision(b"\xff\xd8img", "ПРОМПТ")
    assert out == '{"raw_text": "доска"}'
    assert captured["cmd"][0] == "/usr/local/bin/claude"
    assert "--output-format" in captured["cmd"] and "json" in captured["cmd"]
    assert "--allowedTools" in captured["cmd"] and "Read" in captured["cmd"]
    assert "ПРОМПТ" in captured["cmd"][2]
    assert "board.jpg" in captured["cmd"][2]      # промпт ссылается на файл
    assert captured["cwd"]                        # изоляция во временной папке


def test_claude_vision_no_binary(monkeypatch):
    monkeypatch.setattr(llm, "_claude_bin", lambda: None)
    assert llm.claude_vision(b"img", "p") is None
    assert llm.has_claude_vision() is False


def test_claude_vision_nonzero_rc(monkeypatch):
    monkeypatch.setattr(llm, "_claude_bin", lambda: "claude")
    monkeypatch.setattr(llm.subprocess, "run", lambda *a, **k: _Proc("", returncode=1))
    assert llm.claude_vision(b"img", "p") is None


def test_claude_vision_is_error_envelope(monkeypatch):
    monkeypatch.setattr(llm, "_claude_bin", lambda: "claude")
    monkeypatch.setattr(llm.subprocess, "run",
                        lambda *a, **k: _Proc(_envelope("упал", is_error=True)))
    assert llm.claude_vision(b"img", "p") is None


def test_claude_vision_broken_envelope(monkeypatch):
    monkeypatch.setattr(llm, "_claude_bin", lambda: "claude")
    monkeypatch.setattr(llm.subprocess, "run", lambda *a, **k: _Proc("не json"))
    assert llm.claude_vision(b"img", "p") is None


def test_claude_vision_timeout(monkeypatch):
    monkeypatch.setattr(llm, "_claude_bin", lambda: "claude")

    def _boom(cmd, **k):
        raise llm.subprocess.TimeoutExpired(cmd=cmd, timeout=1)
    monkeypatch.setattr(llm.subprocess, "run", _boom)
    assert llm.claude_vision(b"img", "p") is None


def test_vision_router_claude_engine(monkeypatch):
    monkeypatch.setattr(llm, "claude_vision", lambda *a, **k: "от клода")
    monkeypatch.setattr(llm, "_attempts", lambda paid=True, model=None: FLASH)
    assert llm.vision(b"img", "p", engine="claude") == "от клода"


def test_vision_router_falls_back_to_gemini(monkeypatch):
    monkeypatch.setattr(llm, "claude_vision", lambda *a, **k: None)
    monkeypatch.setattr(llm, "_attempts", lambda paid=True, model=None: FLASH)

    class _Resp:
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "от gemini"}]}}],
                    "usageMetadata": {}}
        def raise_for_status(self): pass

    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: _Resp())
    assert llm.vision(b"img", "p", engine="claude") == "от gemini"


def test_vision_default_engine_skips_claude(monkeypatch):
    def _no_call(*a, **k):
        raise AssertionError("claude_vision не должен вызываться при engine=gemini")
    monkeypatch.setattr(llm, "claude_vision", _no_call)
    monkeypatch.setattr(llm, "_attempts", lambda paid=True, model=None: [])
    assert llm.vision(b"img", "p") is None


def test_engine_for_claude_for_everyone():
    assert botvision.engine_for(1) == "claude"
    assert botvision.engine_for(2) == "claude"


def test_meal_pro_gate(monkeypatch):
    from tjbot.handlers import meal
    from tjbot import access
    monkeypatch.setattr(meal.access, "is_admin", lambda tg_id, path=None: False)
    monkeypatch.setattr(meal.access, "is_pro", lambda tg_id, path=None: tg_id == 7)
    assert meal._pro_only(7) is False
    assert meal._pro_only(8) is True


def test_parse_board_gemini_first(monkeypatch):
    """Быстрое (engine='gemini'): первым идёт Gemini, Claude не трогаем."""
    captured = {}

    def _vision(image_bytes, prompt, *, media_type="image/jpeg", engine="gemini", **k):
        captured["engine"] = engine
        return '{"raw_text": "доска", "format": "amrap", "movements": []}'

    def _no_claude(*a, **k):
        raise AssertionError("claude не должен вызываться, когда gemini ответил")

    monkeypatch.setattr(botvision.llm, "vision", _vision)
    monkeypatch.setattr(botvision.llm, "claude_vision", _no_claude)
    out = botvision.parse_board(b"img", engine="gemini")
    assert captured["engine"] == "gemini"
    assert out and out["raw_text"] == "доска" and out["engine_used"] == "gemini"


def test_parse_board_claude_first(monkeypatch):
    """Медленное (engine='claude'): первым идёт Claude, Gemini не трогаем."""
    monkeypatch.setattr(botvision.llm, "has_claude_vision", lambda: True)
    monkeypatch.setattr(botvision.llm, "claude_vision",
                        lambda *a, **k: '{"raw_text": "доска", "format": "amrap", "movements": []}')

    def _no_gemini(*a, **k):
        raise AssertionError("gemini не должен вызываться, когда claude ответил")

    monkeypatch.setattr(botvision.llm, "vision", _no_gemini)
    out = botvision.parse_board(b"img", engine="claude")
    assert out and out["engine_used"] == "claude"


def test_parse_board_fallback_to_claude(monkeypatch):
    """Быстрое: Gemini молчит -> добивает Claude, помечает engine_used."""
    monkeypatch.setattr(botvision.llm, "vision", lambda *a, **k: None)
    monkeypatch.setattr(botvision.llm, "has_claude_vision", lambda: True)
    monkeypatch.setattr(botvision.llm, "claude_vision",
                        lambda *a, **k: '{"raw_text": "доска", "format": "other", "movements": []}')
    out = botvision.parse_board(b"img", engine="gemini")
    assert out and out["engine_used"] == "claude"
    monkeypatch.setattr(botvision.llm, "claude_vision", lambda *a, **k: None)
    assert botvision.parse_board(b"img", engine="gemini") is None
