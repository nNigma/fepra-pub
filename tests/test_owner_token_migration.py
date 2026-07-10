from tjbot import garmin_sync as gs
from tjbot import db as botdb


def test_owner_token_copied_once(tmp_path, monkeypatch):
    monkeypatch.setattr(botdb, "OWNER_ID", 12345678)
    old = tmp_path / "old_garmin"; old.mkdir(); (old / "oauth1_token.json").write_text("{}")
    dest = tmp_path / "garmin_tokens" / "12345678"
    monkeypatch.setattr(gs, "_owner_legacy_tokenstores", lambda: [old])
    gs.ensure_owner_token(12345678, dest)
    assert (dest / "oauth1_token.json").exists()
