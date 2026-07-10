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


def allow_path() -> Path:
    return _ALLOW_DEFAULT


def load_admins(path=None) -> set[int]:
    p = Path(path or _ADMINS_DEFAULT)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return set()
    return {int(x) for x in data.get("admins", [])}


def is_admin(tg_id: int, path=None) -> bool:
    return int(tg_id) in load_admins(path)


def add_admin(tg_id: int, path=None) -> None:
    p = Path(path or _ADMINS_DEFAULT)
    ids = load_admins(p)
    ids.add(int(tg_id))
    p.write_text(json.dumps({"admins": sorted(ids)}, indent=2), encoding="utf-8")


def load_allow(path=None) -> set[int]:
    p = Path(path or _ALLOW_DEFAULT)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return set()
    return {int(x) for x in data.get("allowed_users", [])}


def is_allowed(tg_id: int, path=None) -> bool:
    return int(tg_id) in load_allow(path)


def add_user(tg_id: int, path=None) -> None:
    p = Path(path or _ALLOW_DEFAULT)
    ids = load_allow(p)
    ids.add(int(tg_id))
    p.write_text(json.dumps({"allowed_users": sorted(ids)}, indent=2), encoding="utf-8")


def remove_user(tg_id: int, path=None) -> None:
    p = Path(path or _ALLOW_DEFAULT)
    ids = load_allow(p)
    ids.discard(int(tg_id))
    p.write_text(json.dumps({"allowed_users": sorted(ids)}, indent=2), encoding="utf-8")


def load_pro(path=None) -> set[int]:
    p = Path(path or _PRO_DEFAULT)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return set()
    return {int(x) for x in data.get("pro_users", [])}


def is_pro(tg_id: int, path=None) -> bool:
    return int(tg_id) in load_pro(path)


def add_pro(tg_id: int, path=None) -> None:
    p = Path(path or _PRO_DEFAULT)
    ids = load_pro(p)
    ids.add(int(tg_id))
    p.write_text(json.dumps({"pro_users": sorted(ids)}, indent=2), encoding="utf-8")


def remove_pro(tg_id: int, path=None) -> None:
    p = Path(path or _PRO_DEFAULT)
    ids = load_pro(p)
    ids.discard(int(tg_id))
    p.write_text(json.dumps({"pro_users": sorted(ids)}, indent=2), encoding="utf-8")


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
