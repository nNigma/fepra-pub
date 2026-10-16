"""Запись тренировки: сервисы поверх sqlite-соединения (без HTTP и Telegram).

Вынесено из tjbot/handlers (record_workout, edit_workout, add_result, lift_disambig,
bodyweight, self_feel). Логику переиспользуем: сборка Activity, разбор шаблона результатов
(tj.analysis.wod_results), лифты (tjbot.db.split_lifts / record_lift_results), ИИ
(tjbot.vision + access.llm_quota_consume).

Идентичность: `uid` = user_id (для старых пользователей == tg_id). id ручной тренировки —
клиентский UUID; запись идемпотентна (повторный save_result с тем же id заменяет строку).
Старые id вида `manual-{uid}-{день}-{вид}` читаются и правятся как раньше.
Даты/время: сервисы принимают `tz` и `today`, чтобы тесты были детерминированными.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from tj import i18n
from tj.analysis import standards
from tj.analysis.parse_input import detect_scaling, parse_lift_lines, parse_rpe
from tj.analysis.progression import epley_1rm
from tj.analysis.wod_results import extract_maxes, summarize_filled
from tj.models import (BOARD_SPORTS, Activity, EnduranceDetails, Scaling, Sport,
                       StrengthWodDetails, WodFormat, WodPerformed, WodPrescription)

from . import board as board_svc
from .errors import BadRequest, Forbidden, Invalid, NotFound

# семья неоднозначных лифтов -> [(discipline_id, i18n-ключ подписи)] — порядок как в боте
FAMILY_VARIANTS = {
    "snatch": [("squat_snatch", "disambig.snatch_squat"), ("power_snatch", "disambig.snatch_power")],
    "clean": [("clean_floor", "disambig.clean_floor"), ("hang_clean", "disambig.clean_hang")],
}
_VARIANT_FAMILY = {did: fam for fam, vs in FAMILY_VARIANTS.items() for did, _ in vs}

_LEGACY_ID = re.compile(r"^manual-(\d+)-\d{4}-\d{2}-\d{2}-[a-z]+$")
BW_MIN, BW_MAX = 20.0, 500.0


# --- мелочи ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _tzinfo(tz) -> ZoneInfo:
    if isinstance(tz, ZoneInfo):
        return tz
    try:
        return ZoneInfo(tz or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def today_in(tz) -> date:
    return datetime.now(_tzinfo(tz)).date()


def normalize_activity_id(uid: int, raw) -> str:
    """Клиентский UUID -> каноническая строка; либо старый `manual-{uid}-...` (только свой)."""
    s = str(raw or "").strip()
    try:
        return str(uuid.UUID(s))
    except ValueError:
        pass
    m = _LEGACY_ID.match(s)
    if m and int(m.group(1)) == int(uid):
        return s
    raise BadRequest("id тренировки: ожидается UUID", code="bad_id")


def _parse_day(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise Invalid("day: ожидается дата ГГГГ-ММ-ДД", code="bad_day")


def _parse_time(value) -> time | None:
    if value in (None, ""):
        return None
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise Invalid("start_time: ожидается ЧЧ:ММ", code="bad_time")
    return time(int(m.group(1)), int(m.group(2)))


def _num_or_none(v, name: str, lo: float, hi: float) -> float | None:
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise Invalid(f"{name}: ожидается число", code="bad_number")
    if not (lo <= f <= hi):
        raise Invalid(f"{name}: вне диапазона {lo:g}..{hi:g}", code="bad_number")
    return f


def _check_rpe(v) -> int | None:
    if v in (None, ""):
        return None
    if isinstance(v, bool) or not isinstance(v, (int, str, float)):
        raise Invalid("rpe: ожидается число 1-10", code="bad_rpe")
    try:
        n = int(float(v))
    except ValueError:
        raise Invalid("rpe: ожидается число 1-10", code="bad_rpe")
    if not 1 <= n <= 10:
        raise Invalid("rpe: ожидается число 1-10", code="bad_rpe")
    return n


def _check_scaling(v) -> Scaling | None:
    if v in (None, "", "none"):
        return None
    try:
        return Scaling(str(v).lower())
    except ValueError:
        raise Invalid("scaling: rx или scaled", code="bad_scaling")


def _extra(raw) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}


def _log(con, uid: int, action: str) -> None:
    from tjbot import db as botdb
    try:
        botdb.log_action(con, uid, action)
    except Exception:
        pass


def _fetch(con, uid: int, activity_id: str):
    return con.execute('SELECT rowid AS _rid, * FROM activities WHERE "tg_id"=? AND "activity_id"=?',
                       (int(uid), activity_id)).fetchone()


def _own_manual(con, uid: int, activity_id: str):
    """Строка ручной тренировки пользователя. Нет/чужая -> NotFound; часы -> Forbidden."""
    row = _fetch(con, uid, activity_id)
    if not row:
        raise NotFound("тренировка не найдена")
    if row["source"] != "manual":
        raise Forbidden("правятся только ручные тренировки")
    return row


# --- сборка Activity -------------------------------------------------------------------

def _score_summary(mdata: dict, text: str) -> str | None:
    """Компактный счёт для списка: времена и AMRAP-круги; иначе первая непустая строка."""
    parts = [f"{s // 60}:{s % 60:02d}" for s in (mdata or {}).get("times_sec", [])]
    for r, x in ((mdata or {}).get("amrap") or {}).get("rounds", []):
        parts.append(f"{r}+{x}" if x else str(r))
    if parts:
        return " · ".join(parts)
    return (text or "").strip()[:200] or None


def build_activity(uid: int, activity_id: str, day: date, sport: Sport, tz, *,
                   board_text=None, board_source="own", wod_format=None,
                   score=None, rpe=None, scaling=None, start_time: time | None = None,
                   duration_min=None, distance_km=None) -> Activity:
    """Ручная активность. Кроссфит/ТА/Hyrox — с доской (StrengthWodDetails), остальное —
    выносливость (дистанция/длительность). Время старта храним только если его назвал атлет:
    по нему часы сливаются по пересечению по времени."""
    zi = _tzinfo(tz)
    start = datetime.combine(day, start_time or time(12, 0), tzinfo=zi)
    act = Activity(source="manual", sport=sport, start=start, activity_id=activity_id,
                   duration_min=duration_min)
    act.extra = {}
    if start_time is not None:
        act.extra["start_ts"] = start.isoformat()
    if sport in BOARD_SPORTS:
        presc = WodPrescription(raw_text=board_text)
        if wod_format:
            try:
                presc.format = WodFormat(wod_format)
            except ValueError:
                pass
        act.strength = StrengthWodDetails(
            presc, WodPerformed(scaling=scaling, score=score, rpe=rpe))
        act.extra.update({"board_text": board_text, "board_source": board_source})
    else:
        if distance_km:
            pace = round(duration_min * 60 / distance_km, 1) if duration_min else None
            act.endurance = EnduranceDetails(distance_km=distance_km, avg_pace_s_per_km=pace)
        if rpe:
            act.extra["rpe"] = rpe
        if score:
            act.extra["result_text"] = score
    return act


# --- лифты -------------------------------------------------------------------------------

def variants_for(family: str, lang: str = "ru") -> list[dict]:
    return [{"id": did, "label": i18n.t(key, lang)} for did, key in FAMILY_VARIANTS[family]]


def _ambiguous_out(items, lang: str = "ru") -> list[dict]:
    """Неоднозначные лифты -> вопросы клиенту с вариантами ответа."""
    out = []
    for it in items or []:
        out.append({"movement": it.get("movement"), "family": it["family"],
                    "weight": it["weight"], "reps": it["reps"],
                    "variants": variants_for(it["family"], lang)})
    return out


def _apply_resolutions(results: list, ambiguous: list, resolutions: list):
    """Ранее выбранные варианты (extra.lift_resolutions) автоматически закрывают
    совпавшие вопросы — повторный PUT не переспрашивает."""
    if not resolutions:
        return results, ambiguous
    discs = standards.disciplines()
    left = []
    for it in ambiguous:
        hit = next((r for r in resolutions
                    if (r.get("movement") or "").lower() == (it.get("movement") or "").lower()
                    and float(r["weight"]) == float(it["weight"]) and int(r["reps"]) == int(it["reps"])
                    and r.get("variant") in discs), None)
        if hit:
            d = hit["variant"]
            results.append({"discipline": d, "name": discs[d]["name_ru"], "weight": it["weight"],
                            "reps": it["reps"], "est_1rm": epley_1rm(it["weight"], it["reps"])})
        else:
            left.append(it)
    return results, left


def _record_maxes(con, uid: int, parsed, day: str, activity_id: str, resolutions=None, *,
                  clear: bool = True):
    """[{movement, weight_kg, reps}] -> (results, ambiguous); результаты пишутся в discipline_results
    (source=auto, дедуп по activity_id). clear=False не трогает уже записанные, если новых нет."""
    from tjbot import db as botdb
    results, ambiguous = botdb.split_lifts(con, parsed)
    results, ambiguous = _apply_resolutions(results, ambiguous, resolutions or [])
    if results or clear:
        botdb.record_lift_results(con, uid, results, day, activity_id)
    return results, ambiguous


def _llm_lifts(con, uid: int, text: str):
    """Текст результата -> (parsed, skipped_quota). ИИ (parse_lifts, квота) с фолбэком на
    построчный разбор — как «правка максов» в боте, только без тупика при лимите."""
    from tjbot import access, vision
    if vision.has_vision():
        if access.llm_quota_consume(uid, con):
            parsed = vision.parse_lifts(text)
            if parsed:
                return parsed, False
        else:
            return parse_lift_lines(text), True
    return parse_lift_lines(text), False


def _confirm_raw(con, uid: int, aid: str, row, maxes, text):
    skipped = False
    if maxes is None:
        if not (text or "").strip():
            raise Invalid("нужны maxes или text", code="bad_maxes")
        maxes, skipped = _llm_lifts(con, uid, text)
    if not isinstance(maxes, list):
        raise Invalid("maxes: ожидается список", code="bad_maxes")
    for m in maxes:
        if not isinstance(m, dict) or not str(m.get("movement") or "").strip():
            raise Invalid("maxes: у каждого нужен movement", code="bad_maxes")
    extra = _extra(row["extra"])
    results, ambiguous = _record_maxes(con, uid, maxes, row["day"], aid,
                                       extra.get("lift_resolutions"), clear=False)
    return results, ambiguous, skipped


def confirm_maxes(con, uid: int, activity_id: str, maxes=None, *, text: str | None = None,
                  lang: str = "ru") -> dict:
    """Подтверждение/ввод максов тренировки: список [{movement, weight_kg, reps}] или текст
    построчно («Взятие 100x3»). Однозначные лифты пишутся в уровни, неоднозначные
    возвращаются вопросами `ambiguous` (решаются resolve_lift). Уже записанные максы этой
    тренировки не стираются. -> {credited, ambiguous, skipped_quota}"""
    aid = normalize_activity_id(uid, activity_id)
    row = _own_manual(con, uid, aid)
    results, ambiguous, skipped = _confirm_raw(con, uid, aid, row, maxes, text)
    return {"credited": results, "ambiguous": _ambiguous_out(ambiguous, lang),
            "skipped_quota": skipped}


def resolve_lift(con, uid: int, activity_id: str, movement: str, variant: str,
                 weight, reps, *, lang: str = "ru") -> dict:
    """Ответ на вопрос «рывок/взятие — какой?»: пишем выбранную дисциплину (source=auto)
    и запоминаем выбор в extra тренировки (повторное сохранение не переспросит)."""
    from tjbot import db as botdb
    aid = normalize_activity_id(uid, activity_id)
    row = _own_manual(con, uid, aid)
    if variant not in _VARIANT_FAMILY:
        raise Invalid("variant: одно из " + ", ".join(sorted(_VARIANT_FAMILY)), code="bad_variant")
    w = _num_or_none(weight, "weight", 0.1, 1000)
    r = _num_or_none(reps if reps is not None else 1, "reps", 1, 1000)
    if w is None or r is None:
        raise Invalid("weight и reps обязательны", code="bad_number")
    r = int(r)
    est = epley_1rm(w, r)
    dup = con.execute(
        'SELECT 1 FROM discipline_results WHERE "tg_id"=? AND "activity_id"=? AND "discipline"=? '
        'AND "value"=? AND "reps"=? AND "source"=\'auto\'', (int(uid), aid, variant, w, r)).fetchone()
    if not dup:
        botdb.add_result(con, tg_id=int(uid), discipline=variant, value=w, reps=r, est_1rm=est,
                         source="auto", day=row["day"], activity_id=aid)
    extra = _extra(row["extra"])
    res = [x for x in extra.get("lift_resolutions", [])
           if not ((x.get("movement") or "").lower() == (movement or "").lower()
                   and float(x["weight"]) == w and int(x["reps"]) == r)]
    res.append({"movement": movement, "weight": w, "reps": r, "variant": variant})
    extra["lift_resolutions"] = res
    con.execute('UPDATE activities SET "extra"=? WHERE "tg_id"=? AND "activity_id"=?',
                (json.dumps(extra, ensure_ascii=False), int(uid), aid))
    con.commit()
    name = standards.discipline_name(standards.disciplines()[variant], lang)
    return {"discipline": variant, "name": name, "weight": w, "reps": r, "est_1rm": est}


# --- сохранение результата ------------------------------------------------------------------

def _resolve_board(con, uid: int, day: date, sport: Sport, payload: dict, existing_extra: dict | None):
    """-> (board_text, board_source, blocks, verified, wod_format). Правила доски:
    source='gym' — текст и блоки только из программы зала на день (клиентский текст
    игнорируется); source='own' — свой текст/блоки. Зальную запись нельзя превратить в свою."""
    b = payload.get("board") or {}
    if not isinstance(b, dict):
        raise Invalid("board: ожидается объект", code="bad_board")
    src = b.get("source") or "own"
    if src not in ("own", "gym"):
        raise Invalid("board.source: own или gym", code="bad_board")
    old = existing_extra or {}
    if old.get("board_source") == "gym":
        if src == "own" and (b.get("text") or "").strip() and \
                (b.get("text") or "").strip() != (old.get("board_text") or "").strip():
            raise Forbidden("доска из зала правится только тренером")
        src = "gym"
    fmt = b.get("format")
    if src == "gym":
        gname = b.get("gym") if isinstance(b.get("gym"), str) and b.get("gym").strip() else None
        prog = board_svc.gym_program(con, uid, day.isoformat(), gname)   # зал, выбранный при записи
        if prog:
            return prog["board_text"], "gym", prog["blocks"], prog["blocks_verified"], fmt
        if old.get("board_source") == "gym" and old.get("board_text"):
            return old["board_text"], "gym", old.get("result_blocks") or [], \
                bool(old.get("blocks_verified")), fmt
        raise Invalid("на эту дату нет программы зала", code="no_gym_program")
    text = (b.get("text") or "").strip() or None
    blocks = b.get("blocks")
    verified = bool(b.get("blocks_verified"))
    if blocks:
        blocks = board_svc.check_blocks(blocks)
    elif text:
        blocks = board_svc.build(con, uid, text, verify=False, use_llm=False)["blocks"]
        verified = False
    else:
        blocks = []
    return text, "own", blocks, verified, fmt


def save_result(con, uid: int, activity_id: str, payload: dict, *, tz="UTC",
                lang: str = "ru") -> dict:
    """Сохранить тренировку: доска + фактический результат + scaling + RPE + вес тела.

    payload: {day, sport, board?: {text, source: own|gym, format?, blocks?, blocks_verified?},
              form_result?: {ключ поля: значение} | "свободный текст", rpe?, scaling?,
              bodyweight?, start_time? "ЧЧ:ММ", duration_min?, distance_km?}
    Идемпотентно по (uid, activity_id). Максы заполненной формы сразу идут в уровни
    (split_lifts -> record_lift_results); неоднозначные — в `ambiguous` (resolve_lift).
    Свободный текст без блоков: максы предлагаются в `proposed_maxes` (ИИ, квота) и
    записываются только через confirm_maxes.
    """
    from tjbot import db as botdb
    from tjbot.activity import RESULT_ADDED, WORKOUT_RECORDED
    aid = normalize_activity_id(uid, activity_id)
    if not isinstance(payload, dict):
        raise Invalid("тело запроса: ожидается объект", code="bad_payload")
    day = _parse_day(payload.get("day"))
    try:
        sport = Sport(str(payload.get("sport") or ""))
    except ValueError:
        raise Invalid("sport: " + ", ".join(s.value for s in Sport), code="bad_sport")
    existing = _fetch(con, uid, aid)
    if existing and existing["source"] != "manual":
        raise Forbidden("нельзя перезаписать тренировку с часов")
    old_extra = _extra(existing["extra"]) if existing else {}

    rpe = _check_rpe(payload.get("rpe"))
    scaling = _check_scaling(payload.get("scaling")) if "scaling" in payload else None
    start_time = _parse_time(payload.get("start_time"))
    duration = _num_or_none(payload.get("duration_min"), "duration_min", 1, 24 * 60)
    distance = _num_or_none(payload.get("distance_km"), "distance_km", 0.01, 5000)
    bw = _num_or_none(payload.get("bodyweight"), "bodyweight", BW_MIN, BW_MAX)

    board_text = board_source = wod_format = None
    blocks: list = []
    verified = False
    if sport in BOARD_SPORTS:
        board_text, board_source, blocks, verified, wod_format = _resolve_board(
            con, uid, day, sport, payload, old_extra)

    fr = payload.get("form_result")
    values = None
    if isinstance(fr, dict):
        if not blocks:
            raise Invalid("form_result без доски: нет блоков для формы", code="no_blocks")
        form = board_svc.result_form(blocks)
        text = board_svc.fill_template(form, fr)
        values = {k: v for k, v in fr.items() if v not in (None, "")}
    else:
        text = str(fr).strip() if fr not in (None, "") else str(payload.get("result_text") or "").strip()

    if rpe is None:
        rpe = parse_rpe(text)
    if scaling is None and "scaling" not in payload:
        scaling = detect_scaling(text)

    mdata, metcon_lines = ({}, [])
    if sport in BOARD_SPORTS and blocks and text:
        mdata, metcon_lines = summarize_filled(blocks, text)
    score = _score_summary(mdata, text) if sport in BOARD_SPORTS else (text or None)

    act = build_activity(uid, aid, day, sport, tz, board_text=board_text,
                         board_source=board_source or "own", wod_format=wod_format,
                         score=score, rpe=rpe, scaling=scaling, start_time=start_time,
                         duration_min=duration, distance_km=distance)
    if sport in BOARD_SPORTS:
        act.extra["metcon"] = mdata
        act.extra["result_blocks"] = blocks
        if verified:
            act.extra["blocks_verified"] = "claude"
        if text:
            act.extra["result_text"] = text
        if values is not None:
            act.extra["form_result"] = values
    if old_extra.get("lift_resolutions"):
        act.extra["lift_resolutions"] = old_extra["lift_resolutions"]
    act.extra["created_at"] = old_extra.get("created_at") or _now_iso()
    act.extra["updated_at"] = _now_iso()
    botdb.insert_activity(con, act, uid)

    results: list = []
    ambiguous: list = []
    proposed = None
    skipped = False
    day_s = day.isoformat()
    if sport in BOARD_SPORTS:
        if blocks:
            maxes = extract_maxes(blocks, text) if text else []
            results, ambiguous = _record_maxes(con, uid, maxes, day_s, aid,
                                               act.extra.get("lift_resolutions"))
        elif text and any(c.isdigit() for c in text):
            parsed, skipped = _llm_lifts(con, uid, text)
            if parsed:
                preview, amb = botdb.split_lifts(con, parsed)
                proposed = {"maxes": parsed, "credited": preview,
                            "ambiguous": _ambiguous_out(amb, lang)}
    if bw is not None:
        botdb.set_bodyweight(con, day_s, bw, uid)
    if not existing:
        _log(con, uid, RESULT_ADDED if board_source == "gym" else WORKOUT_RECORDED)
    return {
        "activity_id": aid, "created": existing is None, "day": day_s, "sport": sport.value,
        "score": score, "rpe": rpe, "scaling": scaling.value if scaling else None,
        "board_source": board_source, "metcon_lines": metcon_lines,
        "credited": results, "ambiguous": _ambiguous_out(ambiguous, lang),
        "proposed_maxes": proposed, "lifts_skipped_quota": skipped,
        "bodyweight": bw,
    }


# --- чтение ------------------------------------------------------------------------------

def _shape(row) -> dict:
    extra = _extra(row["extra"])
    return {
        "id": row["activity_id"], "day": row["day"], "sport": row["sport"],
        "source": row["source"], "wod_format": row["wod_format"],
        "score": row["perf_score"], "scaling": row["perf_scaling"],
        "rpe": row["perf_rpe"] if row["perf_rpe"] is not None else extra.get("rpe"),
        "duration_min": row["duration_min"], "distance_km": row["distance_km"],
        "start_time": ((extra.get("start_ts") or "")[11:16] or None),
        "board_source": extra.get("board_source") if row["sport"] in
        {s.value for s in BOARD_SPORTS} else None,
        "updated_at": extra.get("updated_at"),
    }


def recent(con, uid: int, limit: int = 10) -> list[dict]:
    """Последние ручные тренировки (новые сверху; в один день — по порядку записи)."""
    limit = max(1, min(int(limit), 100))
    rows = con.execute(
        'SELECT rowid AS _rid, * FROM activities WHERE "source"=\'manual\' AND "tg_id"=? '
        'ORDER BY "day" DESC, rowid DESC LIMIT ?', (int(uid), limit)).fetchall()
    return [_shape(r) for r in rows]


def get(con, uid: int, activity_id: str, *, lang: str = "ru") -> dict:
    """Тренировка целиком: поля, доска, форма и значения, метконы, зачтённые максы, вес тела."""
    aid = normalize_activity_id(uid, activity_id)
    row = _fetch(con, uid, aid)
    if not row:
        raise NotFound("тренировка не найдена")
    extra = _extra(row["extra"])
    d = _shape(row)
    manual = row["source"] == "manual"
    blocks = extra.get("result_blocks") or []
    d.update({
        "board_text": extra.get("board_text"),
        "blocks": blocks,
        "form": board_svc.result_form(blocks) if blocks else None,
        "form_values": extra.get("form_result"),
        "result_text": extra.get("result_text"),
        "metcon": extra.get("metcon"),
        "editable": manual,
        "board_editable": manual and (extra.get("board_source") or "own") == "own"
        and row["sport"] in {s.value for s in BOARD_SPORTS},
    })
    d["maxes"] = [dict(r) for r in con.execute(
        'SELECT "discipline","value","reps","est_1rm","source" FROM discipline_results '
        'WHERE "tg_id"=? AND "activity_id"=? ORDER BY rowid', (int(uid), aid))]
    bw = con.execute('SELECT "weight_kg" FROM daily WHERE "tg_id"=? AND "day"=?',
                     (int(uid), row["day"])).fetchone()
    d["bodyweight"] = bw["weight_kg"] if bw else None
    return d


# --- правка -----------------------------------------------------------------------------

def _recompute_result(con, uid: int, aid: str, row, text: str, blocks: list, values=None):
    """Как save_score в боте: счёт, метконы и максы из заполненного текста."""
    from tjbot import db as botdb
    extra = _extra(row["extra"])
    mdata, lines = summarize_filled(blocks, text) if blocks else ({}, [])
    extra["metcon"] = mdata
    extra["result_text"] = text
    if values is not None:
        extra["form_result"] = values
    extra["updated_at"] = _now_iso()
    score = _score_summary(mdata, text)
    con.execute('UPDATE activities SET "extra"=?, "perf_score"=? WHERE "tg_id"=? AND "activity_id"=?',
                (json.dumps(extra, ensure_ascii=False), score, int(uid), aid))
    con.commit()
    results, ambiguous = [], []
    if blocks:
        maxes = extract_maxes(blocks, text)
        results, ambiguous = _record_maxes(con, uid, maxes, row["day"], aid,
                                           extra.get("lift_resolutions"), clear=False)
    return lines, results, ambiguous


def update(con, uid: int, activity_id: str, changes: dict, *, lang: str = "ru") -> dict:
    """Частичная правка ручной тренировки (как «Редактировать» в боте).

    changes (любые из): rpe, scaling, form_result (dict|текст) — пересчёт метконов и максов,
    board {text} — ТОЛЬКО если board_source == 'own' (иначе Forbidden), maxes [{...}] | maxes_text,
    bodyweight. Возвращает {workout, metcon_lines, credited, ambiguous}.
    """
    from tjbot import access, vision
    from tjbot import db as botdb
    from tjbot.activity import WORKOUT_EDITED
    aid = normalize_activity_id(uid, activity_id)
    row = _own_manual(con, uid, aid)
    if not isinstance(changes, dict) or not changes:
        raise Invalid("нечего менять", code="empty_patch")
    extra = _extra(row["extra"])
    is_board = row["sport"] in {s.value for s in BOARD_SPORTS}
    src = extra.get("board_source") or "own"

    if "board" in changes:
        if not is_board or src != "own":
            raise Forbidden("доску можно править только у своей тренировки")
        text = str((changes["board"] or {}).get("text") or "").strip()
        if not text:
            raise Invalid("board.text пуст", code="bad_board")
        allow = vision.has_vision() and access.llm_quota_consume(uid, con)
        draft = vision.parse_text(text, use_llm=allow)
        raw = draft.get("raw_text") or text
        botdb.set_activity_board(con, aid, int(uid), raw_text=raw, fmt=draft.get("format"))
        row = _fetch(con, uid, aid)
        extra = _extra(row["extra"])
        extra["result_blocks"] = board_svc.build(con, uid, raw, verify=False,
                                                 use_llm=False)["blocks"]
        extra.pop("blocks_verified", None)
        extra.pop("form_result", None)
        con.execute('UPDATE activities SET "extra"=? WHERE "tg_id"=? AND "activity_id"=?',
                    (json.dumps(extra, ensure_ascii=False), int(uid), aid))
        con.commit()
        row = _fetch(con, uid, aid)

    if "rpe" in changes:
        rpe = _check_rpe(changes["rpe"])
        if is_board:
            botdb.update_activity(con, aid, int(uid), rpe=rpe)
        else:
            e = _extra(row["extra"])
            if rpe is None:
                e.pop("rpe", None)
            else:
                e["rpe"] = rpe
            con.execute('UPDATE activities SET "extra"=? WHERE "tg_id"=? AND "activity_id"=?',
                        (json.dumps(e, ensure_ascii=False), int(uid), aid))
            con.commit()
    if "scaling" in changes:
        sc = _check_scaling(changes["scaling"])
        botdb.update_activity(con, aid, int(uid), scaling=sc.value if sc else None)

    lines: list = []
    credited: list = []
    ambiguous: list = []
    if "form_result" in changes or "board" in changes:
        row = _fetch(con, uid, aid)
        extra = _extra(row["extra"])
        blocks = extra.get("result_blocks") or []
        fr = changes.get("form_result", extra.get("form_result") if isinstance(
            extra.get("form_result"), dict) else extra.get("result_text"))
        values = None
        if isinstance(fr, dict):
            if not blocks:
                raise Invalid("нет блоков для формы", code="no_blocks")
            text = board_svc.fill_template(board_svc.result_form(blocks), fr)
            values = {k: v for k, v in fr.items() if v not in (None, "")}
        else:
            text = str(fr or "").strip()
        if text or "form_result" in changes:
            lines, credited, ambiguous = _recompute_result(con, uid, aid, row, text, blocks, values)

    if "maxes" in changes or "maxes_text" in changes:
        row = _fetch(con, uid, aid)
        res_, amb_, _sk = _confirm_raw(con, uid, aid, row, changes.get("maxes"),
                                       changes.get("maxes_text"))
        credited += res_
        ambiguous += amb_
    if "bodyweight" in changes:
        kg = _num_or_none(changes["bodyweight"], "bodyweight", BW_MIN, BW_MAX)
        if kg is None:
            raise Invalid("bodyweight обязателен", code="bad_number")
        botdb.set_bodyweight(con, row["day"], kg, int(uid))

    row = _fetch(con, uid, aid)
    e = _extra(row["extra"])
    e["updated_at"] = _now_iso()
    con.execute('UPDATE activities SET "extra"=? WHERE "tg_id"=? AND "activity_id"=?',
                (json.dumps(e, ensure_ascii=False), int(uid), aid))
    con.commit()
    botdb.mark_data_changed(con)
    _log(con, uid, WORKOUT_EDITED)
    return {"workout": get(con, uid, aid, lang=lang), "metcon_lines": lines,
            "credited": credited, "ambiguous": _ambiguous_out(ambiguous, lang)}


# --- удаление / восстановление ------------------------------------------------------------

def delete(con, uid: int, activity_id: str) -> dict:
    """Мягкое удаление ручной тренировки: строка и её авто-результаты (ПМ из неё) уходят
    в activity_trash с меткой deleted_at, из отчётов исчезают. Повторное удаление — NotFound."""
    from tjbot import db as botdb
    aid = normalize_activity_id(uid, activity_id)
    row = _own_manual(con, uid, aid)
    cols = [c[1] for c in con.execute('PRAGMA table_info("activities")')]
    row_json = json.dumps({c: row[c] for c in cols}, ensure_ascii=False)
    res_cols = [c[1] for c in con.execute('PRAGMA table_info("discipline_results")')
                if c[1] != "id"]
    res = [{c: r[c] for c in res_cols} for r in con.execute(
        'SELECT * FROM discipline_results WHERE "tg_id"=? AND "activity_id"=? AND "source"=\'auto\'',
        (int(uid), aid))]
    now = _now_iso()
    con.execute('INSERT OR REPLACE INTO activity_trash ("uid","activity_id","row_json","results_json",'
                '"deleted_at") VALUES (?,?,?,?,?)',
                (int(uid), aid, row_json, json.dumps(res, ensure_ascii=False), now))
    con.execute('DELETE FROM discipline_results WHERE "tg_id"=? AND "activity_id"=? AND "source"=\'auto\'',
                (int(uid), aid))
    con.execute('DELETE FROM activities WHERE "tg_id"=? AND "activity_id"=?', (int(uid), aid))
    con.commit()
    botdb.mark_data_changed(con)
    return {"id": aid, "deleted_at": now}


def restore(con, uid: int, activity_id: str) -> dict:
    """Вернуть удалённую тренировку вместе с её максами. Нет в корзине -> NotFound;
    id уже занят живой записью -> BadRequest."""
    from tjbot import db as botdb
    aid = normalize_activity_id(uid, activity_id)
    t = con.execute('SELECT * FROM activity_trash WHERE "uid"=? AND "activity_id"=?',
                    (int(uid), aid)).fetchone()
    if not t:
        raise NotFound("в корзине нет такой тренировки")
    if _fetch(con, uid, aid):
        raise BadRequest("тренировка с таким id уже существует", code="exists")
    data = json.loads(t["row_json"])
    cols = [c[1] for c in con.execute('PRAGMA table_info("activities")')]
    data = {k: v for k, v in data.items() if k in cols}
    names = ",".join(f'"{k}"' for k in data)
    con.execute(f"INSERT INTO activities ({names}) VALUES ({','.join('?' * len(data))})",
                list(data.values()))
    for r in json.loads(t["results_json"] or "[]"):
        botdb.add_result(con, tg_id=int(uid), discipline=r["discipline"], value=r["value"],
                         reps=r.get("reps"), est_1rm=r.get("est_1rm"), scaling=r.get("scaling"),
                         source=r.get("source") or "auto", day=r.get("day"), activity_id=aid,
                         created_at=r.get("created_at"))
    con.execute('DELETE FROM activity_trash WHERE "uid"=? AND "activity_id"=?', (int(uid), aid))
    con.commit()
    botdb.mark_data_changed(con)
    return get(con, uid, aid)


def trash(con, uid: int, limit: int = 20) -> list[dict]:
    """Недавно удалённые ручные тренировки (для «отменить удаление»)."""
    out = []
    for t in con.execute('SELECT * FROM activity_trash WHERE "uid"=? ORDER BY "deleted_at" DESC LIMIT ?',
                         (int(uid), max(1, min(int(limit), 100)))):
        r = json.loads(t["row_json"])
        out.append({"id": t["activity_id"], "day": r.get("day"), "sport": r.get("sport"),
                    "score": r.get("perf_score"), "deleted_at": t["deleted_at"]})
    return out


# --- вес тела, самочувствие ------------------------------------------------------------------

def set_bodyweight(con, uid: int, kg, day=None, *, tz="UTC", today: date | None = None) -> dict:
    """Вес тела за день (по умолчанию сегодня в tz пользователя) -> daily.weight_kg."""
    from tjbot import db as botdb
    t = today or today_in(tz)
    d = _parse_day(day) if day else t
    if d > t + timedelta(days=1):
        raise Invalid("day: дата в будущем", code="bad_day")
    w = _num_or_none(kg, "kg", BW_MIN, BW_MAX)
    if w is None:
        raise Invalid("kg обязателен", code="bad_number")
    botdb.set_bodyweight(con, d.isoformat(), w, int(uid))
    return {"day": d.isoformat(), "kg": w}


def set_feel(con, uid: int, score, *, tz="UTC", today: date | None = None) -> dict:
    """Самочувствие 1-10 за СЕГОДНЯ по tz пользователя (не по дате сервера)."""
    from tjbot import db as botdb
    if isinstance(score, bool) or not isinstance(score, (int, str)):
        raise Invalid("score: целое 1-10", code="bad_score")
    try:
        n = int(score)
    except ValueError:
        raise Invalid("score: целое 1-10", code="bad_score")
    if not 1 <= n <= 10:
        raise Invalid("score: целое 1-10", code="bad_score")
    d = today or today_in(tz)
    botdb.set_self_feel(con, d.isoformat(), n, int(uid))
    return {"day": d.isoformat(), "score": n}
