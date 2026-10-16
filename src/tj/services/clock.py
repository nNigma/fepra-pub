"""Часы сервисов: «сегодня» в часовом поясе из config.toml [user].timezone (иначе UTC).
Сервисы принимают today параметром; роуты берут его отсюда."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def tz_name() -> str:
    try:
        from tj import config as cfgmod
        return cfgmod.timezone(cfgmod.load_config())
    except Exception:  # нет config.toml и т.п.
        return "UTC"


def today() -> date:
    try:
        return datetime.now(ZoneInfo(tz_name())).date()
    except Exception:
        return datetime.now(timezone.utc).date()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
