"""Идентичность и вход без Telegram: веб-пользователи, инвайты, сессии, passkey.

Чистые функции над sqlite-соединением, без HTTP. Токены (инвайты, сессии) в БД
хранятся только хешами sha256; сырое значение отдаётся один раз при создании.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from tj.services.urls import public_url

# Выше любого Telegram id (< 2^52) и безопасно для JS (< 2^53 ≈ 9.007e15).
WEB_ID_BASE = 5_000_000_000_000_000

SESSION_TTL_DAYS = 60
SESSION_TOUCH_S = 300          # скользящий срок продлеваем не чаще раза в 5 минут
CHALLENGE_TTL_S = 300
INVITE_ROLES = ("user", "pro", "coach", "admin")
MAX_NICK = 40


class AuthFailure(Exception):
    """Ошибка входа с HTTP-кодом для роутов."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


# --------------------------------------------------------------------- время / хеши

def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode()).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


# --------------------------------------------------------------------- роли

def add_role(con: sqlite3.Connection, uid: int, role: str, gym: str | None = None) -> None:
    con.execute('INSERT INTO user_roles ("user_id","role","gym") VALUES (?,?,?) '
                'ON CONFLICT("user_id","role") DO UPDATE SET "gym"=excluded."gym"',
                (int(uid), role, gym))


def roles_of(con: sqlite3.Connection, uid: int) -> dict:
    rows = con.execute('SELECT "role","gym" FROM user_roles WHERE "user_id"=?', (int(uid),)).fetchall()
    have = {r[0]: r[1] for r in rows}
    return {"allowed": "allowlist" in have, "admin": "admin" in have,
            "pro": "pro" in have, "coach": "coach" in have, "coach_gym": have.get("coach")}


# --------------------------------------------------------------------- пользователи

def create_web_user(con: sqlite3.Connection, nick: str, now: datetime | None = None) -> int:
    """Новый пользователь без Telegram: id = max(веб-id)+1, начиная с WEB_ID_BASE."""
    nick = (nick or "").strip()
    if not nick or len(nick) > MAX_NICK:
        raise ValueError(f"ник: от 1 до {MAX_NICK} символов")
    created = iso(_now(now))
    for _ in range(5):
        r = con.execute('SELECT MAX("tg_id") FROM users WHERE "tg_id">=?', (WEB_ID_BASE,)).fetchone()
        uid = (r[0] + 1) if r and r[0] is not None else WEB_ID_BASE
        try:
            con.execute('INSERT INTO users ("tg_id","nick","lang","created_at") VALUES (?,?,?,?)',
                        (uid, nick, "ru", created))
        except sqlite3.IntegrityError:
            continue
        add_role(con, uid, "allowlist")
        con.commit()
        return uid
    raise RuntimeError("не удалось выдать id")


def user_exists(con: sqlite3.Connection, uid: int) -> bool:
    return con.execute('SELECT 1 FROM users WHERE "tg_id"=?', (int(uid),)).fetchone() is not None


# --------------------------------------------------------------------- инвайты

def create_invite(con: sqlite3.Connection, created_by: int | None, role: str = "user",
                  gym: str | None = None, existing_user_id: int | None = None,
                  ttl_hours: float = 72, note: str | None = None,
                  now: datetime | None = None) -> str:
    """Вернуть сырой токен (в БД только хеш)."""
    role = "user" if role == "athlete" else role           # интерфейс говорит «атлет», в БД «user»
    if role not in INVITE_ROLES:
        raise ValueError(f"роль: одна из {', '.join(INVITE_ROLES)}")
    if role == "coach" and not gym:
        raise ValueError("для тренера нужен зал (gym)")
    if not 0 < ttl_hours <= 24 * 30:
        raise ValueError("ttl_hours: от 0 до 720")
    if existing_user_id is not None and not user_exists(con, existing_user_id):
        raise ValueError("existing_user_id: такого пользователя нет")
    t = _now(now)
    raw = _new_token()
    con.execute(
        'INSERT INTO invites ("token_hash","created_by","role","gym","existing_user_id",'
        '"expires_at","note","created_at") VALUES (?,?,?,?,?,?,?,?)',
        (hash_token(raw), created_by, role, gym,
         int(existing_user_id) if existing_user_id is not None else None,
         iso(t + timedelta(hours=ttl_hours)), note, iso(t)))
    con.commit()
    return raw


def list_invites(con: sqlite3.Connection, now: datetime | None = None) -> list[dict]:
    t = iso(_now(now))
    out = []
    for r in con.execute('SELECT * FROM invites ORDER BY "created_at" DESC, rowid DESC'):
        d = dict(r)
        status = "used" if d["used_at"] else ("expired" if d["expires_at"] < t else "active")
        out.append({"id": d["token_hash"][:12], "role": d["role"], "gym": d["gym"],
                    "existing_user_id": d["existing_user_id"], "created_by": d["created_by"],
                    "created_at": d["created_at"], "expires_at": d["expires_at"],
                    "used_at": d["used_at"], "used_by": d["used_by"], "note": d["note"],
                    "status": status})
    return out


def invite_info(con: sqlite3.Connection, raw_token: str, now: datetime | None = None) -> dict:
    """Что за приглашение, не погашая его: {valid, existing, nick}. Для существующего пользователя
    (перенос аккаунта из Telegram) страница входа не спрашивает ник, а показывает чей это аккаунт."""
    row = con.execute('SELECT * FROM invites WHERE "token_hash"=?', (hash_token(raw_token or ""),)).fetchone()
    if row is None or row["used_at"] or row["expires_at"] < iso(_now(now)):
        return {"valid": False, "existing": False, "nick": None}
    ex = row["existing_user_id"]
    nick = None
    if ex is not None:
        u = con.execute('SELECT "nick" FROM users WHERE "tg_id"=?', (int(ex),)).fetchone()
        nick = u["nick"] if u else None
    return {"valid": True, "existing": ex is not None, "nick": nick}


def redeem_invite(con: sqlite3.Connection, raw_token: str, nick: str | None,
                  user_agent: str = "", now: datetime | None = None) -> tuple[int, str]:
    """Погасить инвайт (одноразово). Вернуть (user_id, сырой токен сессии)."""
    t = _now(now)
    th = hash_token(raw_token)
    row = con.execute('SELECT * FROM invites WHERE "token_hash"=?', (th,)).fetchone()
    if row is None:
        raise AuthFailure(400, "приглашение не найдено")
    if row["used_at"]:
        raise AuthFailure(400, "приглашение уже использовано")
    if row["expires_at"] < iso(t):
        raise AuthFailure(400, "приглашение просрочено")
    existing = row["existing_user_id"]
    if existing is None:
        try:
            nick_ok = (nick or "").strip()
            if not nick_ok:
                raise ValueError("ник: от 1 до 40 символов")
            if len(nick_ok) > MAX_NICK:
                raise ValueError(f"ник: от 1 до {MAX_NICK} символов")
        except ValueError as e:
            raise AuthFailure(422, str(e))
    # Атомарное погашение: выигрывает один из параллельных запросов.
    cur = con.execute('UPDATE invites SET "used_at"=? WHERE "token_hash"=? AND "used_at" IS NULL',
                      (iso(t), th))
    if cur.rowcount != 1:
        con.rollback()
        raise AuthFailure(400, "приглашение уже использовано")
    uid = int(existing) if existing is not None else create_web_user(con, nick, now=t)
    add_role(con, uid, "allowlist")
    role = row["role"]
    if role == "pro":
        add_role(con, uid, "pro")
    elif role == "coach":
        add_role(con, uid, "coach", row["gym"])
    elif role == "admin":
        add_role(con, uid, "admin")
    con.execute('UPDATE invites SET "used_by"=? WHERE "token_hash"=?', (uid, th))
    con.execute('INSERT OR IGNORE INTO auth_identities ("provider","subject","user_id","created_at") '
                'VALUES (\'invite\',?,?,?)', (th, uid, iso(t)))
    con.commit()
    return uid, create_session(con, uid, user_agent=user_agent, now=t)


# --------------------------------------------------------------------- сессии

def create_session(con: sqlite3.Connection, uid: int, user_agent: str = "",
                   now: datetime | None = None) -> str:
    t = _now(now)
    raw = _new_token()
    con.execute('INSERT INTO sessions ("token_hash","user_id","created_at","last_seen",'
                '"expires_at","user_agent") VALUES (?,?,?,?,?,?)',
                (hash_token(raw), int(uid), iso(t), iso(t),
                 iso(t + timedelta(days=SESSION_TTL_DAYS)), (user_agent or "")[:300]))
    con.commit()
    return raw


def validate_session(con: sqlite3.Connection, raw: str | None,
                     now: datetime | None = None) -> int | None:
    """user_id по сессии или None. Продлевает срок (скользящие 60 дней)."""
    if not raw:
        return None
    t = _now(now)
    th = hash_token(raw)
    r = con.execute('SELECT "user_id","last_seen","expires_at" FROM sessions WHERE "token_hash"=?',
                    (th,)).fetchone()
    if r is None:
        return None
    if r["expires_at"] < iso(t):
        con.execute('DELETE FROM sessions WHERE "token_hash"=?', (th,))
        con.commit()
        return None
    try:
        last = datetime.strptime(r["last_seen"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        last = None
    if last is None or (t - last).total_seconds() >= SESSION_TOUCH_S:
        con.execute('UPDATE sessions SET "last_seen"=?,"expires_at"=? WHERE "token_hash"=?',
                    (iso(t), iso(t + timedelta(days=SESSION_TTL_DAYS)), th))
        con.commit()
    return int(r["user_id"])


def revoke_session(con: sqlite3.Connection, raw: str | None) -> bool:
    if not raw:
        return False
    cur = con.execute('DELETE FROM sessions WHERE "token_hash"=?', (hash_token(raw),))
    con.commit()
    return cur.rowcount > 0


def revoke_user_sessions(con: sqlite3.Connection, uid: int) -> int:
    cur = con.execute('DELETE FROM sessions WHERE "user_id"=?', (int(uid),))
    con.commit()
    return cur.rowcount


# --------------------------------------------------------------------- /api/me

def get_me(con: sqlite3.Connection, uid: int) -> dict:
    u = con.execute('SELECT "nick","lang","gym" FROM users WHERE "tg_id"=?', (int(uid),)).fetchone()
    roles = roles_of(con, uid)
    g = None
    try:
        g = con.execute('SELECT "status" FROM garmin_accounts WHERE "tg_id"=?', (int(uid),)).fetchone()
    except sqlite3.OperationalError:
        pass
    has_pk = con.execute('SELECT 1 FROM passkeys WHERE "user_id"=? LIMIT 1', (int(uid),)).fetchone()
    return {
        "id": int(uid),
        "nick": u["nick"] if u else None,
        "lang": (u["lang"] if u and u["lang"] in ("ru", "en") else "ru"),
        "roles": {"admin": roles["admin"], "pro": roles["pro"], "coach": roles["coach"]},
        "gym": roles["coach_gym"] or (u["gym"] if u else None),
        "has_passkey": has_pk is not None,
        "garmin": ({"connected": g["status"] == "ok", "status": g["status"]} if g else None),
        "public_url": public_url(),
    }


# --------------------------------------------------------------------- passkey (WebAuthn)

def rp_id() -> str:
    from urllib.parse import urlparse
    return urlparse(public_url()).hostname or "localhost"


def rp_origin() -> str:
    return public_url()


def _store_challenge(con, uid: int | None, challenge: bytes, purpose: str, now: datetime) -> str:
    cid = secrets.token_urlsafe(16)
    con.execute('DELETE FROM webauthn_challenges WHERE "expires_at"<?', (iso(now),))
    con.execute('INSERT INTO webauthn_challenges ("id","user_id","challenge","purpose","expires_at") '
                'VALUES (?,?,?,?,?)',
                (cid, uid, bytes_to_base64url(challenge), purpose,
                 iso(now + timedelta(seconds=CHALLENGE_TTL_S))))
    con.commit()
    return cid


def _take_challenge(con, cid: str, purpose: str, uid: int | None, now: datetime) -> bytes:
    """Достать и удалить challenge (одноразовый). Ошибка, если нет/протух/чужой."""
    r = con.execute('SELECT * FROM webauthn_challenges WHERE "id"=?', (cid or "",)).fetchone()
    if r is None:
        raise AuthFailure(400, "challenge не найден или уже использован")
    con.execute('DELETE FROM webauthn_challenges WHERE "id"=?', (cid,))
    con.commit()
    if r["expires_at"] < iso(now):
        raise AuthFailure(400, "challenge просрочен")
    if r["purpose"] != purpose:
        raise AuthFailure(400, "challenge для другой операции")
    if r["user_id"] is not None and (uid is None or int(r["user_id"]) != int(uid)):
        raise AuthFailure(403, "challenge выдан другому пользователю")
    return base64url_to_bytes(r["challenge"])


def passkey_register_options(con, uid: int, now: datetime | None = None) -> dict:
    t = _now(now)
    u = con.execute('SELECT "nick" FROM users WHERE "tg_id"=?', (int(uid),)).fetchone()
    nick = (u["nick"] if u and u["nick"] else str(uid))
    existing = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(r["credential_id"]))
                for r in con.execute('SELECT "credential_id" FROM passkeys WHERE "user_id"=?', (int(uid),))]
    opts = generate_registration_options(
        rp_id=rp_id(), rp_name="FePra", user_id=str(int(uid)).encode(), user_name=nick,
        user_display_name=nick, exclude_credentials=existing,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED))
    cid = _store_challenge(con, int(uid), opts.challenge, "register", t)
    return {"challenge_id": cid, "options": json.loads(options_to_json(opts))}


def _cred_id(credential) -> str:
    cid = credential.get("id") if isinstance(credential, dict) else None
    if not cid or not isinstance(cid, str):
        raise AuthFailure(422, "в credential нет id")
    return cid


def passkey_register_verify(con, uid: int, challenge_id: str, credential: dict,
                            name: str | None = None, now: datetime | None = None) -> str:
    """Проверить регистрацию и сохранить passkey. Вернуть credential_id."""
    t = _now(now)
    challenge = _take_challenge(con, challenge_id, "register", uid, t)
    try:
        v = verify_registration_response(
            credential=credential, expected_challenge=challenge,
            expected_rp_id=rp_id(), expected_origin=rp_origin())
    except Exception as e:  # библиотека бросает разные InvalidRegistrationResponse
        raise AuthFailure(400, f"passkey не подтверждён: {e}")
    cred_id = bytes_to_base64url(v.credential_id)
    transports = None
    if isinstance(credential, dict):
        tr = (credential.get("response") or {}).get("transports")
        transports = json.dumps(tr) if tr else None
    try:
        con.execute('INSERT INTO passkeys ("credential_id","user_id","public_key","sign_count",'
                    '"transports","created_at","name") VALUES (?,?,?,?,?,?,?)',
                    (cred_id, int(uid), v.credential_public_key, int(v.sign_count),
                     transports, iso(t), (name or "").strip()[:60] or None))
    except sqlite3.IntegrityError:
        raise AuthFailure(409, "этот passkey уже зарегистрирован")
    con.execute('INSERT OR IGNORE INTO auth_identities ("provider","subject","user_id","created_at") '
                'VALUES (\'passkey\',?,?,?)', (cred_id, int(uid), iso(t)))
    con.commit()
    return cred_id


def passkey_login_options(con, now: datetime | None = None) -> dict:
    """Discoverable credential: список разрешённых пуст, аккаунт выберет устройство."""
    t = _now(now)
    opts = generate_authentication_options(
        rp_id=rp_id(), user_verification=UserVerificationRequirement.PREFERRED)
    cid = _store_challenge(con, None, opts.challenge, "login", t)
    return {"challenge_id": cid, "options": json.loads(options_to_json(opts))}


def passkey_login_verify(con, challenge_id: str, credential: dict, user_agent: str = "",
                         now: datetime | None = None) -> tuple[int, str]:
    """Проверить вход по passkey. Вернуть (user_id, сырой токен сессии)."""
    t = _now(now)
    challenge = _take_challenge(con, challenge_id, "login", None, t)
    cred_id = _cred_id(credential)
    row = con.execute('SELECT * FROM passkeys WHERE "credential_id"=?', (cred_id,)).fetchone()
    if row is None:
        raise AuthFailure(401, "passkey не найден")
    try:
        v = verify_authentication_response(
            credential=credential, expected_challenge=challenge,
            expected_rp_id=rp_id(), expected_origin=rp_origin(),
            credential_public_key=bytes(row["public_key"]),
            credential_current_sign_count=int(row["sign_count"] or 0))
    except Exception as e:
        raise AuthFailure(401, f"passkey не подтверждён: {e}")
    old, new = int(row["sign_count"] or 0), int(v.new_sign_count)
    # Счётчик должен расти; 0/0 допустимо (часть платформенных ключей его не ведут).
    if (old or new) and new <= old:
        raise AuthFailure(401, "sign_count не вырос: возможен клон ключа")
    uid = int(row["user_id"])
    con.execute('UPDATE passkeys SET "sign_count"=? WHERE "credential_id"=?', (new, cred_id))
    con.commit()
    if not roles_of(con, uid)["allowed"]:
        raise AuthFailure(403, "доступ закрыт")
    return uid, create_session(con, uid, user_agent=user_agent, now=t)
