"""Авторазборы через LLM (крон на сервере).

Порт логики скилла fepra-claude-review в автономный режим: по каждому
Pro-атлету — поденные разборы новых тренировок + общий разбор Сводки за 30 дней
+ совет на следующую тренировку. Показ и так за Pro-гейтом, поэтому и генерим
только Pro. Текст: agent/claude по FEPRA_LLM_ENGINE, фолбэк Gemini (llm.text_complete);
сбой любого шага — пропуск этого шага, не стоп прогона.

Запуск на сервере: server_review.py ПОСЛЕ server_sync.py (данные уже свежие).
"""
from __future__ import annotations

import datetime
import json

from tj import llm
from tj.models import BOARD_SPORT_VALUES
from tj.analysis import llm_coach
from tj.analysis.workouts import workout_report

from . import access
from . import db as botdb
from . import llm_gen
from . import tg_notify

LOOKBACK_DAYS = 2             # окно догона: прогон раз в сутки разбирает вчера,
                              # а если сутки пропустили — заодно позавчера.
                              # Текущий день не трогаем: он ещё не прожит
_TIMEOUT = 300.0              # разбор с большим контекстом думает дольше vision

_ROLE = (
    "Ты — Месье Клод, тренер-аналитик FePra (кроссфит и выносливость). "
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


def _ask(instr: str) -> tuple[dict | None, str | None]:
    """Поденный разбор: agent/claude по FEPRA_LLM_ENGINE, затем Gemini."""
    raw, engine = llm.text_complete(_ROLE + "\n\n" + instr, timeout=_TIMEOUT,
                                    max_output_tokens=2600)
    if not raw:
        return None, None
    obj = _extract_obj(raw)
    return (obj, engine) if obj else (None, engine)


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
    if (sport or "") in BOARD_SPORT_VALUES and not payload.get("board") \
            and not payload.get("work"):
        return {"day": day, "skip": f"{sport} без доски"}
    payload["bodyweight_kg"] = botdb.latest_weight(con, tg_id, day)
    payload["nutrition"] = _nutrition_block(con, tg_id, day)
    bundle = {"day": day, "trimp": rep.get("trimp"),
              "payload": payload, "history": rep.get("history")}
    astro = botdb.user_astro(con, tg_id)
    obj, engine = _ask(_WORKOUT_INSTR.format(
        day=day, astro=_ASTRO_NOTE if astro else "",
        context=json.dumps(bundle, ensure_ascii=False)))
    md = ((obj or {}).get("review_md") or "").strip()
    if not md:
        return {"day": day, "error": "llm"}
    botdb.claude_review_put(con, tg_id, day, md,
                            datetime.date.today().isoformat(), lang=lang)
    botdb.llm_cache_delete(con, tg_id, "workout", day)   # глубокий разбор перекрывает Gemini
    nar = (obj or {}).get("narrative")
    if _valid_narrative(nar):
        botdb.wk_narrative_put(con, tg_id, day, engine or "claude", nar, lang=lang)
    return {"day": day, "ok": True, "narrative": _valid_narrative(nar)}


def run_user(con, tg_id: int, db_path: str | None = None) -> dict:
    lang = botdb.user_lang(con, tg_id)
    db_path = str(db_path or botdb.default_db_path())
    today = datetime.date.today()
    cutoff = (today - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    last = (today - datetime.timedelta(days=1)).isoformat()
    pending = [p for p in botdb.claude_reviews_pending(con, tg_id, lang=lang)
               if cutoff <= p["day"] <= last]
    days = [review_day(con, tg_id, p["day"], p.get("sport"), lang=lang,
                       db_path=db_path)
            for p in pending]
    sweep_errs = llm_gen.sweep(con, db_path, tg_id, lang, refresh_stale=True,
                               kinds={"summary", "nutr_day", "nutr_week", "competitions"}) or []
    summary_ok = not any(e.get("kind") == "summary" for e in sweep_errs)
    out = {"tg_id": tg_id, "lang": lang, "days": days, "summary": summary_ok}
    if sweep_errs:
        out["sweep_errors"] = sweep_errs
    return out


def _bot_token() -> str | None:
    return tg_notify.bot_token()


def _tg_send(token: str, chat_id: int, text: str) -> None:
    tg_notify.send(token, chat_id, text)


def _errors(results: list[dict]) -> list[str]:
    out = []
    for r in results:
        if r.get("error"):
            out.append(f"{r.get('tg_id', '-')}: {r['error']}")
        for d in r.get("days") or []:
            if d.get("error"):
                out.append(f"{r.get('tg_id', '-')} {d.get('day', '-')}: {d['error']}")
        for e in r.get("sweep_errors") or []:
            out.append(f"{r.get('tg_id', '-')} sweep {e.get('kind')}/{e.get('ref')}: "
                       f"{e.get('error')}")
    return out


def notify_admins(results: list[dict]) -> bool:
    """Ошибки прогона — сообщением админам в TG (падение видно не только в логе).
    Сбой самой отправки глотается: уведомление не должно ронять крон."""
    errs = _errors(results)
    if not errs:
        return False
    token = _bot_token()
    if not token:
        return False
    text = "⚠️ FePra авторазбор: ошибки\n" + "\n".join(errs[:20])
    for admin_id in sorted(access.load_admins()):
        try:
            _tg_send(token, admin_id, text)
        except OSError:
            pass
    return True


def _notify_ready(con, tg_id: int, res: dict) -> None:
    """«Разбор готов» пользователю: баннер + push (+ Telegram как запас, пока жив бот).
    Только если реально появились новые поденные разборы; сбой не ломает крон."""
    n = sum(1 for d in res.get("days") or [] if d.get("ok"))
    if not n:
        return
    try:
        from tj.services import push
        push.notify_user(con, tg_id, "review_ready",
                         "Разбор от Месье Клод готов" if n == 1 else f"Разборы от Месье Клод готовы: {n}",
                         title="Разбор готов", url="/app/#/reviews", tg=True, dedupe=False)
    except Exception as e:  # noqa: BLE001
        print(f"[review] user notify failed: {type(e).__name__}", flush=True)


def run_all(db_path=None) -> list[dict]:
    """Прогон по всем Pro. Нет ни agent/claude, ни Gemini — отказ без порчи данных."""
    if not llm.has_text_llm():
        return [{"error": "LLM недоступен (нет agent/claude/gemini)"}]
    path = db_path or botdb.default_db_path()
    out = []
    con = botdb.connect(path)
    try:
        botdb.init_schema(con)
        for tg_id in sorted(access.load_pro()):
            try:
                res = run_user(con, tg_id, db_path=str(path))
                out.append(res)
                _notify_ready(con, tg_id, res)
            except Exception as e:
                out.append({"tg_id": tg_id, "error": type(e).__name__})
    finally:
        con.close()
    return out
