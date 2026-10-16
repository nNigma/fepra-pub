"""Служебные сообщения в Telegram: алерты серверных кронов.

Раньше эти две функции жили приватными в claude_review, но алерту Garmin-синка
незачем тащить за собой весь LLM-стек этого модуля, поэтому они переехали сюда,
а claude_review делегирует. Сбой отправки не глотаем — это делает вызывающий,
чтобы упавший телеграм не ронял крон.
"""
from __future__ import annotations

import json
import os
import urllib.request


def bot_token() -> str | None:
    from tj import config as cfgmod
    try:
        env = cfgmod.load_dotenv(cfgmod.default_env_path())
    except OSError:
        env = {}
    for k in ("TG_FEPRA_BOT_TOKEN", "TG_BOT_TOKEN"):
        tok = os.environ.get(k) or env.get(k)
        if tok:
            return tok
    return None


def send(token: str, chat_id: int, text: str) -> None:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()
