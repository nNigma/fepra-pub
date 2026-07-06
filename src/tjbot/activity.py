"""Логирование ключевых действий пользователя. Обёртка над db.log_action.

Логирование не должно ронять хендлер — любые ошибки глотаем. Ключи действий
и их подписи живут в tj.analysis.activity_stats.
"""
from __future__ import annotations

from tj.analysis.activity_stats import (
    WORKOUT_RECORDED, WORKOUT_EDITED, RESULT_ADDED, GOAL_SET,
    GARMIN_SYNC, GARMIN_HISTORY, GARMIN_CONNECTED,
    LLM_REVIEW, MINIAPP_OPEN, COMP_ADDED, CLUB_PROGRAM_ADDED,
)

from . import db as botdb


def log(context, tg_id: int, action: str) -> None:
    try:
        con = botdb.connect(context.bot_data["db_path"])
        try:
            botdb.log_action(con, tg_id, action)
        finally:
            con.close()
    except Exception:
        pass
