"""Сводка активности пользователей для админа. Чистый слой: без Telegram/БД.

Ключи действий — стабильные строки, подписи берутся из i18n (stat.action.<key>).
`render` собирает готовый текст из агрегата `db.action_counts`.
"""
from __future__ import annotations

from collections import defaultdict

from tj import i18n

WORKOUT_RECORDED = "workout_recorded"
WORKOUT_EDITED = "workout_edited"
RESULT_ADDED = "result_added"
GOAL_SET = "goal_set"
GARMIN_SYNC = "garmin_sync"
GARMIN_HISTORY = "garmin_history"
GARMIN_CONNECTED = "garmin_connected"
LLM_REVIEW = "llm_review"
MINIAPP_OPEN = "miniapp_open"
COMP_ADDED = "comp_added"
CLUB_PROGRAM_ADDED = "club_program_added"

ACTION_ORDER = [
    WORKOUT_RECORDED, WORKOUT_EDITED, RESULT_ADDED, GOAL_SET,
    GARMIN_SYNC, GARMIN_HISTORY, GARMIN_CONNECTED,
    LLM_REVIEW, MINIAPP_OPEN, COMP_ADDED, CLUB_PROGRAM_ADDED,
]


def _label(action: str, lang: str) -> str:
    return i18n.t(f"stat.action.{action}", lang)


def render(counts, nick_by_id, period_label: str, lang: str = "ru") -> str:
    per_user: dict[int, dict[str, int]] = defaultdict(dict)
    for row in counts:
        per_user[int(row["tg_id"])][row["action"]] = int(row["n"])

    title = i18n.t("stat.title", lang, period=period_label)
    if not per_user:
        return i18n.t("stat.empty", lang, period=period_label)

    users = sorted(per_user.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    blocks = [title, ""]
    for tg_id, actions in users:
        nick = nick_by_id.get(tg_id)
        head = f"{nick} ({tg_id})" if nick else f"({tg_id})"
        known = [a for a in ACTION_ORDER if actions.get(a)]
        extra = [a for a in actions if a not in ACTION_ORDER and actions.get(a)]
        parts = [f"{_label(a, lang)} {actions[a]}" for a in known + extra]
        total = sum(actions.values())
        blocks.append(head)
        blocks.append("  " + " · ".join(parts))
        blocks.append(i18n.t("stat.user_total", lang, total=total))
        blocks.append("")
    return "\n".join(blocks).rstrip()
