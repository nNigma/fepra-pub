"""Реестр роутеров API.

Каждый модуль в этом пакете (кроме начинающихся с `_`) экспортирует
`router = APIRouter()`; `ALL_ROUTERS` собирается автоматически, поэтому новые
роуты не требуют правки этого файла (параллельные ветки не конфликтуют).
"""
from __future__ import annotations

import importlib
import pkgutil

ALL_ROUTERS: list = []

for _m in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
    if _m.name.startswith("_"):
        continue
    _mod = importlib.import_module(f"{__name__}.{_m.name}")
    _r = getattr(_mod, "router", None)
    if _r is not None:
        ALL_ROUTERS.append(_r)
