from tj.services import urls
from tjapp import whoop_oauth
from tjbot.handlers import watch


def test_default_public_url(monkeypatch):
    monkeypatch.delenv("FEPRA_PUBLIC_URL", raising=False)
    assert urls.public_url() == "https://fepra.example"


def test_env_overrides_and_trailing_slash_stripped(monkeypatch):
    monkeypatch.setenv("FEPRA_PUBLIC_URL", "https://example.org/")
    assert urls.public_url() == "https://example.org"
    assert urls.public_link("/x/y") == "https://example.org/x/y"
    assert urls.invite_url("T") == "https://example.org/app/#/invite/T"


def test_whoop_redirect_built_from_public_url(monkeypatch):
    monkeypatch.delenv("WHOOP_REDIRECT_URI", raising=False)
    monkeypatch.setenv("FEPRA_PUBLIC_URL", "https://example.org")
    assert whoop_oauth.redirect_uri() == "https://example.org/whoop/callback"
    monkeypatch.setenv("WHOOP_REDIRECT_URI", "https://custom/cb")
    assert whoop_oauth.redirect_uri() == "https://custom/cb"


def test_watch_links_built_from_public_url(monkeypatch):
    monkeypatch.delenv("FEPRA_APK_URL", raising=False)
    monkeypatch.delenv("FEPRA_APPLE_URL", raising=False)
    monkeypatch.setenv("FEPRA_PUBLIC_URL", "https://example.org")
    assert watch.apk_url() == "https://example.org/fepra-connect.apk"
    assert watch.apple_ingest_url() == "https://example.org/ingest/apple"


def test_no_duckdns_left_in_source():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    assert not [p for p in root.rglob("*.py") if "duckdns" in p.read_text(encoding="utf-8")]
