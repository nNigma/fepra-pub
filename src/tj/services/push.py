"""Web Push: подписки, отправка, общий канал уведомлений ``notify_user``.

VAPID-ключи только из env (FEPRA_VAPID_PRIVATE / FEPRA_VAPID_PUBLIC /
FEPRA_VAPID_SUBJECT, либо из .env проекта). Нет ключей — отправка тихо
пропускается, уведомление остаётся в user_notices.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from . import notices
from ._schema import ensure

_MIG = "0041_push_subscriptions"
WEB_ID_BASE = 5_000_000_000_000_000
_GONE = (404, 410)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    if val:
        return val
    try:
        from tj import config as cfgmod
        return cfgmod.load_dotenv(cfgmod.default_env_path()).get(name) or None
    except Exception:
        return None


def vapid_config() -> dict | None:
    priv, pub = _env("FEPRA_VAPID_PRIVATE"), _env("FEPRA_VAPID_PUBLIC")
    if not priv or not pub:
        return None
    return {"private": priv, "public": pub,
            "subject": _env("FEPRA_VAPID_SUBJECT") or "mailto:admin@example.com"}


def public_key() -> str | None:
    cfg = vapid_config()
    return cfg["public"] if cfg else None


def subscribe(con, uid: int, endpoint: str, p256dh: str, auth: str, ua: str | None = None) -> str:
    """Идемпотентно по endpoint: повторная подписка (в т.ч. удалённой или чужой) оживляет
    строку и переписывает владельца."""
    if not endpoint or not p256dh or not auth:
        raise ValueError("endpoint, p256dh и auth обязательны")
    ensure(con, _MIG)
    row = con.execute('SELECT "id" FROM push_subscriptions WHERE "endpoint"=?', (endpoint,)).fetchone()
    if row:
        con.execute('UPDATE push_subscriptions SET "uid"=?,"p256dh"=?,"auth"=?,"ua"=?,"deleted_at"=NULL '
                    'WHERE "id"=?', (int(uid), p256dh, auth, ua, row["id"]))
        sid = row["id"]
    else:
        sid = str(uuid.uuid4())
        con.execute('INSERT INTO push_subscriptions ("id","uid","endpoint","p256dh","auth","ua","created_at") '
                    'VALUES (?,?,?,?,?,?,?)', (sid, int(uid), endpoint, p256dh, auth, ua, _now()))
    con.commit()
    return sid


def unsubscribe(con, uid: int, endpoint: str) -> bool:
    ensure(con, _MIG)
    cur = con.execute('UPDATE push_subscriptions SET "deleted_at"=? WHERE "uid"=? AND "endpoint"=? '
                      'AND "deleted_at" IS NULL', (_now(), int(uid), endpoint))
    con.commit()
    return cur.rowcount > 0


def subscriptions(con, uid: int) -> list[dict]:
    ensure(con, _MIG)
    return [dict(r) for r in con.execute(
        'SELECT "id","endpoint","p256dh","auth","ua","created_at" FROM push_subscriptions '
        'WHERE "uid"=? AND "deleted_at" IS NULL ORDER BY "created_at"', (int(uid),)).fetchall()]


def _webpush(sub_info: dict, payload: str, cfg: dict) -> None:
    """Обёртка над pywebpush (в тестах подменяется)."""
    from pywebpush import webpush
    webpush(subscription_info=sub_info, data=payload, vapid_private_key=cfg["private"],
            vapid_claims={"sub": cfg["subject"]}, ttl=24 * 3600)


def _status_of(exc: Exception):
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None)


def send(con, uid: int, title: str, body: str = "", url: str | None = None,
         tag: str | None = None) -> dict:
    """Отправить push на все подписки пользователя. 404/410 — мягко удаляем подписку.
    Возвращает {"sent","removed","failed","skipped"}; сбой одной подписки не мешает остальным."""
    out = {"sent": 0, "removed": 0, "failed": 0, "skipped": None}
    cfg = vapid_config()
    if not cfg:
        out["skipped"] = "no_vapid"
        return out
    subs = subscriptions(con, uid)
    if not subs:
        out["skipped"] = "no_subscriptions"
        return out
    payload = json.dumps({"title": title, "body": body, "url": url or "/app/", "tag": tag},
                         ensure_ascii=False)
    for s in subs:
        info = {"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}}
        try:
            _webpush(info, payload, cfg)
            out["sent"] += 1
        except Exception as e:  # noqa: BLE001 — pywebpush бросает WebPushException, сеть — OSError
            if _status_of(e) in _GONE:
                con.execute('UPDATE push_subscriptions SET "deleted_at"=? WHERE "id"=?', (_now(), s["id"]))
                con.commit()
                out["removed"] += 1
            else:
                out["failed"] += 1
                print(f"[push] send failed: {type(e).__name__}", flush=True)
    return out


def _tg_send(uid: int, text: str) -> bool:
    """Запасной канал, пока жив бот. Только для настоящих Telegram-id."""
    if int(uid) >= WEB_ID_BASE or os.environ.get("FEPRA_NOTIFY_TG") == "0" \
            or "PYTEST_CURRENT_TEST" in os.environ:
        return False       # веб-пользователь / выключено / тесты не ходят в сеть
    try:
        from tjbot import tg_notify
        token = tg_notify.bot_token()
        if not token:
            return False
        tg_notify.send(token, int(uid), text)
        return True
    except Exception:  # noqa: BLE001 — телеграм не должен ронять крон
        return False


def notify_user(con, uid: int, kind: str, text: str, title: str = "FePra",
                url: str | None = None, tag: str | None = None, tg: bool = False,
                dedupe: bool = True) -> dict:
    """Общий канал: запись в user_notices + push (если подписан) + опционально Telegram.
    Каждый канал независим: сбой одного не отменяет остальных."""
    nid = None
    try:
        nid = notices.add(con, uid, kind, text, dedupe=dedupe)
    except Exception as e:  # noqa: BLE001
        print(f"[push] notice failed: {type(e).__name__}", flush=True)
    res = {"notice_id": nid, "push": None, "tg": False}
    if nid is None and dedupe:
        return res  # такое же непрочитанное уже висит — не спамим повторно
    try:
        res["push"] = send(con, uid, title, text, url=url, tag=tag or kind)
    except Exception as e:  # noqa: BLE001
        print(f"[push] send crashed: {type(e).__name__}", flush=True)
    if tg:
        res["tg"] = _tg_send(uid, f"{title}: {text}")
    return res


# --- плановые пуши ------------------------------------------------------------

def _table_cols(con, table: str) -> set[str]:
    return {r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()}


def program_sessions_today(con, uid: int, today: str) -> int:
    """Число запланированных на `today` сессий программ без привязанной тренировки
    (схема — миграция 0030). Нет таблиц или колонок — молча 0."""
    try:
        se, en = _table_cols(con, "program_sessions"), _table_cols(con, "program_enrollments")
        if not ({"enrollment_id", "planned_day", "activity_id"} <= se
                and {"id", "uid", "status", "deleted_at"} <= en):
            return 0
        sql = ('SELECT COUNT(*) FROM program_sessions s JOIN program_enrollments e ON e.id=s.enrollment_id '
               'WHERE e.uid=? AND s.planned_day=? AND s.activity_id IS NULL '
               "AND e.status='active' AND e.deleted_at IS NULL "
               "AND s.status IN ('planned','in_progress')")
        return int(con.execute(sql, (int(uid), today)).fetchone()[0])
    except Exception:  # noqa: BLE001 — чужая схема не должна ронять крон
        return 0


def _daily_key(kind: str, uid: int) -> str:
    return f"push_daily:{kind}:{int(uid)}"


def _sent_today(con, kind: str, uid: int, today: str) -> bool:
    r = con.execute('SELECT "value" FROM meta WHERE "key"=?', (_daily_key(kind, uid),)).fetchone()
    return bool(r) and r["value"] == today


def _mark_today(con, kind: str, uid: int, today: str) -> None:
    con.execute('INSERT OR REPLACE INTO meta ("key","value") VALUES (?,?)', (_daily_key(kind, uid), today))
    con.commit()


def notify_program_today(con, uid: int, today: str, n: int | None = None) -> dict | None:
    """Push «программа на сегодня»: раз в день на пользователя, только если есть сессия.
    -> результат notify_user или None (нечего слать / уже слали)."""
    if _sent_today(con, "program_today", uid, today):
        return None
    n = program_sessions_today(con, uid, today) if n is None else n
    if n <= 0:
        return None
    text = "Сегодня по плану тренировка из программы" if n == 1 else f"Сегодня по плану тренировок: {n}"
    _mark_today(con, "program_today", uid, today)
    return notify_user(con, uid, "program_today", text, title="Программа на сегодня",
                       url="/app/#/program", tag=f"program-{today}", dedupe=False)


def notify_rest_over(con, uid: int, exercise: str | None = None) -> dict:
    """Push «отдых закончен» (серверный, на случай заблокированного экрана).
    Эфемерный: только push, в user_notices не пишем."""
    body = f"Пора на следующий подход: {exercise}" if exercise else "Пора на следующий подход"
    return send(con, uid, "Отдых закончен", body, url="/app/#/programs", tag="rest-over")


def push_users(con) -> list[int]:
    ensure(con, _MIG)
    return [r[0] for r in con.execute(
        'SELECT DISTINCT "uid" FROM push_subscriptions WHERE "deleted_at" IS NULL ORDER BY "uid"').fetchall()]


def run_daily(con, today: str, hour: int, from_hour: int = 7) -> dict:
    """Часовой проход для server_notify.py: «программа на сегодня» тем, у кого есть подписка."""
    out = {"checked": 0, "sent": []}
    if hour < from_hour:
        return out
    for uid in push_users(con):
        out["checked"] += 1
        try:
            if notify_program_today(con, uid, today):
                out["sent"].append(uid)
        except Exception as e:  # noqa: BLE001 — один пользователь не роняет проход
            print(f"[notify] {uid}: {type(e).__name__}", flush=True)
    return out
