"""Онбординг часов-компаньонов (Samsung через Health Connect) + Apple через Health Auto Export."""
from __future__ import annotations

import os

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from tj import i18n
from tj.services.urls import public_link
from ..access import restricted


def apk_url() -> str:
    return os.environ.get("FEPRA_APK_URL") or public_link("/fepra-connect.apk")


def connect_message(link: str, token: str, lang: str) -> str:
    return i18n.t("watch.samsung_msg", lang, link=link, token=token)


@restricted
async def samsung_connect_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    q = update.callback_query
    uid = q.from_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        token = botdb.issue_watch_token(con, uid, "samsung")
    finally:
        con.close()
    await q.answer()
    await update.effective_message.reply_text(connect_message(apk_url(), token, lang))


@restricted
async def samsung_disconnect_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    q = update.callback_query
    uid = q.from_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        botdb.watch_account_set_status(con, uid, "samsung", "revoked")
    finally:
        con.close()
    await q.answer(i18n.t("watch.samsung_disconnected", lang))


def apple_ingest_url() -> str:
    return os.environ.get("FEPRA_APPLE_URL") or public_link("/ingest/apple")


@restricted
async def apple_connect_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    q = update.callback_query
    uid = q.from_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        token = botdb.issue_watch_token(con, uid, "apple")
    finally:
        con.close()
    await q.answer()
    await update.effective_message.reply_text(
        i18n.t("watch.apple_msg", lang, url=apple_ingest_url(), token=token))


@restricted
async def apple_disconnect_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    q = update.callback_query
    uid = q.from_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        botdb.watch_account_set_status(con, uid, "apple", "revoked")
    finally:
        con.close()
    await q.answer(i18n.t("watch.apple_disconnected", lang))


def register(app) -> None:
    app.add_handler(CallbackQueryHandler(samsung_connect_cb, pattern=r"^wconnect:samsung$"))
    app.add_handler(CallbackQueryHandler(samsung_disconnect_cb, pattern=r"^wdisc:samsung$"))
    app.add_handler(CallbackQueryHandler(apple_connect_cb, pattern=r"^wconnect:apple$"))
    app.add_handler(CallbackQueryHandler(apple_disconnect_cb, pattern=r"^wdisc:apple$"))
