"""Общие помощники тестов сервисов записи тренировки (tj.services.*)."""
from __future__ import annotations

import importlib

from tjbot import db as botdb

BOARD = """Актив.
2 сета:
- 10 гиперэкстензий

2 ТА.
- Е2МОМх5х5х80%
приседание со штангой на спине
- Е1,5МОМх5х70%-80%
2 взятия на грудь + толчок в ножницы

3 WOD
3 сета:
- 20 прыжки через бокс
- 15 фронтальный присед с гантелью

4 AMRAP 3 мин х 5 / 1 мин отдых
- 16 рывков
- 8 подтягивания
- 4 челночный бег
"""


def migrate(con) -> None:
    """Схема бота + миграции 0020-0021 (напрямую, реестр миграций живёт в другой ветке)."""
    botdb.init_schema(con)
    for name in ("0022_uploads", "0023_activity_trash"):
        importlib.import_module(f"tj.migrations.{name}").upgrade(con)


def make_con(tmp_path, name="t.db"):
    con = botdb.connect(tmp_path / name)
    migrate(con)
    return con


def fill_by(form, mapping: dict) -> dict:
    """{подстрока метки (в порядке появления): значение} -> {ключ поля: значение}.
    Подстрока может повторяться через '#n' (n-е совпадение, с нуля)."""
    out = {}
    fields = [f for b in form["blocks"] for f in b["fields"]]
    for spec, val in mapping.items():
        needle, _, nth = spec.partition("#")
        n = int(nth) if nth else 0
        hits = [f for f in fields if needle in f["label"]]
        out[hits[n]["key"]] = val
    return out
