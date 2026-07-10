"""Отдельный ввод веса тела за дату (из Профиля): дата -> кг -> daily.weight_kg."""
from __future__ import annotations

from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (CallbackQueryHandler, ContextTypes, ConversationHandler,
                          MessageHandler)

from tj import i18n
from .. import db as botdb
from ..access import restricted
from . import menu
from .menu import not_menu_text, show_menu
from .record_workout import _parse_date, _tz

BW_DATE, BW_DATE_INPUT, BW_INPUT = range(3)


def _date_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("record.btn_today", lang), callback_data="bwd:today"),
        InlineKeyboardButton(i18n.t("record.btn_yesterday", lang), callback_data="bwd:yest"),
        InlineKeyboardButton(i18n.t("record.btn_other_date", lang), callback_data="bwd:other"),
    ]])


@restricted
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    await q.message.reply_text(i18n.t("bw.ask_date", lang), reply_markup=_date_kb(lang))
    return BW_DATE


async def pick_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    choice = q.data.split(":", 1)[1]
    today = datetime.now(_tz(context)).date()
    if choice == "today":
        context.user_data["bw_day"] = today
    elif choice == "yest":
        context.user_data["bw_day"] = today - timedelta(days=1)
    else:
        await q.edit_message_text(i18n.t("record.ask_date_input", lang))
        return BW_DATE_INPUT
    await q.edit_message_text(i18n.t("record.date_chosen", lang, date=context.user_data["bw_day"]))
    await q.message.reply_text(i18n.t("bw.ask_kg", lang))
    return BW_INPUT


async def date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    d = _parse_date(update.message.text, datetime.now(_tz(context)).date())
    if d is None:
        await update.message.reply_text(i18n.t("record.date_invalid", lang))
        return BW_DATE_INPUT
    context.user_data["bw_day"] = d
    await update.message.reply_text(i18n.t("record.date_chosen", lang, date=d))
    await update.message.reply_text(i18n.t("bw.ask_kg", lang))
    return BW_INPUT


async def save_kg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    try:
        kg = float(update.message.text.strip().replace(",", "."))
    except ValueError:
        await update.message.reply_text(i18n.t("record.bodyweight_invalid", lang))
        return BW_INPUT
    day = context.user_data.get("bw_day", datetime.now(_tz(context)).date())
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.set_bodyweight(con, day.isoformat(), kg, update.effective_user.id)
    finally:
        con.close()
    context.user_data.clear()
    await show_menu(update, context, "bw.saved", date=day.isoformat(), kg=kg)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await show_menu(update, context, "menu.cancelled_short")
    return ConversationHandler.END


def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(entry, pattern=r"^bw:start$")],
        states={
            BW_DATE: [CallbackQueryHandler(pick_date, pattern=r"^bwd:")],
            BW_DATE_INPUT: [MessageHandler(not_menu_text(), date_input)],
            BW_INPUT: [MessageHandler(not_menu_text(), save_kg)],
        },
        fallbacks=menu.wizard_fallbacks(),
        name="bodyweight",
    )
