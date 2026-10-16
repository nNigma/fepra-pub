"""Garmin как сервис (без Telegram): вход с MFA, статус, синк, отключение.

Реестр сессий входа живёт в памяти процесса (uvicorn — один воркер): по uid,
TTL 5 минут, один активный вход на uid (новый вытесняет старый). Пароль
существует только в аргументах потока GarminConnectSession: ни в реестре, ни в
БД, ни в логах, ни в сообщениях об ошибках (наружу идёт только тип исключения).
"""
from __future__ import annotations

import shutil
import threading
import time
from datetime import date

from tj.adapters.garmin import GarminAdapter
from tjbot import db as botdb
from tjbot import garmin_alerts, garmin_sync
from tjbot.garmin_connect import GarminConnectSession

from . import notices

SESSION_TTL = 300.0        # секунд на весь вход (логин + ввод MFA)
LOGIN_WAIT = 60.0          # сколько запрос ждёт ответа Garmin (ok / need_mfa)
KIND_EXPIRED = "garmin_expired"
KIND_SYNC_FAILED = "garmin_sync_failed"

_lock = threading.Lock()
_sessions: dict[int, "_Entry"] = {}
_clock = time.monotonic          # подменяется в тестах


class _Entry:
    __slots__ = ("session", "email", "deadline")

    def __init__(self, session, email, deadline):
        self.session, self.email, self.deadline = session, email, deadline

    def __repr__(self):  # никаких секретов даже в отладочном выводе
        return f"<garmin login entry email={self.email!r}>"


def _tz():
    from tj import config as cfgmod
    try:
        return cfgmod.timezone(cfgmod.load_config())
    except Exception:
        return "UTC"


def adapter_factory(email, password, tokenstore, prompt_mfa):
    """Точка подмены в тестах (сеть в тестах не ходим)."""
    return GarminAdapter(email, password, tokenstore, _tz(), prompt_mfa=prompt_mfa)


def _purge_locked() -> None:
    now = _clock()
    for uid in [u for u, e in _sessions.items() if e.deadline <= now]:
        _drop_locked(uid)


def _drop_locked(uid: int) -> None:
    e = _sessions.pop(uid, None)
    if e:
        try:
            e.session.submit_mfa("")     # разбудить поток, ждущий MFA, чтобы он завершился
        except Exception:  # noqa: BLE001
            pass


def pending_count() -> int:
    with _lock:
        _purge_locked()
        return len(_sessions)


_MESSAGES = {
    "GarminConnectAuthenticationError": "Garmin отклонил вход: проверьте email, пароль и код MFA.",
    "GarminConnectTooManyRequestsError": "Garmin временно ограничил запросы. Подождите несколько минут.",
    "TimeoutError": "Время ввода кода MFA истекло. Начните вход заново.",
    "GarminConnectConnectionError": "Не удалось связаться с Garmin. Попробуйте позже.",
}


def _error_message(err_type: str | None) -> str:
    return _MESSAGES.get(err_type or "", "Не удалось войти в Garmin. Проверьте данные и попробуйте позже.")


def _finish(con, uid: int, entry: _Entry, state: str) -> dict:
    if state == "need_mfa":
        return {"state": "need_mfa", "message": "Garmin прислал код подтверждения — введите его."}
    with _lock:
        if _sessions.get(uid) is entry:
            _sessions.pop(uid, None)
    if state == "ok":
        botdb.garmin_account_set(con, uid, entry.email)
        garmin_alerts.reset(con, uid)
        notices.mark_kind_read(con, uid, KIND_EXPIRED)
        notices.mark_kind_read(con, uid, KIND_SYNC_FAILED)
        return {"state": "ok", "message": "Garmin подключён."}
    if state == "pending":                       # Garmin не ответил за LOGIN_WAIT
        _drop_entry(uid, entry)
        return {"state": "error", "message": "Garmin не ответил вовремя. Попробуйте позже."}
    return {"state": "error", "message": _error_message(getattr(entry.session, "_error", None))}


def _drop_entry(uid, entry) -> None:
    with _lock:
        if _sessions.get(uid) is entry:
            _drop_locked(uid)


def start_login(con, uid: int, email: str, password: str, wait: float | None = None) -> dict:
    """-> {"state": "ok"|"need_mfa"|"error", "message": str}. Блокирует до ответа Garmin."""
    email = (email or "").strip()
    if not email or not password:
        return {"state": "error", "message": "Укажите email и пароль Garmin."}
    session = GarminConnectSession(adapter_factory)
    entry = _Entry(session, email, _clock() + SESSION_TTL)
    with _lock:
        _purge_locked()
        _drop_locked(int(uid))                   # один активный вход на uid
        _sessions[int(uid)] = entry
    session.start_login(email, password, str(botdb.garmin_tokenstore(uid)))
    del password
    state = session.wait_state(LOGIN_WAIT if wait is None else wait)
    return _finish(con, int(uid), entry, state)


def submit_mfa(con, uid: int, code: str, wait: float | None = None) -> dict:
    code = (code or "").strip()
    if not code:
        return {"state": "error", "message": "Введите код подтверждения."}
    with _lock:
        _purge_locked()
        entry = _sessions.get(int(uid))
    if entry is None:
        return {"state": "error", "message": "Сессия входа истекла. Начните вход заново."}
    entry.session.submit_mfa(code)
    state = entry.session.wait_state(LOGIN_WAIT if wait is None else wait)
    return _finish(con, int(uid), entry, state)


def _meta_get(con, key):
    r = con.execute('SELECT "value" FROM meta WHERE "key"=?', (key,)).fetchone()
    return r["value"] if r else None


def status(con, uid: int) -> dict:
    acc = botdb.garmin_account_get(con, uid)
    with _lock:
        _purge_locked()
        pending = int(uid) in _sessions
    last = _meta_get(con, garmin_alerts.sync_key(uid))
    return {
        "connected": bool(acc) and acc["status"] == "ok",
        "status": acc["status"] if acc else "none",
        "email": acc["email"] if acc else None,
        "last_sync": last or garmin_sync.last_watch_date(con, uid),
        "fail_count": garmin_alerts.streak(con, uid),
        "mfa_pending": pending,
    }


def _mark_synced(con, uid: int) -> None:
    garmin_alerts.record_success(con, uid)


def _run_sync(fn, uid, db_path, **kw) -> dict:
    db_path = db_path or botdb.default_db_path()
    try:
        res = fn(db_path, uid, botdb.garmin_tokenstore(uid), **kw)
    except Exception as e:
        con = botdb.connect(db_path)
        try:
            garmin_alerts.record_failure(con, uid, type(e).__name__)
        finally:
            con.close()
        raise
    con = botdb.connect(db_path)
    try:
        _mark_synced(con, uid)
    finally:
        con.close()
    return res


def sync_recent(uid: int, db_path=None, upto: date | None = None) -> dict:
    """Для jobs: свежие дни. Исключения летят наружу (job -> error), статус аккаунта обновляется."""
    return _run_sync(garmin_sync.sync_recent, uid, db_path, upto=upto)


def sync_history(uid: int, days: int = 60, db_path=None, upto: date | None = None) -> dict:
    days = max(1, min(int(days), 365))
    return _run_sync(garmin_sync.sync_history, uid, db_path, days=days, upto=upto)


def disconnect(con, uid: int) -> None:
    with _lock:
        _drop_locked(int(uid))
    shutil.rmtree(botdb.garmin_tokenstore(uid), ignore_errors=True)
    botdb.garmin_account_delete(con, uid)
    con.execute('DELETE FROM meta WHERE "key" IN (?,?)', (garmin_alerts.sync_key(uid), garmin_alerts._key(uid)))
    con.commit()
    notices.mark_kind_read(con, uid, KIND_EXPIRED)
    notices.mark_kind_read(con, uid, KIND_SYNC_FAILED)
