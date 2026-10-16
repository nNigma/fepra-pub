import json

import pytest

from tj import llm
from tjbot import vision


def test_engine_for_default_claude(monkeypatch):
    monkeypatch.delenv("FEPRA_LLM_ENGINE", raising=False)
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    assert vision.engine_for(1) == "claude"


def test_engine_for_agent_when_helper_present(monkeypatch, tmp_path):
    helper = tmp_path / "fepra-infer.sh"
    helper.write_text("#!/bin/bash\n")
    monkeypatch.setenv("FEPRA_AGENT_HELPER", str(helper))
    monkeypatch.setenv("FEPRA_LLM_ENGINE", "agent")
    assert vision.engine_for(1) == "agent"


def test_engine_for_falls_back_when_agent_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("FEPRA_AGENT_HELPER", str(tmp_path / "нет-такого"))
    monkeypatch.setenv("FEPRA_LLM_ENGINE", "agent")
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    assert vision.engine_for(1) == "claude"


def test_agent_text_reads_outputs():
    assert llm._agent_text({"ok": True, "outputs": [{"text": "привет"}]}) == "привет"
    assert llm._agent_text({"ok": True, "text": "привет"}) == "привет"
    assert llm._agent_text({"ok": False, "outputs": [{"text": "x"}]}) is None
    assert llm._agent_text({"ok": True, "outputs": []}) is None


def test_agent_run_parses_helper_output(monkeypatch, tmp_path):
    helper = tmp_path / "helper.sh"
    helper.write_text("#!/bin/bash\n")
    monkeypatch.setenv("FEPRA_AGENT_HELPER", str(helper))
    payload = json.dumps({"ok": True, "outputs": [{"text": "12 свингов"}]})

    class P:
        returncode = 0
        stdout = payload
        stderr = ""

    monkeypatch.setattr(llm.subprocess, "run", lambda *a, **k: P())
    assert llm.agent_run("промпт", image_bytes=b"jpg") == "12 свингов"


def test_vision_falls_back_to_gemini_when_agent_raises(monkeypatch):
    """Сбой инфраструктуры движка по подписке не должен выглядеть как отказ
    задачи: запрос обязан уехать в Gemini."""
    def boom(*a, **k):
        raise PermissionError("нет прав на файл блокировки")

    monkeypatch.setattr(llm, "agent_run", boom)
    monkeypatch.setattr(llm, "_attempts", lambda **k: [("key", "gemini-2.5-flash")])
    monkeypatch.setattr(llm, "_run", lambda *a, **k: "ответ гемини")
    assert llm.vision(b"jpg", "промпт", engine="agent") == "ответ гемини"


def test_vision_falls_back_to_gemini_when_claude_raises(monkeypatch):
    def boom(*a, **k):
        raise PermissionError("тот самый lock из /tmp")

    monkeypatch.setattr(llm, "claude_vision", boom)
    monkeypatch.setattr(llm, "_attempts", lambda **k: [("key", "gemini-2.5-flash")])
    monkeypatch.setattr(llm, "_run", lambda *a, **k: "ответ гемини")
    assert llm.vision(b"jpg", "промпт", engine="claude") == "ответ гемини"


def test_subscription_complete_swallows_exceptions(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("упало")

    monkeypatch.setattr(llm, "claude_complete", boom)
    assert llm.subscription_complete("промпт", engine="claude") is None


@pytest.mark.parametrize("engine,fn", [("agent", "agent_run"), ("claude", "claude_complete")])
def test_subscription_complete_routes_by_engine(monkeypatch, engine, fn):
    monkeypatch.setattr(llm, fn, lambda *a, **k: f"ответ {engine}")
    assert llm.subscription_complete("промпт", engine=engine) == f"ответ {engine}"


def test_agent_run_survives_cli_preamble(monkeypatch, tmp_path):
    """CLI печатает диагностику перед JSON — это не должно ломать разбор."""
    helper = tmp_path / "helper.sh"
    helper.write_text("#!/bin/bash\n")
    monkeypatch.setenv("FEPRA_AGENT_HELPER", str(helper))

    class P:
        returncode = 0
        stdout = '[provider-transport] шум\n{"ok": true, "outputs": [{"text": "4"}]}'
        stderr = ""

    monkeypatch.setattr(llm.subprocess, "run", lambda *a, **k: P())
    assert llm.agent_run("сколько будет два плюс два") == "4"


def test_parse_board_uses_agent_engine(monkeypatch):
    """Доски тоже должны идти через агента, а не мимо роутера."""
    monkeypatch.setattr(llm, "has_agent", lambda: True)
    monkeypatch.setattr(llm, "agent_run", lambda *a, **k: '{"movements": ["бёрпи"], "raw_text": "5 бёрпи"}')
    monkeypatch.setattr(llm, "claude_vision", lambda *a, **k: pytest.fail("claude не должен вызываться"))
    out = vision.parse_board(b"jpg", engine="agent")
    assert out and out["engine_used"] == "agent" and out["movements"] == ["бёрпи"]


def test_parse_board_agent_failure_falls_back_to_gemini(monkeypatch):
    monkeypatch.setattr(llm, "has_agent", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("агент недоступен")

    monkeypatch.setattr(llm, "agent_run", boom)
    monkeypatch.setattr(llm, "vision", lambda *a, **k: '{"movements": ["присед"], "raw_text": "10 приседов"}')
    out = vision.parse_board(b"jpg", engine="agent")
    assert out and out["engine_used"] == "gemini"
