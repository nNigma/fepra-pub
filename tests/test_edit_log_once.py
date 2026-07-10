from __future__ import annotations
from types import SimpleNamespace

from tjbot import db as botdb
from tjbot.handlers import edit_workout


def _counts(dbp):
    con = botdb.connect(str(dbp))
    try:
        return {(r["tg_id"], r["action"]): r["n"] for r in botdb.action_counts(con)}
    finally:
        con.close()


def test_edit_logged_once_per_session(tmp_path):
    dbp = tmp_path / "t.db"
    con = botdb.connect(str(dbp)); botdb.init_schema(con); con.close()
    ctx = SimpleNamespace(bot_data={"db_path": str(dbp)}, user_data={})

    edit_workout._log_edit_once(ctx, 5)
    edit_workout._log_edit_once(ctx, 5)
    edit_workout._log_edit_once(ctx, 5)
    assert _counts(dbp) == {(5, "workout_edited"): 1}

    ctx.user_data["_edit_logged"] = False  # новая сессия правки (после pick)
    edit_workout._log_edit_once(ctx, 5)
    assert _counts(dbp) == {(5, "workout_edited"): 2}
