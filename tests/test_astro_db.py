from __future__ import annotations

from tjbot import db


def test_astro_default_flip_persist(tmp_path):
    con = db.connect(str(tmp_path / "t.db")); db.init_schema(con)
    db.save_user(con, 1, nick="a", height_cm=180, weight_kg=80, sex="m", gym="G")
    assert db.user_astro(con, 1) is False
    db.set_astro(con, 1, True)
    assert db.user_astro(con, 1) is True
    db.set_astro(con, 1, False)
    assert db.user_astro(con, 1) is False


def test_llm_cache_delete(tmp_path):
    con = db.connect(str(tmp_path / "t.db")); db.init_schema(con)
    db.llm_cache_put(con, 1, "workout", "2026-07-03", "h1", "текст ru", "gemini", lang="ru")
    db.llm_cache_put(con, 1, "workout", "2026-07-03", "h2", "text en", "gemini", lang="en")
    db.llm_cache_delete(con, 1, "workout", "2026-07-03")
    assert db.llm_cache_get(con, 1, "workout", "2026-07-03", "h1", lang="ru") is None
    assert db.llm_cache_get(con, 1, "workout", "2026-07-03", "h2", lang="en") is None
