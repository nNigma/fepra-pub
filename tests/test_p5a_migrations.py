"""Миграции 0050/0060: идемпотентны, только добавляют nullable-колонки; роуты зарегистрированы."""
from p5a_env import p5a  # noqa: F401
from tj.migrations import run_migrations
from tjapp.routes import ALL_ROUTERS


def _cols(con, t):
    return {r[1] for r in con.execute(f'PRAGMA table_info("{t}")')}


def test_columns_added_and_idempotent(p5a):
    assert "updated_at" in _cols(p5a.con, "users")
    assert {"uuid", "updated_at", "created_by"} <= _cols(p5a.con, "wod_programs")
    from tj.migrations import _registry
    for n, name in _registry():
        if n in (50, 60):
            import importlib
            importlib.import_module(f"tj.migrations.{name}").upgrade(p5a.con)   # повтор не падает
    assert run_migrations(p5a.con) >= 60


def test_bot_style_insert_still_works(p5a):
    """Бот и userbot пишут в wod_programs без новых колонок."""
    from tjbot import db as botdb
    botdb.add_program(p5a.con, "2026-09-28", "Universe", "текст", confirmed=1)
    r = botdb.get_program(p5a.con, "2026-09-28", "Universe")
    assert r["uuid"] is None


def test_phase5a_routes_registered():
    paths = {r.path for rt in ALL_ROUTERS for r in rt.routes}
    assert {"/api/profile", "/api/gyms", "/api/onboarding", "/api/coach/ask", "/api/coach/recent",
            "/api/admin/users", "/api/admin/users/{uid}/roles", "/api/admin/gyms", "/api/admin/coaches",
            "/api/admin/stats", "/api/admin/review", "/api/club/program", "/api/club/pending",
            "/api/club/pending/{prog_id}/confirm", "/api/club/stats", "/api/club/athletes"} <= paths
