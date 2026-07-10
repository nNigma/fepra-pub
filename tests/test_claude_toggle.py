import textwrap

from tj import config as cfgmod


def _write_cfg(tmp_path, body: str):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_claude_enabled_default_false(tmp_path, monkeypatch):
    monkeypatch.delenv("KUZ_USE_CLAUDE", raising=False)
    cfgmod.reset_claude_cache()
    monkeypatch.setattr(cfgmod, "load_config", lambda *a, **k: {})
    assert cfgmod.claude_enabled() is False


def test_claude_enabled_from_config_true(tmp_path, monkeypatch):
    monkeypatch.delenv("KUZ_USE_CLAUDE", raising=False)
    cfgmod.reset_claude_cache()
    monkeypatch.setattr(cfgmod, "load_config",
                        lambda *a, **k: {"llm": {"use_claude": True}})
    assert cfgmod.claude_enabled() is True


def test_claude_enabled_env_override_wins(monkeypatch):
    cfgmod.reset_claude_cache()
    monkeypatch.setattr(cfgmod, "load_config",
                        lambda *a, **k: {"llm": {"use_claude": True}})
    monkeypatch.setenv("KUZ_USE_CLAUDE", "0")
    assert cfgmod.claude_enabled() is False
    monkeypatch.setenv("KUZ_USE_CLAUDE", "1")
    assert cfgmod.claude_enabled() is True


def test_claude_enabled_missing_config_is_false(monkeypatch):
    monkeypatch.delenv("KUZ_USE_CLAUDE", raising=False)
    cfgmod.reset_claude_cache()

    def _raise(*a, **k):
        raise FileNotFoundError("no config")

    monkeypatch.setattr(cfgmod, "load_config", _raise)
    assert cfgmod.claude_enabled() is False
