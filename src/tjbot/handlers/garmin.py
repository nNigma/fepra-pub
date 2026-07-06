"""Подключение Garmin: email -> пароль (удаляем) -> логин в потоке (MFA через
GarminConnectSession) -> сохраняем per-user токен. Пароль не персистится."""
from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import (ContextTypes, ConversationHandler, MessageHandler,
                          CommandHandler, CallbackQueryHandler, filters)

from tj import i18n
from tj.adapters.garmin import GarminAdapter
from .. import activity
from .. import db as botdb
from ..access import restricted
from ..garmin_connect import GarminConnectSession
from . import menu

ASK_EMAIL, ASK_PASSWORD, ASK_MFA = range(3)

_PENDING_ROUNDS = 6
_PENDING_STEP = 10


def _tz():
    from tj import config as cfgmod
    try:
        cfg = cfgmod.load_config()
    except Exception:
        return "UTC"
    return cfgmod.timezone(cfg)


def _adapter_factory(tz):
    def factory(email, password, tokenstore, prompt_mfa):
        return GarminAdapter(email, password, tokenstore, tz, prompt_mfa=prompt_mfa)
    return factory


async def _wait_out_pending(session) -> str:
    state = await asyncio.to_thread(session.wait_state, _PENDING_STEP)
    rounds = 1
    while state == "pending" and rounds < _PENDING_ROUNDS:
        state = await asyncio.to_thread(session.wait_state, _PENDING_STEP)
        rounds += 1
    return state


async def _lang_for(context: ContextTypes.DEFAULT_TYPE, uid: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = await _lang_for(context, update.effective_user.id)
    context.user_data["lang"] = lang
    await update.effective_message.reply_text(i18n.t("garmin.ask_email", lang))
    return ASK_EMAIL


async def got_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang") or await _lang_for(context, update.effective_user.id)
    context.user_data["g_email"] = update.effective_message.text.strip()
    await update.effective_message.reply_text(i18n.t("garmin.ask_password", lang))
    return ASK_PASSWORD


async def got_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password = update.effective_message.text
    try:
        await update.effective_message.delete()
    except Exception:
        pass
    email = context.user_data.get("g_email")
    tg_id = update.effective_user.id
    session = GarminConnectSession(_adapter_factory(_tz()))
    context.user_data["g_session"] = session
    session.start_login(email, password, str(botdb.garmin_tokenstore(tg_id)))
    state = await _wait_out_pending(session)
    return await _after_login(update, context, state)


async def got_mfa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang") or await _lang_for(context, update.effective_user.id)
    session = context.user_data.get("g_session")
    if not session:
        await update.effective_message.reply_text(i18n.t("garmin.session_lost", lang))
        return ConversationHandler.END
    session.submit_mfa(update.effective_message.text.strip())
    state = await _wait_out_pending(session)
    return await _after_login(update, context, state)


async def _after_login(update, context, state) -> int:
    tg_id = update.effective_user.id
    lang = context.user_data.get("lang") or await _lang_for(context, tg_id)
    if state == "need_mfa":
        await update.effective_message.reply_text(i18n.t("garmin.ask_mfa", lang))
        return ASK_MFA
    if state == "pending":
        await update.effective_message.reply_text(i18n.t("garmin.login_pending", lang))
        context.user_data.pop("g_session", None)
        context.user_data.pop("g_email", None)
        return ConversationHandler.END
    con = botdb.connect(context.bot_data["db_path"])
    try:
        if state == "ok":
            botdb.garmin_account_set(con, tg_id, context.user_data.get("g_email"))
            activity.log(context, tg_id, activity.GARMIN_CONNECTED)
            await update.effective_message.reply_text(i18n.t("garmin.connected", lang))
        else:
            await update.effective_message.reply_text(i18n.t("garmin.login_failed", lang))
    finally:
        con.close()
    context.user_data.pop("g_session", None)
    context.user_data.pop("g_email", None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang") or await _lang_for(context, update.effective_user.id)
    context.user_data.pop("g_session", None)
    context.user_data.pop("g_email", None)
    await update.effective_message.reply_text(i18n.t("garmin.cancelled", lang))
    return ConversationHandler.END


def handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start, pattern="^gconnect$")],
        states={
            ASK_EMAIL: [MessageHandler(menu.not_menu_text(), got_email)],
            ASK_PASSWORD: [MessageHandler(menu.not_menu_text(), got_password)],
            ASK_MFA: [MessageHandler(menu.not_menu_text(), got_mfa)],
        },
        fallbacks=menu.wizard_fallbacks(cancel=cancel),
    )
