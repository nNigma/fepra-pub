from tjbot.handlers import garmin as gh


def test_adapter_factory_builds_with_tokenstore(tmp_path, monkeypatch):
    captured = {}

    class _Ad:
        def __init__(self, email, password, tokenstore, tz, prompt_mfa=None, **kw):
            captured.update(email=email, tokenstore=str(tokenstore), has_cb=prompt_mfa is not None)

        def _login(self): return object()

    monkeypatch.setattr(gh, "GarminAdapter", _Ad)
    f = gh._adapter_factory(tz=None)
    f("e@x", "secret", tmp_path / "ts", prompt_mfa=lambda: "1")
    assert captured["email"] == "e@x" and captured["has_cb"] and captured["tokenstore"].endswith("ts")
