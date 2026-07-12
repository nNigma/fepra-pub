"""Валидация Telegram Mini App initData (HMAC-SHA256 с токеном бота).

Без валидации любой мог бы дёргать API как угодно. Плюс гейт по тому же
allowlist, что у бота — приложение приватное.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

_TOKEN_KEYS = ("TG_FEPRA_BOT_TOKEN", "TG_BOT_TOKEN")


class AuthError(Exception):
    pass


def bot_token() -> str:
    from tj import config as cfgmod

    env = cfgmod.load_dotenv(cfgmod.default_env_path())
    for k in _TOKEN_KEYS:
        tok = os.environ.get(k) or env.get(k)
        if tok:
            return tok
    raise AuthError("нет токена бота (TG_FEPRA_BOT_TOKEN)")


def validate_init_data(init_data: str, token: str | None = None, max_age_s: int = 86400) -> dict:
    """Проверить подпись initData. Вернуть user dict или бросить AuthError."""
    token = token or bot_token()
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        raise AuthError("нет hash в initData")
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()

    def _calc(p: dict) -> str:
        dcs = "\n".join(f"{k}={p[k]}" for k in sorted(p))
        return hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()

    # По спецификации data-check-string — все поля кроме hash (signature включён).
    # Часть клиентов считает hash без signature — пробуем и так (устойчиво к обоим).
    ok = hmac.compare_digest(_calc(pairs), received)
    if not ok and "signature" in pairs:
        ok = hmac.compare_digest(
            _calc({k: v for k, v in pairs.items() if k != "signature"}), received)
    if not ok:
        raise AuthError("подпись initData не совпала")
    if max_age_s > 0 and pairs.get("auth_date", "").isdigit():
        if time.time() - int(pairs["auth_date"]) > max_age_s:
            raise AuthError("initData устарел")
    return json.loads(pairs.get("user", "{}"))


def authorized_user(init_data: str) -> dict:
    """Валидация + проверка allowlist (как у бота)."""
    from tjbot.access import is_allowed

    user = validate_init_data(init_data)
    uid = user.get("id")
    if uid is None or not is_allowed(uid):
        raise AuthError("доступ закрыт")
    return user


def resolve_effective_user(requester_id, as_user, _load_allow=None, _load_admins=None):
    """Кого реально показываем. as_user действует, только если requester —
    админ и as_user в allowlist; иначе возвращаем самого requester."""
    if as_user is None:
        return requester_id
    from tjbot.access import is_admin as _is_admin, load_allow as _load
    load_allow = _load_allow or _load
    admins = _load_admins() if _load_admins else None
    is_adm = (int(requester_id) in admins) if admins is not None else _is_admin(requester_id)
    try:
        target = int(as_user)
    except (TypeError, ValueError):
        return requester_id
    if is_adm and target in load_allow():
        return target
    return requester_id
