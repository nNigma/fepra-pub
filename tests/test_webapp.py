"""Раздача PWA: /app/, SPA-fallback, политика кэша."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tjapp import webapp


def _client(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>shell</html>")
    (tmp_path / "sw.js").write_text("// sw")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    webapp.mount(app, tmp_path)
    return TestClient(app)


def test_index_no_cache(tmp_path):
    r = _client(tmp_path).get("/app/")
    assert r.status_code == 200 and "shell" in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_sw_no_cache_and_assets_immutable(tmp_path):
    c = _client(tmp_path)
    assert c.get("/app/sw.js").headers["cache-control"] == "no-cache"
    a = c.get("/app/assets/index-abc123.js")
    assert a.status_code == 200
    assert "immutable" in a.headers["cache-control"]


def test_spa_fallback_for_unknown_route_but_not_for_missing_file(tmp_path):
    c = _client(tmp_path)
    r = c.get("/app/workouts/2026-09-01")
    assert r.status_code == 200 and "shell" in r.text
    assert r.headers["cache-control"] == "no-cache"
    assert c.get("/app/assets/nope.js").status_code == 404


def test_api_not_shadowed(tmp_path):
    assert _client(tmp_path).get("/api/ping").json() == {"ok": True}


def test_missing_build_is_skipped(tmp_path):
    app = FastAPI()
    webapp.mount(app, tmp_path / "нет")
    assert TestClient(app).get("/app/").status_code == 404


def test_real_app_serves_build():
    import pathlib
    import pytest
    from tjapp.api import app

    build = pathlib.Path(__file__).resolve().parents[1] / "src/tjapp/static/app/index.html"
    if not build.exists():
        pytest.skip("PWA не собрана: cd web && npm ci && npm run build")

    r = TestClient(app).get("/app/")
    assert r.status_code == 200 and '<div id="root">' in r.text
