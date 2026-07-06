"""Локальный запуск Mini App:

    PYTHONPATH=src .venv/bin/python -m tjapp.server

Слушает 127.0.0.1:8000. Наружу — через cloudflared-тоннель (HTTPS обязателен
для Telegram Mini App). URL тоннеля кладём в miniapp_url.txt, бот читает его.
"""
from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("tjapp.api:app", host="127.0.0.1",
                port=int(os.environ.get("TJAPP_PORT", "8000")), log_level="warning")
