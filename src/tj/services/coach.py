"""ИИ-тренер (Pro): лимиты и вызов движка tj.analysis.coach; ответы — coach_qa.

Логика лимитов та же, что в handlers/coach.py: не-админ — не больше COACH_DAILY_LIMIT
вопросов в день И общая суточная квота ИИ (access.llm_quota_consume). Сам вопрос идёт
задачей (tj.services.jobs), поэтому здесь отдельно проверка/списание и тело задачи.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from tj.analysis import coach as engine
from tjbot import access
from tjbot import db as botdb

from .clock import tz_name

COACH_DAILY_LIMIT = 3       # вопросов/день для не-админа (равно handlers.coach.COACH_DAILY_LIMIT)
MAX_QUESTION = 2000
RECENT_LIMIT = 20


class CoachError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def check_and_consume(con, uid: int, day: str) -> None:
    """Проверить лимиты и списать обращение к ИИ. Админ без лимитов."""
    if access.is_admin(uid):
        return
    if botdb.coach_count_today(con, uid, day) >= COACH_DAILY_LIMIT:
        raise CoachError(429, f"лимит тренера: {COACH_DAILY_LIMIT} вопроса в день")
    if not access.llm_quota_consume(uid, con):
        raise CoachError(429, f"суточный лимит обращений к ИИ ({access.LLM_DAILY_LIMIT}) исчерпан")


def ask_and_store(db_path, uid: int, question: str, lang: str = "ru") -> dict:
    """Тело задачи: спросить тренера, сохранить пару вопрос-ответ. Пустой ответ = ошибка задачи."""
    answer, used = engine.ask(str(db_path), uid, question, lang)
    if not answer:
        raise RuntimeError("тренер не смог ответить, попробуйте позже")
    ts = datetime.now(ZoneInfo(tz_name())).isoformat(timespec="seconds")
    con = botdb.connect(db_path)
    try:
        qa_id = botdb.add_coach_qa(con, uid, ts, question, answer, lang, used)
    finally:
        con.close()
    return {"id": qa_id, "answer": answer, "engine": used, "ts": ts}


def recent(con, uid: int, limit: int = 5) -> list[dict]:
    return botdb.coach_recent(con, uid, limit=max(1, min(int(limit), RECENT_LIMIT)))
