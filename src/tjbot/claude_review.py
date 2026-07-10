"""Авторазборы Месье Клода через headless `claude -p` (крон на сервере).

Порт логики скилла kuznitsa-claude-review в автономный режим: по каждому
Pro-атлету — поденные разборы новых тренировок + общий разбор Сводки за 30 дней
+ совет на следующую тренировку. Показ и так за Pro-гейтом, поэтому и генерим
только Pro. Текст пишет Claude по подписке (llm.claude_complete, под общим
файловым локом с vision); сбой любого шага — пропуск этого шага, не стоп прогона.

Запуск на сервере: server_review.py ПОСЛЕ server_sync.py (данные уже свежие).
"""
from __future__ import annotations

import datetime
import json

from tj import llm
from tj.analysis import llm_coach
from tj.analysis.dashboard import summary_data
from tj.analysis.workouts import recent_workouts, workout_report

from . import access
from . import db as botdb

LOOKBACK_DAYS = 30            # свежие дни важнее архива (как в скилле)
_TIMEOUT = 300.0              # разбор с большим контекстом думает дольше vision

_ROLE = (
    "Ты — Месье Клод, тренер-аналитик «Кузницы» (кроссфит и выносливость). "
    "Пишешь глубокий тренерский разбор по-русски, опираясь ТОЛЬКО на цифры из "
    "данных; чего нет в данных — честно не выдумываешь. Без воды."
)

_ASTRO_NOTE = (
    " Самым последним абзацем разбора добавь шуточный блок «🔮 Астро-разбор от "
    "Месье Клода:» — 1-2 фразы барского гороскопа, обыгрывающие цифры этой "
    "тренировки/периода астро-языком (это чистый юмор, не совет)."
)

_WORKOUT_INSTR = (
    "Ниже JSON-контекст тренировки за {day}: payload (как подошёл — сон/пульс "
    "покоя/готовность/HRV/ACWR; как прошла — зоны/Training Effect; work — веса/"
    "повторы/тоннаж/метконы; board — замысел доски; nutrition — еда/вода за день "
    "и накануне, если записаны — учитывай в «Как ты подошёл»: топливо и "
    "восстановление), history — прошлые сессии той же программы (like-for-like), "
    "trimp.\n"
    "Напиши markdown-разбор тремя разделами: '## Как ты подошёл' (восстановлен "
    "ли на входе), '## Как прошла' (внутренняя нагрузка, что развивала, цена), "
    "'## Разбор работы' (факт против замысла доски, прогресс по подходам, "
    "сравнение с history; в конце практичный совет).{astro}\n"
    "Также сделай компактную выжимку — СТРОГО пять блоков:\n"
    '[{{"kind":"verdict","title":"Что развивает","body":"…"}},'
    '{{"kind":"section","title":"Зоны","body":"…"}},'
    '{{"kind":"section","title":"Интенсивные минуты","body":"…"}},'
    '{{"kind":"risk","title":"Риск","body":"…"}},'
    '{{"kind":"advice","title":"Совет","body":"…"}}]\n'
    'Верни ТОЛЬКО JSON-объект вида {{"review_md":"…","narrative":[…]}}.\n\n'
    "ДАННЫЕ:\n{context}"
)

_SUMMARY_INSTR = (
    "Ниже JSON-контекст формы атлета за 30 дней: payload (форма, ACWR, VO2max, "
    "тренды, риск; nutrition7 — среднее питание за неделю, если записано — "
    "свяжи с нагрузкой и восстановлением), sessions — тренировки окна.\n"
    "Напиши общий markdown-разбор тремя разделами: '## Куда идёт форма' "
    "(динамика месяца), '## Что за блок' (характер 30 дней: баланс модальностей, "
    "перекосы, тяжёлые серии), '## Риски и куда дальше'.{astro}\n"
    "Плюс ОДНУ строку — совет, что делать на ближайшей тренировке.\n"
    'Верни ТОЛЬКО JSON-объект вида {{"summary_md":"…","advice":"…"}}.\n\n'
    "ДАННЫЕ:\n{context}"
)


def _nutrition_day(con, tg_id: int, day: str) -> dict | None:
    from tj.analysis import nutrition as nutr
    meals = botdb.meals_for_day(con, tg_id, day)
    if not meals:
        return None
    t = nutr.day_totals(meals)
    t["water_l"] = botdb.water_for_day(con, tg_id, day)
    t["meals"] = len(meals)
    return t


def _nutrition_block(con, tg_id: int, day: str) -> dict | None:
    """Питание за день тренировки и накануне — для разбора «Как ты подошёл»."""
    prev = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
    out = {}
    d = _nutrition_day(con, tg_id, day)
    p = _nutrition_day(con, tg_id, prev)
    if d:
        out["day"] = d
    if p:
        out["prev_day"] = p
    return out or None


def _extract_obj(text: str) -> dict | None:
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j <= i:
        return None
    try:
        obj = json.loads(text[i:j + 1])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _valid_narrative(blocks) -> bool:
    if not isinstance(blocks, list) or not (3 <= len(blocks) <= 6):
        return False
    return all(isinstance(b, dict)
               and isinstance(b.get("kind"), str)
               and isinstance(b.get("title"), str)
               and isinstance(b.get("body"), str) for b in blocks)


def _ask(instr: str) -> dict | None:
    raw = llm.deep_complete(_ROLE + "\n\n" + instr, timeout=_TIMEOUT)
    return _extract_obj(raw) if raw else None


def review_day(con, tg_id: int, day: str, sport: str | None = None,
               lang: str = "ru", db_path: str | None = None) -> dict:
    """Поденный разбор одного дня. Кроссфит без доски и без работы — пропуск
    (нечего судить, выдумывать нельзя)."""
    db_path = str(db_path or botdb.default_db_path())
    hr_max, sex = botdb.profile_hr_sex(con, tg_id)
    rep = workout_report(db_path, "sqlite", hr_max, sex, day, tg_id=tg_id)
    if not rep:
        return {"day": day, "skip": "no data"}
    payload = llm_coach.workout_payload(rep)
    if (sport or "").startswith("crossfit") and not payload.get("board") \
            and not payload.get("work"):
        return {"day": day, "skip": "crossfit без доски"}
    payload["bodyweight_kg"] = botdb.latest_weight(con, tg_id, day)
    payload["nutrition"] = _nutrition_block(con, tg_id, day)
    bundle = {"day": day, "trimp": rep.get("trimp"),
              "payload": payload, "history": rep.get("history")}
    astro = botdb.user_astro(con, tg_id)
    obj = _ask(_WORKOUT_INSTR.format(
        day=day, astro=_ASTRO_NOTE if astro else "",
        context=json.dumps(bundle, ensure_ascii=False)))
    md = ((obj or {}).get("review_md") or "").strip()
    if not md:
        return {"day": day, "error": "llm"}
    botdb.claude_review_put(con, tg_id, day, md,
                            datetime.date.today().isoformat(), lang=lang)
    botdb.llm_cache_delete(con, tg_id, "workout", day)   # Клод перекрывает Gemini
    nar = (obj or {}).get("narrative")
    if _valid_narrative(nar):
        botdb.wk_narrative_put(con, tg_id, day, "claude", nar, lang=lang)
    return {"day": day, "ok": True, "narrative": _valid_narrative(nar)}


def review_summary(con, tg_id: int, lang: str = "ru",
                   db_path: str | None = None) -> dict:
    """Общий разбор Сводки за 30 дней + совет. Перезаписывается каждый прогон."""
    db_path = str(db_path or botdb.default_db_path())
    hr_max, sex = botdb.profile_hr_sex(con, tg_id)
    today = datetime.date.today()
    data = summary_data(db_path, "sqlite", hr_max, sex, today, tg_id=tg_id)
    payload = llm_coach.summary_payload(data)
    payload["weight_kg"] = botdb.latest_weight(con, tg_id)
    from tj.analysis import nutrition as nutr
    ns = nutr.period_summary(botdb.nutrition_days(con, tg_id, days=7),
                             botdb.water_days(con, tg_id), payload["weight_kg"])
    payload["nutrition7"] = ns if ns.get("days") else None
    cutoff = (today - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    rows = [r for r in recent_workouts(db_path, "sqlite", limit=80, tg_id=tg_id)
            if r["day"] >= cutoff]
    sessions = [{"day": r["day"], "sport": r["sport"], "wod_name": r.get("wod_name"),
                 "duration_min": r.get("duration_min"), "avg_hr": r.get("avg_hr"),
                 "primary_benefit": (r.get("extra") or {}).get("primary_benefit"),
                 "readiness": r.get("readiness")} for r in rows]
    bundle = {"range_days": LOOKBACK_DAYS, "today": today.isoformat(),
              "workouts_count": len(sessions), "payload": payload,
              "sessions": sessions}
    astro = botdb.user_astro(con, tg_id)
    obj = _ask(_SUMMARY_INSTR.format(
        astro=_ASTRO_NOTE if astro else "",
        context=json.dumps(bundle, ensure_ascii=False)))
    md = ((obj or {}).get("summary_md") or "").strip()
    if not md:
        return {"summary": False, "error": "llm"}
    botdb.claude_review_put(con, tg_id, "summary", md,
                            today.isoformat(), lang=lang)
    botdb.llm_cache_delete(con, tg_id, "summary", "30d")
    advice = ((obj or {}).get("advice") or "").strip()
    if advice:
        botdb.next_advice_put(con, tg_id, "claude", advice, lang=lang)
    return {"summary": True, "advice": bool(advice)}


def run_user(con, tg_id: int, db_path: str | None = None) -> dict:
    lang = botdb.user_lang(con, tg_id)
    cutoff = (datetime.date.today()
              - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    pending = [p for p in botdb.claude_reviews_pending(con, tg_id, lang=lang)
               if p["day"] >= cutoff]
    days = [review_day(con, tg_id, p["day"], p.get("sport"), lang=lang,
                       db_path=db_path)
            for p in pending]
    return {"tg_id": tg_id, "lang": lang, "days": days,
            **review_summary(con, tg_id, lang=lang, db_path=db_path)}


def run_all(db_path=None) -> list[dict]:
    """Прогон по всем Pro. Текст пишет Claude (если включён) или Gemini —
    через deep_complete. Сбой шага — пропуск, не порча данных."""
    path = db_path or botdb.default_db_path()
    out = []
    con = botdb.connect(path)
    try:
        botdb.init_schema(con)
        for tg_id in sorted(access.load_pro()):
            try:
                out.append(run_user(con, tg_id, db_path=str(path)))
            except Exception as e:
                out.append({"tg_id": tg_id, "error": type(e).__name__})
    finally:
        con.close()
    return out
