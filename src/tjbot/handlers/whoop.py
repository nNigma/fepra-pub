"""Подключение Whoop: OAuth-ссылка из бота, ручной синк, отключение."""
from __future__ import annotations

import asyncio
from urllib.parse import quote

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from tj import i18n
from tj.adapters import whoop as whoopmod
from ..access import restricted


def auth_url(client_id: str, redirect: str, state: str) -> str:
    return (f"{whoopmod.AUTH_URL}?response_type=code&client_id={quote(client_id)}"
            f"&redirect_uri={quote(redirect, safe='')}&scope={quote(whoopmod.SCOPES)}"
            f"&state={quote(state)}")


@restricted
async def whoop_connect_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    from tjapp.whoop_oauth import redirect_uri, whoop_creds
    q = update.callback_query
    uid = q.from_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        cid, _ = whoop_creds()
        if not cid:
            await q.answer()
            await update.effective_message.reply_text(i18n.t("whoop.not_configured", lang))
            return
        state = botdb.oauth_state_issue(con, uid, "whoop")
    finally:
        con.close()
    await q.answer()
    await update.effective_message.reply_text(
        i18n.t("whoop.link_msg", lang, url=auth_url(cid, redirect_uri(), state)))


@restricted
async def whoop_sync_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    from .. import whoop_sync
    uid = update.callback_query.from_user.id
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid)
    con.close()
    await update.callback_query.answer()
    await update.effective_message.reply_text(i18n.t("whoop.syncing", lang))
    res = await asyncio.to_thread(whoop_sync.sync_recent, context.bot_data["db_path"], uid)
    if "error" in res:
        await update.effective_message.reply_text(
            i18n.t("whoop.sync_error", lang, err=res["error"]))
    else:
        await update.effective_message.reply_text(
            i18n.t("whoop.synced", lang, days=res["days"], acts=res["activities"]))


@restricted
async def whoop_disconnect_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    from .. import whoop_sync
    q = update.callback_query
    uid = q.from_user.id
    db_path = context.bot_data["db_path"]

    def _revoke():
        try:
            whoop_sync._client(db_path, uid).delete("/user/access")
        except Exception:
            pass

    await asyncio.to_thread(_revoke)
    con = botdb.connect(db_path)
    try:
        lang = botdb.user_lang(con, uid)
        botdb.whoop_tokens_delete(con, uid)
        botdb.watch_account_set_status(con, uid, "whoop", "revoked")
    finally:
        con.close()
    await q.answer(i18n.t("whoop.disconnected", lang))


def register(app) -> None:
    app.add_handler(CallbackQueryHandler(whoop_connect_cb, pattern=r"^wconnect:whoop$"))
    app.add_handler(CallbackQueryHandler(whoop_sync_cb, pattern=r"^wsync:whoop$"))
    app.add_handler(CallbackQueryHandler(whoop_disconnect_cb, pattern=r"^wdisc:whoop$"))
