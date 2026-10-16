"""Цели и личные максимумы (ПМ): сервисы поверх sqlite-соединения.

Вынесено из tjbot/handlers/goal.py и record_result.py. Все операции с целью проверяют
владельца: чужая цель для пользователя выглядит как несуществующая (NotFound).
Экран целей — tj.analysis.levels.goals_screen_data (переиспользуем как есть).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from tj import i18n
from tj.analysis import standards
from tj.analysis.levels import goals_screen_data, tier
from tj.analysis.parse_input import est_1rm_for, parse_benchmark, parse_lift

from .errors import Invalid, NotFound


def _user_sex_bw(con, uid: int) -> tuple[str, float | None]:
    from tjbot import db as botdb
    u = dict(botdb.get_user(con, uid) or {})
    return (u.get("sex") or "m"), u.get("weight_kg")


def screen(con, uid: int, lang: str = "ru") -> dict:
    """Экран целей и уровней: {overall, goals, lifts, benchmarks}."""
    sex, bw = _user_sex_bw(con, uid)
    return goals_screen_data(con, int(uid), sex, bw, lang=lang)


def list_goals(con, uid: int) -> list[dict]:
    from tjbot import db as botdb
    return botdb.active_goals(con, int(uid))


def _owned(con, uid: int, goal_id) -> dict:
    try:
        gid = int(goal_id)
    except (TypeError, ValueError):
        raise NotFound("цель не найдена")
    row = con.execute("SELECT * FROM goals WHERE id=? AND tg_id=?", (gid, int(uid))).fetchone()
    if not row:
        raise NotFound("цель не найдена")
    return dict(row)


def _meta(discipline: str) -> dict:
    meta = standards.disciplines().get(discipline)
    if not meta:
        raise Invalid("discipline: неизвестная дисциплина", code="bad_discipline")
    return meta


def _parse_target(meta: dict, target) -> float:
    """Числовая цель: лифт — кг (принимает «100», «100x1»), бенчмарк — «мм:сс»/секунды/круги."""
    if isinstance(target, bool) or target is None:
        raise Invalid("target обязателен", code="bad_target")
    if isinstance(target, (int, float)):
        val = float(target) if target > 0 else None
    elif meta["kind"] == "lift":
        p = parse_lift(str(target))
        val = p[0] if p else None
    else:
        val = parse_benchmark(str(target), meta["unit"])
    if not val:
        raise Invalid("target: не разобрано значение цели", code="bad_target")
    return val


def add(con, uid: int, kind: str, discipline: str, target, *, lang: str = "ru") -> dict:
    """Новая цель. kind='numeric': target — значение (кг/время/круги); kind='level': target —
    название уровня из standards.tiers() (без первого). -> сохранённая цель."""
    from tjbot import db as botdb
    from tjbot.activity import GOAL_SET
    meta = _meta(discipline)
    dname = standards.discipline_name(meta, lang)
    if kind == "level":
        tiers = standards.tiers("ru")[1:] + standards.tiers("en")[1:]
        t = str(target or "").strip()
        if t not in tiers:
            raise Invalid("target: неизвестный уровень", code="bad_target")
        ru = standards.tiers("ru")
        en = standards.tiers("en")
        canon = t if t in ru else ru[en.index(t)]     # в БД — русское имя, как в боте
        metric, value = "level", canon
        title = i18n.t("goal.title_level", lang, name=dname,
                       target=standards.tier_name(canon, lang))
    elif kind == "numeric":
        value = _parse_target(meta, target)
        metric = "kg" if meta["kind"] == "lift" else meta["basis"]
        title = i18n.t("goal.title_value", lang, name=dname, target=value)
    else:
        raise Invalid("kind: numeric или level", code="bad_kind")
    gid = botdb.add_goal(con, tg_id=int(uid), kind=kind, discipline=discipline,
                         target_value=value, metric=metric, title=title,
                         created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    try:
        botdb.log_action(con, int(uid), GOAL_SET)
    except Exception:
        pass
    return _owned(con, uid, gid)


def archive(con, uid: int, goal_id) -> dict:
    """Убрать цель (status=archived). Чужая/несуществующая -> NotFound, ничего не меняется."""
    from tjbot import db as botdb
    g = _owned(con, uid, goal_id)
    botdb.archive_goal(con, g["id"], int(uid))
    return _owned(con, uid, g["id"])


def complete(con, uid: int, goal_id) -> dict:
    """Отметить цель достигнутой (status=done)."""
    from tjbot import db as botdb
    g = _owned(con, uid, goal_id)
    botdb.complete_goal(con, g["id"], int(uid))
    return _owned(con, uid, g["id"])


def enter_pm(con, uid: int, discipline: str, value, reps=None, *, lang: str = "ru",
             today: date | None = None, tz="UTC") -> dict:
    """Ручной ввод ПМ/результата (как «✍️ Ввести ПМ»). Лифт: value — вес или «100x3»
    (reps можно передать отдельно), считается оценка 1ПМ (Эпли); бенчмарк: «мм:сс»/секунды/круги.
    -> {discipline, name, value, reps, est_1rm, day, tier}"""
    from tjbot import db as botdb
    from .workouts import today_in
    meta = _meta(discipline)
    day = (today or today_in(tz)).isoformat()
    uid = int(uid)
    sex, bw = _user_sex_bw(con, uid)
    est = None
    if meta["kind"] == "lift":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            load, r = float(value), int(reps or 1)
            ok = load > 0 and r >= 1
        else:
            p = parse_lift(str(value if value is not None else ""))
            ok = bool(p)
            load, r = p if p else (None, None)
            if ok and reps:
                r = int(reps)
        if not ok:
            raise Invalid("value: ожидается вес (100) или вес×повторы (100x3)", code="bad_value")
        est = est_1rm_for(load, r)
        botdb.add_result(con, tg_id=uid, discipline=discipline, value=load, reps=r,
                         est_1rm=est, source="manual", day=day)
        val = load
    else:
        val = _parse_target(meta, value)
        r = None
        botdb.add_result(con, tg_id=uid, discipline=discipline, value=val,
                         source="manual", day=day)
    best = botdb.best_results(con, uid)
    t = tier(discipline, best[discipline]["value"], sex, bw, lang=lang) if discipline in best else None
    return {"discipline": discipline, "name": standards.discipline_name(meta, lang),
            "value": val, "reps": r, "est_1rm": est, "day": day, "tier": t}
