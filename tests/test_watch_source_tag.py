from tj.analysis.dashboard import readiness_source
from tjbot.handlers.whoop import auth_url


def test_bio_readiness_tagged_watch():
    assert readiness_source(72, None) == (72, "watch")


def test_self_feel_fallback_unchanged():
    assert readiness_source(None, 4) == (40, "self")
    assert readiness_source(None, None) == (None, None)


def test_whoop_auth_url_contains_params():
    url = auth_url("cid123", "https://fepra.example.org/whoop/callback", "state456")
    assert "client_id=cid123" in url
    assert "redirect_uri=https%3A%2F%2Ffepra.example.org%2Fwhoop%2Fcallback" in url
    assert "state=state456" in url
    assert "scope=" in url
