"""Публичный адрес FePra (FEPRA_PUBLIC_URL) и построение ссылок."""
from __future__ import annotations

import os

DEFAULT_PUBLIC_URL = "https://fepra.example"


def public_url() -> str:
    """FEPRA_PUBLIC_URL без хвостового слэша; по умолчанию плейсхолдер fepra.example."""
    return (os.environ.get("FEPRA_PUBLIC_URL") or DEFAULT_PUBLIC_URL).strip().rstrip("/")


def public_link(path: str) -> str:
    return f"{public_url()}/{path.lstrip('/')}"


def invite_url(token: str) -> str:
    return f"{public_url()}/app/#/invite/{token}"
