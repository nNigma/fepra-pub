"""Общее для роутов: соединение с миграциями, tz, перевод ошибок сервисов, формат ошибок валидации."""
from __future__ import annotations

import sqlite3

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from tj import config as cfgmod
from tj.services._schema import ensure
from tj.services.errors import ServiceError
from tjbot import db as botdb

MIGRATIONS = ("0022_uploads", "0023_activity_trash")


def _connect():
    """Соединение на запрос. Зависимость-генератор и сам обработчик FastAPI могут выполняться в разных
    потоках пула, поэтому check_same_thread=False (соединение всё равно используется последовательно, одним запросом)."""
    p = botdb.default_db_path()
    con = sqlite3.connect(str(p), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def open_con():
    """Новое соединение с гарантированными таблицами загрузок и корзины (для потоков jobs тоже)."""
    con = _connect()
    for m in MIGRATIONS:
        ensure(con, m)
    return con


def db_con():
    """FastAPI-зависимость: соединение на время запроса."""
    con = open_con()
    try:
        yield con
    finally:
        con.close()


def user_tz() -> str:
    """Часовой пояс атлета из config.toml [user].timezone; нет конфига — UTC."""
    try:
        return cfgmod.timezone(cfgmod.load_config())
    except Exception:
        return "UTC"


def lang_of(con, uid: int) -> str:
    try:
        return botdb.user_lang(con, uid)
    except Exception:
        return "ru"


def call(fn, *args, **kwargs):
    """Вызвать сервис; ServiceError -> HTTPException(status, detail)."""
    try:
        return fn(*args, **kwargs)
    except ServiceError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


def get_con():
    con = _connect()
    try:
        yield con
    finally:
        con.close()


def fields_error(errors: dict[str, str], status: int = 422) -> JSONResponse:
    """{detail: строка, fields: {поле: сообщение}} — detail всегда строка, как в остальном API."""
    return JSONResponse(status_code=status, content={
        "detail": "; ".join(errors.values()), "fields": errors})
