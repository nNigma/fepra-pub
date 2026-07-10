from __future__ import annotations
import sqlite3

from tjbot import db as botdb
from tj.analysis import activity_stats as stats


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_log_and_count_all():
    con = _con()
    botdb.log_action(con, 1, "workout_recorded")
    botdb.log_action(con, 1, "workout_recorded")
    botdb.log_action(con, 1, "goal_set")
    botdb.log_action(con, 2, "miniapp_open")
    rows = botdb.action_counts(con)
    got = {(r["tg_id"], r["action"]): r["n"] for r in rows}
    assert got == {
        (1, "workout_recorded"): 2,
        (1, "goal_set"): 1,
        (2, "miniapp_open"): 1,
    }


def test_count_since_filters_by_ts():
    con = _con()
    botdb.log_action(con, 1, "workout_recorded", ts="2026-01-01T10:00:00+00:00")
    botdb.log_action(con, 1, "workout_recorded", ts="2026-07-05T10:00:00+00:00")
    rows = botdb.action_counts(con, since="2026-07-01T00:00:00+00:00")
    got = {(r["tg_id"], r["action"]): r["n"] for r in rows}
    assert got == {(1, "workout_recorded"): 1}


def test_render_empty():
    out = stats.render([], {}, "за 30 дней")
    assert "за 30 дней" in out
    assert "Пока нет" in out


def test_render_one_user():
    counts = [
        {"tg_id": 22222222, "action": "workout_recorded", "n": 5},
        {"tg_id": 22222222, "action": "result_added", "n": 3},
        {"tg_id": 22222222, "action": "garmin_sync", "n": 10},
        {"tg_id": 22222222, "action": "llm_review", "n": 2},
    ]
    out = stats.render(counts, {22222222: "Петя"}, "за 30 дней")
    assert "📊 Статистика · за 30 дней" in out
    assert "Петя (22222222)" in out
    assert "Тренировка 5" in out
    assert "Результат 3" in out
    assert "Синк Garmin 10" in out
    assert "Разбор ИИ 2" in out
    assert "всего: 20" in out


def test_render_sorts_users_by_total_desc():
    counts = [
        {"tg_id": 1, "action": "workout_recorded", "n": 2},
        {"tg_id": 2, "action": "miniapp_open", "n": 8},
        {"tg_id": 2, "action": "workout_recorded", "n": 2},
    ]
    out = stats.render(counts, {1: "A", 2: "B"}, "за всё время")
    assert out.index("B (2)") < out.index("A (1)")


def test_render_unknown_nick_shows_id_only():
    counts = [{"tg_id": 55, "action": "goal_set", "n": 1}]
    out = stats.render(counts, {}, "за 7 дней")
    assert "(55)" in out
    assert "Цель 1" in out
