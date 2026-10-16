"""Профиль и онбординг без Telegram.

Единственное место валидации полей профиля (в хендлерах бота она дублируется:
onboarding.py и profile_edit.py). Данные — таблица users; функции БД переиспользуют
tjbot.db. Чистые функции над sqlite-соединением, без HTTP.
"""
from __future__ import annotations

import sqlite3

from tjbot import db as botdb

from ._schema import ensure
from .clock import now_iso

_MIG = "0050_profile_meta"

MAX_NICK = 40
MAX_CITY = 60
HEIGHT_RANGE = (100, 250)
AGE_RANGE = (10, 100)
WEIGHT_RANGE = (20.0, 400.0)
SEX_VALUES = ("m", "f")
LANGS = ("ru", "en")
SPECIAL_GYMS = ("solo", "other")      # «тренируюсь один» / «другой зал» (как в онбординге бота)

PATCHABLE = ("nick", "height_cm", "weight_kg", "sex", "age", "gym", "extra_gyms", "lang", "goal", "city", "astro")
REQUIRED = ("nick", "height_cm", "weight_kg", "sex", "age", "gym")   # онбординг завершён, когда все есть


class ProfileError(ValueError):
    """Ошибки валидации по полям: .errors = {поле: сообщение}."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


# --------------------------------------------------------------------------- валидация

def _int(v):
    if isinstance(v, bool):
        raise ValueError
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    raise ValueError


def _float(v):
    if isinstance(v, bool):
        raise ValueError
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        return float(v.strip().replace(",", "."))
    raise ValueError


def valid_gym_names(con) -> list[str]:
    return [g["name"] for g in botdb.list_gyms(con)] + list(SPECIAL_GYMS)


def validate_fields(con, data: dict) -> dict:
    """Проверить и нормализовать переданные поля профиля. Неизвестные поля — ошибка.
    Возвращает чистый dict; при нарушениях бросает ProfileError со всеми ошибками сразу."""
    clean: dict = {}
    err: dict[str, str] = {}
    for k, v in data.items():
        if k not in PATCHABLE:
            err[k] = "неизвестное поле"
            continue
        try:
            if k == "nick":
                s = str(v).strip() if v is not None else ""
                if not s or len(s) > MAX_NICK:
                    raise ValueError
                clean[k] = s
            elif k == "height_cm":
                n = _int(v)
                if not HEIGHT_RANGE[0] <= n <= HEIGHT_RANGE[1]:
                    raise ValueError
                clean[k] = n
            elif k == "weight_kg":
                f = _float(v)
                if not WEIGHT_RANGE[0] <= f <= WEIGHT_RANGE[1]:
                    raise ValueError
                clean[k] = round(f, 2)
            elif k == "sex":
                if v not in SEX_VALUES:
                    raise ValueError
                clean[k] = v
            elif k == "age":
                n = _int(v)
                if not AGE_RANGE[0] <= n <= AGE_RANGE[1]:
                    raise ValueError
                clean[k] = n
            elif k == "gym":
                if v not in valid_gym_names(con):
                    raise ValueError
                clean[k] = v
            elif k == "extra_gyms":
                if not isinstance(v, list) or len(v) > 20:
                    raise ValueError
                known = {g["name"].casefold(): g["name"] for g in botdb.list_gyms(con)}
                names = []
                for x in v:
                    c = known.get(str(x).casefold())
                    if c is None:
                        raise ValueError
                    if c not in names:
                        names.append(c)
                clean[k] = names
            elif k == "lang":
                if v not in LANGS:
                    raise ValueError
                clean[k] = v
            elif k == "goal":
                if v not in botdb.GOALS:
                    raise ValueError
                clean[k] = v
            elif k == "city":
                s = str(v).strip() if v is not None else ""
                if not s or len(s) > MAX_CITY:
                    raise ValueError
                clean[k] = s
            elif k == "astro":
                if not isinstance(v, bool):
                    raise ValueError
                clean[k] = v
        except (ValueError, TypeError):
            err[k] = _MSG[k]
    if err:
        raise ProfileError(err)
    return clean


_MSG = {
    "nick": f"ник: от 1 до {MAX_NICK} символов",
    "height_cm": f"рост: целое число {HEIGHT_RANGE[0]}–{HEIGHT_RANGE[1]} см",
    "weight_kg": f"вес: число {WEIGHT_RANGE[0]:g}–{WEIGHT_RANGE[1]:g} кг",
    "sex": "пол: m или f",
    "age": f"возраст: целое число {AGE_RANGE[0]}–{AGE_RANGE[1]}",
    "gym": "зал: из списка /api/gyms (или solo / other)",
    "extra_gyms": "дополнительные залы: список названий из /api/gyms",
    "lang": "язык: ru или en",
    "goal": f"цель питания: одна из {', '.join(botdb.GOALS)}",
    "city": f"город: от 1 до {MAX_CITY} символов",
    "astro": "astro: true или false",
}


# --------------------------------------------------------------------------- часы

def available_watch_actions(profile: dict) -> list[str]:
    """Правило «один источник часов» (из menu._profile_kb): какие действия с часами доступны.

    profile["watch"] = {"garmin": {"status": ...} | None, "samsung": bool, "whoop": bool,
    "apple": bool} (bool — подключено). Пока подключён один источник, подключение
    остальных скрыто; у Garmin с истёкшими токенами доступен повторный вход."""
    w = profile.get("watch") or {}
    garmin = w.get("garmin")
    has_acc = garmin is not None
    sam, wh, ap = bool(w.get("samsung")), bool(w.get("whoop")), bool(w.get("apple"))
    out: list[str] = []
    if has_acc:
        if (garmin or {}).get("status") == "expired":
            out.append("garmin_connect")
        out += ["garmin_sync", "garmin_history", "garmin_disconnect"]
    elif not (sam or wh or ap):
        out.append("garmin_connect")
    if sam:
        out.append("samsung_disconnect")
    elif not (has_acc or wh or ap):
        out.append("samsung_connect")
    if wh:
        out += ["whoop_sync", "whoop_disconnect"]
    elif not (has_acc or sam or ap):
        out.append("whoop_connect")
    if ap:
        out.append("apple_disconnect")
    elif not (has_acc or sam or wh):
        out.append("apple_connect")
    return out


def watch_state(con, uid: int) -> dict:
    acc = botdb.garmin_account_get(con, uid)

    def _on(provider: str) -> bool:
        a = botdb.watch_account_get(con, uid, provider)
        return bool(a and a["status"] == "connected")

    return {"garmin": ({"status": acc["status"]} if acc else None),
            "samsung": _on("samsung"), "whoop": _on("whoop"), "apple": _on("apple")}


# --------------------------------------------------------------------------- чтение

def get_profile(con, uid: int) -> dict | None:
    """Профиль или None, если строки users нет."""
    ensure(con, _MIG)
    u = botdb.get_user(con, uid)
    if u is None:
        return None
    d = dict(u)
    prof = {
        "id": int(uid), "nick": d.get("nick"), "height_cm": d.get("height_cm"),
        "weight_kg": d.get("weight_kg"), "sex": d.get("sex"), "age": d.get("age"),
        "gym": d.get("gym"), "extra_gyms": botdb.extra_gyms(con, uid), "level": d.get("level"),
        "lang": botdb.user_lang(con, uid), "goal": botdb.user_goal(con, uid),
        "city": botdb.user_city(con, uid), "astro": botdb.user_astro(con, uid),
        "created_at": d.get("created_at"), "updated_at": d.get("updated_at"),
        "watch": watch_state(con, uid),
    }
    prof["available_watch_actions"] = available_watch_actions(prof)
    return prof


def onboarding_status(con, uid: int) -> dict:
    """Что осталось заполнить. complete — все обязательные поля профиля на месте."""
    u = botdb.get_user(con, uid)
    d = dict(u) if u else {}
    missing = [f for f in REQUIRED if d.get(f) in (None, "")]
    w = watch_state(con, uid)
    has_watch = bool(w["garmin"] or w["samsung"] or w["whoop"] or w["apple"])
    return {"complete": not missing, "missing": missing,
            "optional_missing": [] if has_watch else ["watch"],
            "ranges": {"height_cm": list(HEIGHT_RANGE), "age": list(AGE_RANGE),
                       "weight_kg": list(WEIGHT_RANGE)}}


def list_gyms(con) -> dict:
    gyms = botdb.list_gyms(con)
    return {"gyms": [{"name": g["name"], "is_default": bool(g["is_default"]),
                      "members": len(botdb.gym_members(con, g["name"]))} for g in gyms],
            "special": list(SPECIAL_GYMS)}


# --------------------------------------------------------------------------- запись

def update_profile(con, uid: int, data: dict) -> dict:
    """PATCH: точечные UPDATE (как profile_edit бота, не save_user — тот сбросил бы created_at).
    Пользователю без строки users строка создаётся, если в data есть ник."""
    ensure(con, _MIG)
    clean = validate_fields(con, data)
    if botdb.get_user(con, uid) is None:
        if not clean.get("nick"):
            raise ProfileError({"nick": "профиль ещё не создан: нужен ник"})
        con.execute('INSERT INTO users ("tg_id","nick","lang","created_at") VALUES (?,?,?,?)',
                    (int(uid), clean["nick"], "ru", now_iso()))
    setters = {"nick": botdb.set_nick, "height_cm": botdb.set_height, "weight_kg": botdb.set_weight,
               "sex": botdb.set_sex, "age": botdb.set_age, "gym": botdb.set_gym,
               "lang": botdb.set_lang, "goal": botdb.set_goal, "city": botdb.set_city,
               "astro": botdb.set_astro, "extra_gyms": botdb.set_extra_gyms}
    for k, v in clean.items():
        if k != "extra_gyms":
            setters[k](con, uid, v)
    if "extra_gyms" in clean:                 # после основного зала: он в доп. не входит
        main = clean.get("gym") or (botdb.get_user(con, uid) or {"gym": None})["gym"]
        setters["extra_gyms"](con, uid, [g for g in clean["extra_gyms"] if g != main])
    if clean:
        con.execute('UPDATE users SET "updated_at"=? WHERE "tg_id"=?', (now_iso(), int(uid)))
        con.commit()
    return get_profile(con, uid)
