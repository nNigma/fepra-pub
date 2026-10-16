"""Питание: запись приёма пищи по фото или тексту, правка, удаление, вода.

Поверх tjbot.vision (parse_meal / parse_meal_text: Claude opus -> фолбэк Gemini) и tjbot.db.
Поток как в боте (handlers/meal.py), но без состояния на сервере:
  parse()  фото (upload_id) или текст -> черновик {foods, totals, quality...} + накопленные
           уточнения `notes` (клиент присылает их обратно при следующем уточнении);
  save()   подтверждённый черновик -> строка meals (фото хранится как meals.photo_path,
           не Telegram file_id); повторная запись с тем же uuid ничего не дублирует;
  replace() правка = delete+add одной транзакцией с тем же id (идемпотентно);
  parse_saved() перепарс сохранённого приёма по СОХРАНЁННОМУ файлу (или тексту-описанию).
Квота ИИ (access.llm_quota_consume, админ без лимита) списывается на каждый вызов ИИ:
в боте уточнения бесплатны, но в API это позволило бы обойти квоту, поэтому платные все.
Функции синхронные и подходят для jobs; сегодняшний день считается в tz пользователя.
"""
from __future__ import annotations

import json
import sqlite3
import uuid as uuidlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from tj.analysis import nutrition as nutr

from .errors import BadRequest, Invalid, NotFound

MAX_TEXT = 600
MAX_NOTES = 8
MAX_WATER_DELTA_ML = 5000


# --- время ------------------------------------------------------------------------

def _tzinfo(tz) -> ZoneInfo:
    if isinstance(tz, ZoneInfo):
        return tz
    try:
        return ZoneInfo(tz or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def today_in(tz, now: datetime | None = None) -> date:
    z = _tzinfo(tz)
    return (now.astimezone(z) if now else datetime.now(z)).date()


def meal_ts(day: str, tz="UTC", now: datetime | None = None) -> str:
    """Время приёма: сегодня (по tz) — сейчас, другой день — полдень (как _meal_ts бота)."""
    z = _tzinfo(tz)
    n = now.astimezone(z) if now else datetime.now(z)
    if day == n.date().isoformat():
        return n.isoformat(timespec="seconds")
    return f"{day}T12:00:00"


def check_day(day: str | None, tz="UTC", now: datetime | None = None) -> str:
    """ISO-дата (пусто -> сегодня); дальше завтрашнего дня нельзя."""
    today = today_in(tz, now)
    if day in (None, ""):
        return today.isoformat()
    try:
        d = date.fromisoformat(str(day))
    except ValueError:
        raise Invalid("day: ожидается дата ГГГГ-ММ-ДД", code="bad_day")
    if d > today + timedelta(days=1):
        raise Invalid("day: дата в будущем", code="bad_day")
    return d.isoformat()


def _check_ts(ts: str, day: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        raise Invalid("ts: ожидается ISO-время", code="bad_ts")
    if parsed.date().isoformat() != day and (parsed.tzinfo is None):
        raise Invalid("ts не совпадает с day", code="bad_ts")
    return str(ts)


# --- черновик ---------------------------------------------------------------------

def check_draft(draft) -> dict:
    """Черновик от клиента -> проверенный (тоталы пересчитываются на сервере, как в vision)."""
    from tjbot import vision
    if not isinstance(draft, dict):
        raise Invalid("draft: ожидается объект {foods, totals}", code="bad_draft")
    clean = vision._valid_meal(dict(draft))
    if clean is None:
        raise Invalid("draft не прошёл проверку: нужны блюда с названием и ккал "
                      "(итог 0–6000 ккал)", code="bad_draft")
    return clean


def _uuid(value) -> str | None:
    if value in (None, ""):
        return None
    try:
        return str(uuidlib.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise Invalid("uuid: ожидается UUID", code="bad_uuid")


def _clean_notes(notes, correction) -> list[str]:
    out = [str(n).strip()[:400] for n in (notes or []) if str(n).strip()]
    if correction is not None:
        c = str(correction).strip()
        if len(c) < 2:
            raise Invalid("уточнение слишком короткое", code="bad_correction")
        out.append(c[:400])
    return out[-MAX_NOTES:]


# --- разбор -----------------------------------------------------------------------

def _empty(reason: str | None, source: dict, notes: list[str]) -> dict:
    return {"recognized": False, "reason": reason, "draft": None, "notes": notes,
            "source": source}


def _run_parse(con, uid: int, *, data: bytes | None, mime: str | None, text: str | None,
               notes: list[str], source: dict) -> dict:
    from tjbot import access, vision
    if data is not None and not vision.has_vision():
        return _empty("no_vision", source, notes)
    if not access.llm_quota_consume(uid, con):
        return _empty("quota", source, notes)
    correction = "; ".join(notes) if notes else None
    engine = vision.engine_for(uid)
    try:
        if data is not None:
            draft = vision.parse_meal(data, media_type=mime or "image/jpeg", engine=engine,
                                      correction=correction, hint=text)
        else:
            draft = vision.parse_meal_text(text, engine=engine, correction=correction)
    except Exception as e:
        print(f"[meal] парс не удался: {type(e).__name__}", flush=True)
        draft = None
    if not draft:
        return _empty("not_recognized", source, notes)
    return {"recognized": True, "reason": None, "draft": draft, "notes": notes,
            "source": source}


def parse(con, uid: int, *, upload_id: str | None = None, text: str | None = None,
          correction: str | None = None, notes: list | None = None,
          uploads_root=None) -> dict:
    """Фото (upload_id, только своё) или текст -> {recognized, reason, draft, notes, source}.
    reason: null | "quota" | "no_vision" | "not_recognized". Ровно один источник.
    Повторное уточнение: те же upload_id/text + `notes` (накопленные) + `correction` (новое)."""
    from . import uploads
    has_text = text is not None and str(text).strip() != ""
    if not upload_id and not has_text:
        raise BadRequest("нужно upload_id или text", code="bad_source")
    all_notes = _clean_notes(notes, correction)
    if upload_id:
        data, mime = uploads.read_bytes(con, uid, upload_id, root=uploads_root)
        hint = str(text).strip()[:MAX_TEXT] if has_text else None   # описание к фото
        src = {"kind": "photo", "upload_id": uploads.get(con, uid, upload_id)["id"],
               "url": uploads.public_url(upload_id), "text": hint}
        return _run_parse(con, uid, data=data, mime=mime, text=hint, notes=all_notes,
                          source=src)
    t = str(text).strip()
    if len(t) < 3:
        raise Invalid("описание слишком короткое", code="text_too_short")
    t = t[:MAX_TEXT]
    return _run_parse(con, uid, data=None, mime=None, text=t, notes=all_notes,
                      source={"kind": "text", "upload_id": None, "url": None, "text": t})


def _saved_file(con, uid: int, meal: dict, uploads_root=None):
    """Байты сохранённого фото приёма -> (bytes, mime, upload_id) | None (нет файла)."""
    from . import uploads
    rel = meal.get("photo_path")
    if not rel:
        return None
    row = con.execute('SELECT "id" FROM uploads WHERE "path"=? AND "uid"=? '
                      'AND "deleted_at" IS NULL', (rel, int(uid))).fetchone()
    try:
        root = uploads_root if uploads_root is not None else uploads.uploads_root()
        p = uploads._safe_path(root, rel)
        if not p.is_file():
            return None
        data = p.read_bytes()
    except Exception:
        return None
    found = uploads.sniff(data)
    return data, (found[0] if found else "image/jpeg"), (row["id"] if row else None)


def parse_saved(con, uid: int, meal_id: int, *, correction: str, notes: list | None = None,
                uploads_root=None) -> dict:
    """Перепарс СОХРАНЁННОГО приёма с текст-уточнением: по файлу, иначе по тексту-описанию
    (note). Ни того ни другого (приём из Telegram без описания) -> Invalid fix_no_source."""
    meal = _get(con, uid, meal_id)
    all_notes = _clean_notes(notes, correction)
    f = _saved_file(con, uid, meal, uploads_root)
    note = (meal.get("note") or "").strip()
    if f is not None:
        data, mime, up_id = f
        src = {"kind": "photo", "upload_id": up_id, "meal_id": int(meal_id),
               "url": f"/api/uploads/{up_id}" if up_id else None, "text": note or None}
        return _run_parse(con, uid, data=data, mime=mime, text=note or None, notes=all_notes,
                          source=src)
    if note:
        return _run_parse(con, uid, data=None, mime=None, text=note, notes=all_notes,
                          source={"kind": "text", "upload_id": None, "meal_id": int(meal_id),
                                  "url": None, "text": note})
    raise Invalid("нечего перепарсить: у приёма нет фото и описания", code="fix_no_source")


# --- строки meals -----------------------------------------------------------------

def _row(r) -> dict:
    m = dict(r)
    try:
        m["foods"] = json.loads(m["foods"]) if m.get("foods") else []
    except ValueError:
        m["foods"] = []
    return m


def _get(con, uid: int, meal_id: int) -> dict:
    r = con.execute('SELECT * FROM meals WHERE "id"=? AND "tg_id"=?',
                    (int(meal_id), int(uid))).fetchone()
    if not r:
        raise NotFound("приём пищи не найден")
    return _row(r)


def get(con, uid: int, meal_id: int) -> dict:
    """Один приём пищи (только свой) для клиента."""
    return public(con, _get(con, uid, meal_id))


def public(con, m: dict) -> dict:
    """Приём для клиента: без Telegram file_id и внутренних путей, с photo_url."""
    photo_url = None
    if m.get("photo_path"):
        r = con.execute('SELECT "id" FROM uploads WHERE "path"=? AND "uid"=? '
                        'AND "deleted_at" IS NULL', (m["photo_path"], m["tg_id"])).fetchone()
        if r:
            photo_url = f"/api/uploads/{r['id']}"
    return {"id": m["id"], "uuid": m.get("client_uuid"), "day": m["day"], "ts": m["ts"],
            "foods": m["foods"], "kcal": m["kcal"], "protein_g": m["protein_g"],
            "fat_g": m["fat_g"], "carb_g": m["carb_g"], "note": m.get("note"),
            "photo_url": photo_url, "quality": m.get("quality"),
            "quality_note": m.get("quality_note"), "engine": m.get("engine")}


def _insert(con, uid, day, ts, draft, *, note, photo_path, client_uuid, engine,
            meal_id=None) -> int:
    t = draft["totals"]
    cols = ('"tg_id","day","ts","foods","kcal","protein_g","fat_g","carb_g","note",'
            '"photo_path","client_uuid","engine","quality","quality_note"')
    vals = [uid, day, ts, json.dumps(draft["foods"], ensure_ascii=False), t.get("kcal"),
            t.get("protein_g"), t.get("fat_g"), t.get("carb_g"), note, photo_path,
            client_uuid, engine, draft.get("quality"), draft.get("quality_note")]
    if meal_id is not None:
        cols = '"id",' + cols
        vals = [int(meal_id)] + vals
    cur = con.execute(f"INSERT INTO meals ({cols}) VALUES ({','.join('?' * len(vals))})", vals)
    return cur.lastrowid


def save(con, uid: int, *, draft: dict, day: str | None = None, ts: str | None = None,
         uuid: str | None = None, upload_id: str | None = None, text: str | None = None,
         tz="UTC", now: datetime | None = None) -> dict:
    """Сохранить подтверждённый черновик -> {created, meal}.
    uuid — клиентский ключ идемпотентности: повтор возвращает уже записанный приём
    (created=false), дубля нет. upload_id -> meals.photo_path, text -> meals.note."""
    from tjbot import vision
    from . import uploads
    clean = check_draft(draft)
    day = check_day(day, tz, now)
    cu = _uuid(uuid)
    if cu:
        old = con.execute('SELECT * FROM meals WHERE "tg_id"=? AND "client_uuid"=?',
                          (int(uid), cu)).fetchone()
        if old:
            return {"created": False, "meal": public(con, _row(old))}
    photo_path = uploads.get(con, uid, upload_id)["path"] if upload_id else None
    note = str(text).strip()[:MAX_TEXT] if text and str(text).strip() else None
    ts = _check_ts(ts, day) if ts else meal_ts(day, tz, now)
    try:
        mid = _insert(con, int(uid), day, ts, clean, note=note, photo_path=photo_path,
                      client_uuid=cu, engine=vision.engine_for(uid))
        con.commit()
    except sqlite3.IntegrityError:          # гонка с параллельным повтором того же uuid
        con.rollback()
        old = con.execute('SELECT * FROM meals WHERE "tg_id"=? AND "client_uuid"=?',
                          (int(uid), cu)).fetchone()
        if not old:
            raise
        return {"created": False, "meal": public(con, _row(old))}
    return {"created": True, "meal": public(con, _get(con, uid, mid))}


def replace(con, uid: int, meal_id: int, *, draft: dict, day: str | None = None,
            ts: str | None = None, tz="UTC", now: datetime | None = None) -> dict:
    """Правка приёма = замена: delete+add ОДНОЙ транзакцией, id/uuid/фото/описание/время
    сохраняются (день поменяли без ts -> полдень нового дня). Повтор того же вызова даёт то же
    состояние."""
    from tjbot import vision
    old = _get(con, uid, meal_id)
    clean = check_draft(draft)
    new_day = check_day(day, tz, now) if day else old["day"]
    if ts:
        new_ts = _check_ts(ts, new_day)
    elif new_day == old["day"]:
        new_ts = old["ts"]
    else:
        new_ts = meal_ts(new_day, tz, now)
    try:
        with con:
            con.execute('DELETE FROM meals WHERE "id"=? AND "tg_id"=?', (int(meal_id), int(uid)))
            _insert(con, int(uid), new_day, new_ts, clean, note=old.get("note"),
                    photo_path=old.get("photo_path"), client_uuid=old.get("client_uuid"),
                    engine=vision.engine_for(uid), meal_id=meal_id)
    except sqlite3.IntegrityError:
        raise Invalid("не удалось заменить приём", code="replace_failed")
    return public(con, _get(con, uid, meal_id))


def delete(con, uid: int, meal_id: int) -> None:
    from tjbot import db as botdb
    if not botdb.delete_meal(con, int(uid), int(meal_id)):
        raise NotFound("приём пищи не найден")


def day_meals(con, uid: int, day: str | None = None, tz="UTC",
              now: datetime | None = None) -> dict:
    """Приёмы дня + тоталы + вода: {day, meals, totals, water_ml, water_l}."""
    from tjbot import db as botdb
    day = check_day(day, tz, now)
    rows = [_row(r) for r in con.execute(
        'SELECT * FROM meals WHERE "tg_id"=? AND "day"=? ORDER BY "ts","id"', (int(uid), day))]
    water = botdb.water_for_day(con, int(uid), day)
    from tj.analysis import nutrition_goals as ng
    from tjbot import llm_gen
    _goal, weight, targets = llm_gen.user_targets(con, int(uid), day)
    totals = nutr.day_totals(rows)
    return {"day": day, "meals": [public(con, m) for m in rows],
            "totals": totals, "water_l": water,
            "water_ml": int(round(water * 1000)),
            "targets": targets, "burned": ng.burned(con, int(uid), day),
            "water_target_l": ng.water_target_l(ng.sweat_ml(con, int(uid), day)),
            "micro_targets": nutr.MICRO_TARGETS, "micro_limit": sorted(nutr.MICRO_LIMIT),
            "protein_per_kg": round(totals["protein_g"] / weight, 2)
            if weight and totals["protein_g"] else None}


# --- вода -------------------------------------------------------------------------

def add_water(con, uid: int, delta_ml, day: str | None = None, tz="UTC",
              now: datetime | None = None) -> dict:
    """+delta_ml к воде дня (отрицательное — откат, итог не ниже 0) -> {day, water_ml, water_l}."""
    from tjbot import db as botdb
    if isinstance(delta_ml, bool) or not isinstance(delta_ml, (int, float)):
        raise Invalid("delta_ml: ожидается число миллилитров", code="bad_delta")
    d = int(round(delta_ml))
    if d == 0 or abs(d) > MAX_WATER_DELTA_ML:
        raise Invalid(f"delta_ml: от -{MAX_WATER_DELTA_ML} до {MAX_WATER_DELTA_ML}, не 0",
                      code="bad_delta")
    day = check_day(day, tz, now)
    total = botdb.add_water(con, int(uid), day, d / 1000.0)
    return {"day": day, "water_l": total, "water_ml": int(round(total * 1000))}


def water(con, uid: int, day: str | None = None, tz="UTC", now: datetime | None = None) -> dict:
    from tjbot import db as botdb
    day = check_day(day, tz, now)
    total = botdb.water_for_day(con, int(uid), day)
    return {"day": day, "water_l": total, "water_ml": int(round(total * 1000))}
