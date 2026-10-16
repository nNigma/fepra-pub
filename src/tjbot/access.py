"""Приватный доступ: бот работает только для ID из users_allow.json.

На первый контакт незнакомцу отдаём его Telegram ID — админ добавляет вручную
(как договорились: бот скидывает ID, владелец вписывает в allowlist).
"""
from __future__ import annotations

import json
from datetime import date
from functools import wraps
from pathlib import Path

# Суточный лимит обращений к ИИ (разбор + распознавание) для не-админов.
LLM_DAILY_LIMIT = 7

_ALLOW_DEFAULT = Path(__file__).resolve().parents[2] / "users_allow.json"
_ADMINS_DEFAULT = Path(__file__).resolve().parents[2] / "admins.json"
_PRO_DEFAULT = Path(__file__).resolve().parents[2] / "pro_users.json"
_COACHES_DEFAULT = Path(__file__).resolve().parents[2] / "coaches.json"


def allow_path() -> Path:
    return _ALLOW_DEFAULT


# --- Роли: источник правды — таблица user_roles в БД (миграция 0001). Если path
# передан явно — прежнее JSON-поведение (так работают существующие тесты). ---

def _roles_con(create: bool = False):
    """Короткое соединение с БД ролей. None, если БД ещё нет (читать нечего).
    Вызывающий обязан закрыть."""
    from . import db as botdb
    p = botdb.default_db_path()
    if not create and not p.exists():
        return None
    con = botdb.connect(p)
    if create:
        from tj.migrations import run_migrations
        run_migrations(con)
    return con


def _db_role_ids(role: str) -> dict[int, str | None]:
    import sqlite3
    con = _roles_con()
    if con is None:
        return {}
    try:
        rows = con.execute('SELECT "user_id","gym" FROM user_roles WHERE "role"=?', (role,)).fetchall()
        return {int(r[0]): r[1] for r in rows}
    except sqlite3.OperationalError:  # БД есть, миграции ещё не прогнаны
        return {}
    finally:
        con.close()


def _db_add_role(tg_id: int, role: str, gym: str | None = None) -> None:
    con = _roles_con(create=True)
    try:
        con.execute('INSERT INTO user_roles ("user_id","role","gym") VALUES (?,?,?) '
                    'ON CONFLICT("user_id","role") DO UPDATE SET "gym"=excluded."gym"',
                    (int(tg_id), role, gym))
        con.commit()
    finally:
        con.close()


def _db_remove_role(tg_id: int, role: str) -> None:
    con = _roles_con(create=True)
    try:
        con.execute('DELETE FROM user_roles WHERE "user_id"=? AND "role"=?', (int(tg_id), role))
        con.commit()
    finally:
        con.close()


def _db_coach_gyms() -> dict[int, list[str]]:
    """id тренера -> его залы (основной первым). Основной зал — из user_roles, остальные — coach_gyms."""
    import sqlite3
    con = _roles_con()
    if con is None:
        return {}
    try:
        out: dict[int, list[str]] = {}
        for r in con.execute('SELECT "user_id","gym" FROM user_roles WHERE "role"=\'coach\''):
            out.setdefault(int(r[0]), [])
            if r[1]:
                out[int(r[0])].append(str(r[1]))
        try:
            for r in con.execute('SELECT "user_id","gym" FROM coach_gyms ORDER BY "gym"'):
                lst = out.setdefault(int(r[0]), [])
                if str(r[1]) not in lst:
                    lst.append(str(r[1]))
        except sqlite3.OperationalError:      # миграция 0062 ещё не прогнана
            pass
        return out
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()


def _db_set_coach_gyms(tg_id: int, gyms: list[str]) -> None:
    """Полная замена набора залов тренера. Пусто — тренер снят. Основной зал — первый в списке."""
    con = _roles_con(create=True)
    try:
        uid = int(tg_id)
        con.execute('DELETE FROM coach_gyms WHERE "user_id"=?', (uid,))
        if not gyms:
            con.execute('DELETE FROM user_roles WHERE "user_id"=? AND "role"=\'coach\'', (uid,))
        else:
            con.execute('INSERT INTO user_roles ("user_id","role","gym") VALUES (?,?,?) '
                        'ON CONFLICT("user_id","role") DO UPDATE SET "gym"=excluded."gym"',
                        (uid, "coach", gyms[0]))
            for g in gyms:
                con.execute('INSERT OR IGNORE INTO coach_gyms ("user_id","gym") VALUES (?,?)', (uid, g))
        con.commit()
    finally:
        con.close()


def _read_ids(path, default, key) -> set[int]:
    p = Path(path or default)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return set()
    return {int(x) for x in data.get(key, [])}


def load_admins(path=None) -> set[int]:
    if path is None:
        return set(_db_role_ids("admin"))
    return _read_ids(path, _ADMINS_DEFAULT, "admins")


def is_admin(tg_id: int, path=None) -> bool:
    return int(tg_id) in load_admins(path)


def add_admin(tg_id: int, path=None) -> None:
    if path is None:
        return _db_add_role(tg_id, "admin")
    p = Path(path)
    ids = load_admins(p)
    ids.add(int(tg_id))
    p.write_text(json.dumps({"admins": sorted(ids)}, indent=2), encoding="utf-8")


def remove_admin(tg_id: int, path=None) -> None:
    if path is None:
        return _db_remove_role(tg_id, "admin")
    p = Path(path)
    ids = load_admins(p)
    ids.discard(int(tg_id))
    p.write_text(json.dumps({"admins": sorted(ids)}, indent=2), encoding="utf-8")


def load_allow(path=None) -> set[int]:
    if path is None:
        return set(_db_role_ids("allowlist"))
    return _read_ids(path, _ALLOW_DEFAULT, "allowed_users")


def is_allowed(tg_id: int, path=None) -> bool:
    return int(tg_id) in load_allow(path)


def add_user(tg_id: int, path=None) -> None:
    if path is None:
        return _db_add_role(tg_id, "allowlist")
    p = Path(path)
    ids = load_allow(p)
    ids.add(int(tg_id))
    p.write_text(json.dumps({"allowed_users": sorted(ids)}, indent=2), encoding="utf-8")


def remove_user(tg_id: int, path=None) -> None:
    if path is None:
        return _db_remove_role(tg_id, "allowlist")
    p = Path(path)
    ids = load_allow(p)
    ids.discard(int(tg_id))
    p.write_text(json.dumps({"allowed_users": sorted(ids)}, indent=2), encoding="utf-8")


def load_pro(path=None) -> set[int]:
    if path is None:
        return set(_db_role_ids("pro"))
    return _read_ids(path, _PRO_DEFAULT, "pro_users")


def is_pro(tg_id: int, path=None) -> bool:
    return int(tg_id) in load_pro(path)


def add_pro(tg_id: int, path=None) -> None:
    if path is None:
        return _db_add_role(tg_id, "pro")
    p = Path(path)
    ids = load_pro(p)
    ids.add(int(tg_id))
    p.write_text(json.dumps({"pro_users": sorted(ids)}, indent=2), encoding="utf-8")


def remove_pro(tg_id: int, path=None) -> None:
    if path is None:
        return _db_remove_role(tg_id, "pro")
    p = Path(path)
    ids = load_pro(p)
    ids.discard(int(tg_id))
    p.write_text(json.dumps({"pro_users": sorted(ids)}, indent=2), encoding="utf-8")


def load_coaches(path=None) -> dict[int, str]:
    if path is None:
        return {k: str(v) for k, v in _db_role_ids("coach").items() if v is not None}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    out = {}
    for k, v in (data.get("coaches") or {}).items():
        try:
            out[int(k)] = str(v)
        except (TypeError, ValueError):
            continue
    return out


def coach_gym(tg_id: int, path=None) -> str | None:
    """Основной зал тренера (первый из его залов)."""
    return load_coaches(path).get(int(tg_id))


def load_coach_gyms() -> dict[int, list[str]]:
    """Все тренеры и их залы (из БД)."""
    return _db_coach_gyms()


def coach_gyms(tg_id: int, path=None) -> list[str]:
    """Все залы тренера (основной первым). Пусто — не тренер."""
    if path is None:
        return list(_db_coach_gyms().get(int(tg_id), []))
    g = coach_gym(tg_id, path)
    return [g] if g else []


def is_coach(tg_id: int, path=None) -> bool:
    if path is None:
        return int(tg_id) in _db_coach_gyms()
    return int(tg_id) in load_coaches(path)


def _save_coaches(coaches: dict[int, str], p: Path) -> None:
    p.write_text(json.dumps({"coaches": {str(k): coaches[k] for k in sorted(coaches)}},
                            indent=2, ensure_ascii=False), encoding="utf-8")


def add_coach(tg_id: int, gym: str, path=None) -> None:
    """Добавить зал тренеру (у тренера может быть несколько залов). С path — прежний JSON:
    один зал на тренера, замена."""
    if path is None:
        cur = coach_gyms(tg_id)
        if gym not in cur:
            cur.append(gym)
        return _db_set_coach_gyms(tg_id, cur)
    p = Path(path)
    coaches = load_coaches(p)
    coaches[int(tg_id)] = gym
    _save_coaches(coaches, p)


def set_coach_gyms(tg_id: int, gyms: list[str]) -> None:
    """Задать полный набор залов тренера (пусто — снять роль)."""
    _db_set_coach_gyms(tg_id, list(dict.fromkeys(gyms)))


def remove_coach(tg_id: int, path=None, gym: str | None = None) -> None:
    """Снять тренера целиком; с gym — только из этого зала (остальные остаются)."""
    if path is None:
        if gym is None:
            return _db_set_coach_gyms(tg_id, [])
        return _db_set_coach_gyms(tg_id, [g for g in coach_gyms(tg_id) if g != gym])
    p = Path(path)
    coaches = load_coaches(p)
    coaches.pop(int(tg_id), None)
    _save_coaches(coaches, p)


def llm_quota_remaining(tg_id, con=None, limit: int = LLM_DAILY_LIMIT) -> int | None:
    """Сколько обращений к ИИ осталось сегодня. None = без лимита (админ).
    Только читает, ничего не списывает."""
    if is_admin(tg_id):
        return None
    from . import db
    own = con is None
    if own:
        con = db.connect(db.default_db_path())
    try:
        used = db.llm_quota_used(con, int(tg_id), date.today().isoformat())
        return max(0, limit - used)
    finally:
        if own:
            con.close()


def llm_quota_consume(tg_id, con=None, limit: int = LLM_DAILY_LIMIT) -> bool:
    """Списать одно обращение к ИИ. True = можно (админ — всегда, без списания;
    либо лимит не исчерпан → списано). False = суточный лимит исчерпан."""
    if is_admin(tg_id):
        return True
    from . import db
    own = con is None
    if own:
        con = db.connect(db.default_db_path())
    try:
        day = date.today().isoformat()
        if db.llm_quota_used(con, int(tg_id), day) >= limit:
            return False
        db.llm_quota_bump(con, int(tg_id), day)
        return True
    finally:
        if own:
            con.close()


def restricted(handler):
    """Декоратор PTB-хендлера: пускает только разрешённые ID, иначе отдаёт
    пользователю его ID для передачи админу. PTB не импортируется (утиная типизация)."""
    @wraps(handler)
    async def wrapper(update, context, *args, **kwargs):
        user = getattr(update, "effective_user", None)
        if user is None or not is_allowed(user.id):
            uid = user.id if user else "—"
            await update.effective_message.reply_text(
                f"Доступ закрыт. Передай админу свой Telegram ID: {uid}\n"
                f"Access closed. Send the admin your Telegram ID: {uid}"
            )
            return
        return await handler(update, context, *args, **kwargs)

    return wrapper
