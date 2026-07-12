import textwrap

from tj import config as cfgmod


def _write_cfg(tmp_path, body: str):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_claude_enabled_default_false(tmp_path, monkeypatch):
    monkeypatch.delenv("FEPRA_USE_CLAUDE", raising=False)
    cfgmod.reset_claude_cache()
    monkeypatch.setattr(cfgmod, "load_config", lambda *a, **k: {})
    assert cfgmod.claude_enabled() is False


def test_claude_enabled_from_config_true(tmp_path, monkeypatch):
    monkeypatch.delenv("FEPRA_USE_CLAUDE", raising=False)
    cfgmod.reset_claude_cache()
    monkeypatch.setattr(cfgmod, "load_config",
                        lambda *a, **k: {"llm": {"use_claude": True}})
    assert cfgmod.claude_enabled() is True


def test_claude_enabled_env_override_wins(monkeypatch):
    cfgmod.reset_claude_cache()
    monkeypatch.setattr(cfgmod, "load_config",
                        lambda *a, **k: {"llm": {"use_claude": True}})
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "0")
    assert cfgmod.claude_enabled() is False
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    assert cfgmod.claude_enabled() is True


def test_claude_enabled_missing_config_is_false(monkeypatch):
    monkeypatch.delenv("FEPRA_USE_CLAUDE", raising=False)
    cfgmod.reset_claude_cache()

    def _raise(*a, **k):
        raise FileNotFoundError("no config")

    monkeypatch.setattr(cfgmod, "load_config", _raise)
    assert cfgmod.claude_enabled() is False


from tj import llm


def test_claude_complete_gated_off(monkeypatch):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "0")
    called = {"bin": False}
    monkeypatch.setattr(llm, "_claude_bin", lambda: (called.__setitem__("bin", True) or "/x/claude"))
    assert llm.claude_complete("привет") is None
    assert called["bin"] is False  # до бинарника даже не дошли


def test_claude_vision_gated_off(monkeypatch):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "0")
    monkeypatch.setattr(llm, "_claude_bin", lambda: "/x/claude")
    assert llm.claude_vision(b"\xff\xd8", "prompt") is None


def test_has_claude_vision_gated_off(monkeypatch):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "0")
    monkeypatch.setattr(llm, "_claude_bin", lambda: "/x/claude")
    assert llm.has_claude_vision() is False


def test_has_claude_vision_on_with_bin(monkeypatch):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    monkeypatch.setattr(llm, "_claude_bin", lambda: "/x/claude")
    assert llm.has_claude_vision() is True


def test_claude_complete_uses_api_when_no_cli(monkeypatch):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    monkeypatch.setattr(llm, "_claude_bin", lambda: None)          # CLI нет
    monkeypatch.setattr(llm, "_anthropic_complete",
                        lambda prompt, **k: "API-ответ")
    assert llm.claude_complete("вопрос") == "API-ответ"


def test_claude_complete_prefers_cli_over_api(monkeypatch):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    monkeypatch.setattr(llm, "_claude_bin", lambda: "/x/claude")
    monkeypatch.setattr(llm, "_claude_run", lambda *a, **k: "CLI-ответ")
    monkeypatch.setattr(llm, "_anthropic_complete",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("API не должен вызываться")))
    assert llm.claude_complete("вопрос") == "CLI-ответ"


def test_deep_complete_claude_when_enabled(monkeypatch):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    monkeypatch.setattr(llm, "claude_complete", lambda p, **k: "глубокий Claude")
    monkeypatch.setattr(llm, "complete",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Gemini не нужен")))
    assert llm.deep_complete("prompt") == "глубокий Claude"


def test_deep_complete_gemini_when_disabled(monkeypatch):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "0")
    # claude_complete под гейтом сам вернёт None
    monkeypatch.setattr(llm, "complete", lambda system, user, **k: "глубокий Gemini")
    assert llm.deep_complete("prompt") == "глубокий Gemini"


def test_engine_for_off_is_gemini(monkeypatch):
    from tjbot import vision
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "0")
    assert vision.engine_for(123) == "gemini"


def test_engine_for_on_is_claude(monkeypatch):
    from tjbot import vision
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    assert vision.engine_for(123) == "claude"


def test_review_ask_uses_deep_complete(monkeypatch):
    from tjbot import claude_review
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "0")
    monkeypatch.setattr(llm, "deep_complete", lambda p, **k: '{"blocks": []}')
    assert claude_review._ask("инструкция") == {"blocks": []}


def test_run_all_no_hardstop_without_claude(monkeypatch):
    from tjbot import claude_review
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "0")
    monkeypatch.setattr(llm, "has_claude_vision", lambda: False)
    monkeypatch.setattr(claude_review.access, "load_pro", lambda: set())
    # раньше возвращал [{"error": "claude CLI недоступен"}]; теперь — обычный (пустой) прогон
    out = claude_review.run_all(db_path=":memory:")
    assert out == [] or all("claude CLI недоступен" not in str(x) for x in out)
