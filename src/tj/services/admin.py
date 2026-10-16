"""Администрирование без Telegram: пользователи и роли, залы, тренеры, статистика, «Разбор полётов».

Портировано из handlers/admin.py и handlers/pro.py. Роли пишутся через tjbot.access
(источник правды — user_roles). Инвайты живут в tj.services.auth / routes/auth.py.
Жёсткое правило: у системы всегда остаётся хотя бы один админ.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tj.analysis import activity_stats
from tjbot import access
from tjbot import db as botdb

from . import auth as auth_svc

MAX_GYM_NAME = 60            # разумная длина; лимита callback_data (64 байта) больше нет
RESERVED_GYMS = {"other", "solo"}
STATS_MAX_DAYS = 3650
REVIEW_KIND = "admin_review"


class AdminError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _nicks(con) -> dict[int, str]:
    return {int(r["tg_id"]): r["nick"] for r in con.execute('SELECT "tg_id","nick" FROM users')
            if r["nick"]}


def _roles_map(con) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for r in con.execute('SELECT "user_id","role","gym" FROM user_roles'):
        d = out.setdefault(int(r["user_id"]), {"allowlist": False, "pro": False, "admin": False,
                                               "coach": False, "coach_gym": None, "coach_gyms": []})
        if r["role"] == "coach":
            d["coach"], d["coach_gym"] = True, r["gym"]
        elif r["role"] in d:
            d[r["role"]] = True
    for uid, gyms in access.load_coach_gyms().items():          # все залы тренера
        if uid in out:
            out[uid]["coach_gyms"] = gyms
            out[uid]["coach_gym"] = out[uid]["coach_gym"] or (gyms[0] if gyms else None)
    return out


def _blank_roles() -> dict:
    return {"allowlist": False, "pro": False, "admin": False, "coach": False, "coach_gym": None,
            "coach_gyms": []}


def _known(con, uid: int) -> bool:
    return (con.execute('SELECT 1 FROM users WHERE "tg_id"=?', (int(uid),)).fetchone() is not None
            or con.execute('SELECT 1 FROM user_roles WHERE "user_id"=?', (int(uid),)).fetchone()
            is not None)


def _admins(con) -> set[int]:
    return {int(r[0]) for r in con.execute('SELECT "user_id" FROM user_roles WHERE "role"=\'admin\'')}


# --------------------------------------------------------------------------- пользователи

def list_users(con, q: str | None = None) -> list[dict]:
    """Все, у кого есть строка users или хоть одна роль. q — подстрока ника/id."""
    roles = _roles_map(con)
    rows = {int(r["tg_id"]): dict(r) for r in
            con.execute('SELECT "tg_id","nick","gym","created_at" FROM users')}
    out = []
    for uid in sorted(set(rows) | set(roles)):
        u = rows.get(uid, {})
        item = {"id": uid, "nick": u.get("nick"), "gym": u.get("gym"),
                "created_at": u.get("created_at"), "roles": roles.get(uid, _blank_roles())}
        if q and q.casefold() not in f"{item['nick'] or ''} {uid}".casefold():
            continue
        out.append(item)
    out.sort(key=lambda x: ((x["nick"] or "").casefold(), x["id"]))
    return out


def get_user(con, uid: int) -> dict | None:
    for u in list_users(con):
        if u["id"] == int(uid):
            return u
    return None


def set_roles(con, uid: int, changes: dict) -> dict:
    """Выдать/снять роли. changes: allowlist/pro/admin — bool, coach — null (снять), название зала
    или СПИСОК залов (тренер может вести несколько; это полный набор, он заменяет прежний). Сначала проверяем всё, потом применяем (частично не применяется).
    Нельзя: снять admin у последнего админа; снять allowlist у админа; тренера в несуществующий зал."""
    uid = int(uid)
    if not _known(con, uid):
        raise AdminError(404, "пользователь не найден")
    unknown = set(changes) - {"allowlist", "pro", "admin", "coach"}
    if unknown or not changes:
        raise AdminError(422, "роли: allowlist, pro, admin (bool), coach (зал или null)")
    for k in ("allowlist", "pro", "admin"):
        if k in changes and not isinstance(changes[k], bool):
            raise AdminError(422, f"{k}: true или false")
    cur = _roles_map(con).get(uid, _blank_roles())
    will_admin = changes.get("admin", cur["admin"])
    if cur["admin"] and not will_admin and _admins(con) <= {uid}:
        raise AdminError(409, "нельзя снять роль admin у последнего администратора")
    if changes.get("allowlist") is False and will_admin:
        raise AdminError(409, "у администратора нельзя убрать доступ: сначала снимите роль admin")
    gyms: list[str] | None = None
    if changes.get("coach") is not None:
        raw = changes["coach"]
        raw = [raw] if isinstance(raw, str) else raw
        if not isinstance(raw, list) or not raw or not all(isinstance(x, str) for x in raw):
            raise AdminError(422, "coach: зал, список залов или null")
        gyms = []
        for name in raw:
            if not botdb.gym_exists(con, name):
                raise AdminError(422, f"coach: такого зала нет: {name}")
            canon = next(g["name"] for g in botdb.list_gyms(con) if g["name"].casefold() == name.casefold())
            if canon not in gyms:
                gyms.append(canon)
    # применяем
    if changes.get("admin") is True:
        access.add_admin(uid)
        access.add_user(uid)                  # админ без доступа бессмысленен
    elif changes.get("admin") is False:
        access.remove_admin(uid)
    if changes.get("allowlist") is True:
        access.add_user(uid)
    elif changes.get("allowlist") is False:
        access.remove_user(uid)
    if changes.get("pro") is True:
        access.add_pro(uid)
    elif changes.get("pro") is False:
        access.remove_pro(uid)
    if "coach" in changes:
        if gyms is None:
            access.remove_coach(uid)
        else:
            access.set_coach_gyms(uid, gyms)
    if changes.get("allowlist") is False:
        auth_svc.revoke_user_sessions(con, uid)
    return _roles_map(con).get(uid, _blank_roles())


def remove_access(con, uid: int) -> None:
    """Убрать пользователя из бота/PWA: allowlist, pro, coach, сессии. Данные тренировок остаются.
    Администратора удалить нельзя (сначала снять admin — а он защищён правилом последнего)."""
    uid = int(uid)
    if not _known(con, uid):
        raise AdminError(404, "пользователь не найден")
    if uid in _admins(con):
        raise AdminError(409, "администратора нельзя удалить: сначала снимите роль admin")
    access.remove_user(uid)
    access.remove_pro(uid)
    access.remove_coach(uid)
    auth_svc.revoke_user_sessions(con, uid)


# --------------------------------------------------------------------------- залы

def gym_name_error(con, name: str) -> str | None:
    """Валидация имени зала (лимит callback_data убран — нужна только разумная длина)."""
    if not name or "\n" in name or "\r" in name:
        return "название зала: одна непустая строка"
    if len(name) > MAX_GYM_NAME:
        return f"название зала: не длиннее {MAX_GYM_NAME} символов"
    if name.casefold() in RESERVED_GYMS:
        return "это название зарезервировано"
    if botdb.gym_exists(con, name):
        return "такой зал уже есть"
    return None


def list_gyms(con) -> list[dict]:
    counts = {r["gym"]: r["n"] for r in con.execute(
        'SELECT "gym", COUNT(*) AS n FROM users GROUP BY "gym"')}
    coaches = access.load_coach_gyms()
    nicks = _nicks(con)
    out = []
    for g in botdb.list_gyms(con):
        out.append({"name": g["name"], "is_default": bool(g["is_default"]),
                    "members": counts.get(g["name"], 0),
                    "coaches": [{"id": i, "nick": nicks.get(i)} for i, gys in sorted(coaches.items())
                                if g["name"] in gys]})
    return out


def add_gym(con, name: str) -> dict:
    name = (name or "").strip()
    err = gym_name_error(con, name)
    if err:
        raise AdminError(409 if err == "такой зал уже есть" else 422, err)
    botdb.add_gym(con, name)
    return {"name": name, "is_default": False, "members": 0, "coaches": []}


# --------------------------------------------------------------------------- тренеры

def list_coaches(con) -> list[dict]:
    nicks = _nicks(con)
    return [{"id": i, "nick": nicks.get(i), "gym": gyms[0] if gyms else None, "gyms": gyms}
            for i, gyms in sorted(access.load_coach_gyms().items())]


def assign_coach(con, uid: int, gym: str) -> dict:
    """Добавить тренеру зал (прежние залы остаются)."""
    cur = _roles_map(con).get(int(uid), _blank_roles())["coach_gyms"]
    roles = set_roles(con, uid, {"coach": list(cur) + [gym]})
    return {"id": int(uid), "nick": _nicks(con).get(int(uid)), "gym": roles["coach_gym"],
            "gyms": roles["coach_gyms"]}


def revoke_coach(con, uid: int, gym: str | None = None) -> None:
    """Снять тренера целиком или только из одного зала."""
    if int(uid) not in access.load_coach_gyms():
        raise AdminError(404, "этот пользователь не тренер")
    if gym is not None and gym not in access.coach_gyms(int(uid)):
        raise AdminError(404, "тренер не ведёт этот зал")
    access.remove_coach(int(uid), gym=gym)



# --------------------------------------------------------------------------- статистика

def stats(con, days: int | None = None, now: datetime | None = None, lang: str = "ru") -> dict:
    """Активность пользователей за days дней (None/0 — за всё время), данными, не текстом."""
    now = now or datetime.now(timezone.utc)
    since = None
    if days:
        if not 0 < days <= STATS_MAX_DAYS:
            raise AdminError(422, f"days: от 1 до {STATS_MAX_DAYS}")
        since = (now - timedelta(days=days)).isoformat(timespec="seconds")
    users = activity_stats.aggregate(botdb.action_counts(con, since), _nicks(con), lang)
    return {"days": days or None, "since": since, "users": users,
            "total": sum(u["total"] for u in users)}


# --------------------------------------------------------------------------- «Разбор полётов»

def review_running_job(con) -> str | None:
    """job_id уже идущего прогона (общий для всех админов) или None."""
    r = con.execute('SELECT "id" FROM jobs WHERE "kind"=? AND "status" IN (\'pending\',\'running\') '
                    'ORDER BY "created_at" DESC LIMIT 1', (REVIEW_KIND,)).fetchone()
    return r["id"] if r else None


def summarize_review(res: list[dict]) -> dict:
    """Результат claude_review.run_all -> компактный JSON (как _review_report бота, но данными)."""
    for u in res:
        if "error" in u and "tg_id" not in u:
            return {"ok": False, "error": u["error"], "users": []}
    users = []
    for u in res:
        days = u.get("days") or []
        users.append({"id": u.get("tg_id"),
                      "ok": sum(1 for d in days if d.get("ok")),
                      "skipped": sum(1 for d in days if d.get("skip")),
                      "errors": sum(1 for d in days if d.get("error")) + (1 if u.get("error") else 0),
                      "summary": bool(u.get("summary"))})
    return {"ok": True, "error": None, "users": users}


def run_review(db_path) -> dict:
    """Тело задачи: прогон разборов по всем Pro."""
    from tjbot import claude_review
    return summarize_review(claude_review.run_all(db_path))
