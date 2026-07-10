from tjbot import garmin_sync as gs


def test_owner_token_copied_once(tmp_path, monkeypatch):
    old = tmp_path / "old_garmin"; old.mkdir(); (old / "oauth1_token.json").write_text("{}")
    dest = tmp_path / "garmin_tokens" / "REDACTED"
    monkeypatch.setattr(gs, "_owner_legacy_tokenstores", lambda: [old])
    gs.ensure_owner_token(REDACTED, dest)
    assert (dest / "oauth1_token.json").exists()
