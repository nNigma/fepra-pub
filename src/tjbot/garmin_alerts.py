"""Реакция на падения кронового Garmin-синка: статус аккаунта + алерт админам.

Крон молчалив по построению: server_sync.py ловит исключение, пишет строку в
/var/log/fepra_sync.log и выходит с кодом 0. После переезда на другой сервер
(2026-08-27) протухшие refresh-токены роняли синк шесть прогонов подряд, а
профиль в боте всё это время выглядел исправным — заметили только по дыре в
аналитике. Отсюда две вещи:

1. Ошибка авторизации переводит аккаунт в статус expired — профиль показывает
   кнопку подключения (см. handlers/menu._profile_kb).
2. Две неудачи подряд — сообщение админам, дальше повтор раз в неделю, чтобы
   не долбить каждым прогоном.

Успешный синк сбрасывает и статус, и счётчик: лечится само, руками ничего
разблокировать не надо.
"""
from __future__ import annotations

from datetime import datetime, timezone

from tj.analysis.wod_program import _plural

from . import access
from . import db as botdb
from . import tg_notify

ALERT_AT = 2       # неудач подряд до первого сообщения
ALERT_EVERY = 14   # и каждые столько дальше (синк 2×/сутки → примерно раз в неделю)

# Только протухшая авторизация означает «аккаунт надо переподключать». Сетевые
# сбои и 429 статус не трогают: иначе любой чих Garmin гасил бы профиль.
AUTH_ERRORS = ("GarminConnectAuthenticationError",)

_RECONNECT_HINT = ("Токены Garmin протухли — владельцу аккаунта надо переподключиться: "
                   "Профиль → 🔗 Подключить Garmin (email, пароль, MFA), затем «История» — "
                   "она добёрет пропущенное.")

_USER_EXPIRED = "Garmin просит войти заново: токены протухли. Откройте «Подключить Garmin» и войдите ещё раз."
_USER_FAILED = "Синхронизация Garmin не проходит уже несколько раз подряд ({n}). Мы повторим позже; если не пройдёт — переподключите Garmin."


def sync_key(tg_id) -> str:
    return f"garmin_sync_at:{int(tg_id)}"


def _key(tg_id) -> str:
    return f"garmin_fail:{int(tg_id)}"


def _label(con, tg_id) -> str:
    """Алерт уходит админам, а переподключаться — владельцу аккаунта: по голому
    tg_id непонятно, кому передавать."""
    row = botdb.get_user(con, tg_id)
    nick = (row["nick"] if row else None) or ""
    return f"{nick} ({tg_id})" if nick else str(tg_id)


def _streak(con, tg_id) -> int:
    row = con.execute('SELECT "value" FROM meta WHERE "key"=?', (_key(tg_id),)).fetchone()
    if not row:
        return 0
    try:
        return int(row["value"])
    except (TypeError, ValueError):
        return 0


def _streak_set(con, tg_id, n: int) -> None:
    con.execute('INSERT OR REPLACE INTO meta ("key","value") VALUES (?,?)',
                (_key(tg_id), str(int(n))))
    con.commit()


streak = _streak


def reset(con, tg_id) -> None:
    if _streak(con, tg_id):
        _streak_set(con, tg_id, 0)


def _user_notify(con, tg_id, kind: str, text: str) -> None:
    """Уведомление владельцу аккаунта: user_notices (баннер PWA) + push + Telegram-запас.
    Админский алерт (notify) живёт отдельно и не меняется."""
    try:
        from tj.services import push
        push.notify_user(con, tg_id, kind, text, title="Garmin", url="/app/#/garmin", tg=True)
    except Exception as e:  # noqa: BLE001 — уведомление не должно ронять синк
        print(f"[garmin] user notify failed: {type(e).__name__}", flush=True)


def record_success(con, tg_id) -> bool:
    """Успешный синк: сброс счётчика и статуса. True, если до этого шёл алерт (≥ALERT_AT)."""
    was_alerting = _streak(con, tg_id) >= ALERT_AT
    con.execute('INSERT OR REPLACE INTO meta ("key","value") VALUES (?,?)',
                (sync_key(tg_id), datetime.now(timezone.utc).isoformat(timespec="seconds")
                 .replace("+00:00", "Z")))
    con.commit()
    reset(con, tg_id)
    acc = botdb.garmin_account_get(con, tg_id)
    if acc and acc["status"] != "ok":
        botdb.garmin_account_set_status(con, tg_id, "ok")
    return was_alerting


def record_failure(con, tg_id, error) -> dict:
    """Неудачный синк: счётчик, expired при ошибке авторизации, уведомление пользователю.
    -> {"streak", "expired" (перешёл в expired сейчас), "due" (пора алертить админов)}."""
    n = _streak(con, tg_id) + 1
    _streak_set(con, tg_id, n)
    acc = botdb.garmin_account_get(con, tg_id)
    expired_now = bool(error in AUTH_ERRORS and acc and acc["status"] != "expired")
    if expired_now:
        botdb.garmin_account_set_status(con, tg_id, "expired")
        _user_notify(con, tg_id, "garmin_expired", _USER_EXPIRED)
    due = _due(n)
    if due and not expired_now and error not in AUTH_ERRORS:
        _user_notify(con, tg_id, "garmin_sync_failed", _USER_FAILED.format(n=n))
    return {"streak": n, "expired": expired_now, "due": due}


def _due(streak: int) -> bool:
    """Алертим на ALERT_AT, дальше каждые ALERT_EVERY прогонов."""
    if streak < ALERT_AT:
        return False
    return (streak - ALERT_AT) % ALERT_EVERY == 0


def _text(failed: list[tuple], recovered: list[str]) -> str:
    lines = []
    if failed:
        lines.append("⚠️ FePra: Garmin-синк падает")
        for who, streak, error in failed:
            runs = _plural(streak, "прогон", "прогона", "прогонов")
            lines.append(f"{who}: {error or 'неизвестная ошибка'}, {streak} {runs} подряд")
        if any(e in AUTH_ERRORS for _, _, e in failed):
            lines.append(_RECONNECT_HINT)
    if recovered:
        if lines:
            lines.append("")
        lines.append("✅ FePra: Garmin-синк снова работает: " + ", ".join(recovered))
    return "\n".join(lines)


def apply(db_path, results: list[dict]) -> dict:
    """results — выхлоп server_sync.py: [{"tg_id": …, "ok": bool, "error": …}, …].

    Возвращает сводку по побочным эффектам (для лога крона)."""
    expired, failed, recovered = [], [], []
    recovered_labels, alerted = [], []
    con = botdb.connect(db_path)
    try:
        for r in results:
            tg_id = r.get("tg_id")
            if tg_id is None:
                continue
            if r.get("ok"):
                if record_success(con, tg_id):
                    recovered.append(tg_id)
                    recovered_labels.append(_label(con, tg_id))
                continue
            error = r.get("error")
            res = record_failure(con, tg_id, error)
            if res["expired"]:
                expired.append(tg_id)
            if res["due"]:
                failed.append((_label(con, tg_id), res["streak"], error))
                alerted.append(tg_id)
    finally:
        con.close()

    return {"expired": expired, "alerted": alerted, "recovered": recovered,
            "notified": notify(failed, recovered_labels)}


def notify(failed: list[tuple], recovered: list[str]) -> bool:
    """Сообщение админам. Сбой отправки глотаем: телеграм не должен ронять крон."""
    if not failed and not recovered:
        return False
    token = tg_notify.bot_token()
    if not token:
        return False
    text = _text(failed, recovered)
    sent = False
    for admin_id in sorted(access.load_admins()):
        try:
            tg_notify.send(token, admin_id, text)
            sent = True
        except OSError:
            pass
    return sent
