"""Раздача PWA (сборка Vite из web/) по /app/.

Сборка лежит в src/tjapp/static/app/ и коммитится в репозиторий (deploy заливает
только src/). Роутинг на клиенте hash-овый, но на всякий случай любой путь без
расширения отдаёт index.html (SPA-fallback).

Кэш: index.html, sw.js и манифест — no-cache (иначе оболочка не обновится),
файлы assets/ имеют хэш в имени — кэшируются надолго.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

APP_DIR = Path(__file__).resolve().parent / "static" / "app"
_NO_CACHE = "no-cache"
_NO_CACHE_NAMES = {"index.html", "sw.js", "registerSW.js", "manifest.webmanifest"}


class SpaStaticFiles(StaticFiles):
    """StaticFiles(html=True) + SPA-fallback + политика Cache-Control."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            resp = await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code != 404 or "." in Path(path).name:
                raise
            resp = await super().get_response("index.html", scope)
            path = "index.html"
        name = Path(path).name or "index.html"
        if path in ("", ".", "/") or name in _NO_CACHE_NAMES:
            resp.headers["Cache-Control"] = _NO_CACHE
        elif path.startswith("assets/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            resp.headers["Cache-Control"] = _NO_CACHE
        return resp


def mount(app: FastAPI, directory: Path | None = None) -> None:
    """Подключить /app/. Если сборки нет (dev без npm run build) — тихо пропускаем."""
    d = Path(directory) if directory else APP_DIR
    if not d.is_dir():
        return
    app.mount("/app", SpaStaticFiles(directory=str(d), html=True), name="webapp")
