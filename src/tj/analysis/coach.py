"""ИИ-тренер: свободный вопрос с полным контекстом атлета (профиль, основные
типы тренировок, питание, сводка состояния, последние тренировки).
Движок: Claude CLI по подписке -> фолбэк Gemini. Сбой обоих -> (None, None)."""
from __future__ import annotations

import json
from datetime import date, timedelta

from tj import llm
from tj.analysis import nutrition as nutr
from tj.analysis.dashboard import summary_data
from tj.analysis.llm_coach import summary_payload
from tj.analysis.workouts import recent_workouts, sport_counts

_SYS_RU = (
    "Ты — персональный тренер по кроссфиту и фитнесу. Тебе дан JSON-контекст "
    "атлета: профиль (возраст/пол/рост/вес/зал), основные типы тренировок, "
    "питание за сегодня и вчера (ккал/БЖУ/вода), сводка состояния за 30 дней "
    "(готовность, нагрузка ACWR, риск, форма) и последние тренировки. "
    "Ответь на вопрос атлета как тренер: конкретно, практично, с цифрами из "
    "контекста. Опирайся ТОЛЬКО на данные контекста; чего в них нет — честно "
    "скажи, не выдумывай. Если вопрос про тренировку — дай конкретную "
    "рекомендацию (тип, объём, интенсивность/пульсовые зоны) с учётом текущей "
    "готовности и недавней нагрузки. Аббревиатуры расшифровывай при первом "
    "упоминании (RHR — пульс покоя, HRV — вариабельность пульса, ACWR — "
    "отношение свежей нагрузки к хронической). Пиши по-русски, 5-10 "
    "предложений, без воды и без markdown-заголовков."
)

_SYS_EN = (
    "You are a personal CrossFit and fitness coach. You get a JSON context of "
    "the athlete: profile (age/sex/height/weight/gym), main workout types, "
    "nutrition for today and yesterday (kcal/macros/water), a 30-day state "
    "summary (readiness, ACWR load, risk, form) and recent workouts. "
    "Answer the athlete's question as a coach: specific, practical, with "
    "numbers from the context. Rely ONLY on the context data; if something is "
    "missing, say so honestly - do not invent. If the question is about a "
    "workout, give a concrete recommendation (type, volume, intensity/HR "
    "zones) considering current readiness and recent load. Write in English, "
    "5-10 sentences, no fluff and no markdown headers."
)


def _day_nutrition(botdb, con, tg_id: int, day: str) -> dict | None:
    import sqlite3
    try:
        meals = botdb.meals_for_day(con, tg_id, day)
    except sqlite3.OperationalError:
        return None
    if not meals:
        return None
    t = nutr.day_totals(meals)
    return {"kcal": round(t["kcal"]), "protein_g": round(t["protein_g"]),
            "fat_g": round(t["fat_g"]), "carb_g": round(t["carb_g"]),
            "water_l": botdb.water_for_day(con, tg_id, day)}


_WK_FIELDS = ("day", "sport", "duration_min", "avg_hr", "wod_name", "score",
              "rpe", "readiness")


def coach_payload(db_path, tg_id: int, lang: str = "ru",
                  today: date | None = None) -> dict:
    from tjbot import db as botdb
    today = today or date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    con = botdb.connect(db_path)
    try:
        hr_max, sex = botdb.profile_hr_sex(con, tg_id)
        u = botdb.get_user(con, tg_id)
        weight = botdb.latest_weight(con, tg_id)
        nutrition = {"today": _day_nutrition(botdb, con, tg_id, today.isoformat()),
                     "yesterday": _day_nutrition(botdb, con, tg_id, yesterday)}
    finally:
        con.close()
    sports = sport_counts(db_path, "sqlite", tg_id=tg_id,
                          since=(today - timedelta(days=60)).isoformat())
    summary = summary_data(db_path, "sqlite", hr_max, sex, today, tg_id=tg_id, lang=lang)
    workouts = [{k: w.get(k) for k in _WK_FIELDS if w.get(k) is not None}
                for w in recent_workouts(db_path, "sqlite", limit=5, tg_id=tg_id, lang=lang)]
    athlete = {"age": u["age"] if u else None, "sex": sex,
               "height_cm": u["height_cm"] if u else None,
               "weight_kg": weight or (u["weight_kg"] if u else None),
               "gym": u["gym"] if u else None, "hr_max": hr_max}
    return {"athlete": athlete, "main_sports": sports, "nutrition": nutrition,
            "summary": summary_payload(summary), "recent_workouts": workouts}


def ask(db_path, tg_id: int, question: str, lang: str = "ru") -> tuple[str | None, str | None]:
    payload = coach_payload(db_path, tg_id, lang=lang)
    sys = _SYS_RU if lang == "ru" else _SYS_EN
    ctx_label = "КОНТЕКСТ" if lang == "ru" else "CONTEXT"
    q_label = "ВОПРОС АТЛЕТА" if lang == "ru" else "ATHLETE'S QUESTION"
    user = (f"{ctx_label}:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            f"{q_label}:\n{question.strip()}")
    text = llm.claude_complete(f"{sys}\n\n{user}")
    if text:
        return text.strip(), "claude"
    text = llm.complete(sys, user, max_output_tokens=1600)
    return (text.strip(), "gemini") if text else (None, None)
