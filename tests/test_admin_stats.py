from __future__ import annotations
import sqlite3
from datetime import datetime, timezone

from tjbot import db as botdb
from tjbot.handlers import admin


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)


def test_period_since_all():
    since, key = admin._period_since("all", NOW)
    assert since is None
    assert key == "stat.period.all"


def test_period_since_7_days():
    since, key = admin._period_since("7", NOW)
    assert since == "2026-06-29T12:00:00+00:00"
    assert key == "stat.period.7"


def test_stats_text_all_time():
    con = _con()
    botdb.save_user(con, 42, nick="Петя", height_cm=180, weight_kg=80, sex="m", age=36, gym="Universe")
    botdb.log_action(con, 42, "workout_recorded", ts="2026-07-05T10:00:00+00:00")
    botdb.log_action(con, 42, "workout_recorded", ts="2026-07-05T11:00:00+00:00")
    botdb.log_action(con, 42, "goal_set", ts="2026-01-01T10:00:00+00:00")
    text = admin._stats_text(con, "all", NOW, "ru")
    assert "Петя (42)" in text
    assert "Тренировка 2" in text
    assert "Цель 1" in text
    assert "всего: 3" in text


def test_stats_text_period_excludes_old():
    con = _con()
    botdb.save_user(con, 42, nick="Петя", height_cm=180, weight_kg=80, sex="m", age=36, gym="Universe")
    botdb.log_action(con, 42, "workout_recorded", ts="2026-07-05T10:00:00+00:00")
    botdb.log_action(con, 42, "goal_set", ts="2026-01-01T10:00:00+00:00")
    text = admin._stats_text(con, "7", NOW, "ru")
    assert "Тренировка 1" in text
    assert "Цель" not in text
