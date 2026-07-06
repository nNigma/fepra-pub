"""Админ-мастер «Pro»: список Pro-пользователей + выдать/снять (только админ)."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n

from .. import db as botdb
from ..access import add_pro, is_admin, load_pro, remove_pro
from . import menu
from .menu import show_menu

ADD = range(1)[0]
BTN_PRO = "Pro"


async def _lang_for(context: ContextTypes.DEFAULT_TYPE, uid: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = await _lang_for(context, uid)
    context.user_data["lang"] = lang
    if not is_admin(uid):
        await update.effective_message.reply_text(i18n.t("pro.only_admin", lang))
        return ConversationHandler.END
    ids = sorted(load_pro())
    lines = [i18n.t("pro.list_line", lang, tg_id=i) for i in ids] or [i18n.t("pro.list_empty", lang)]
    rows = [[InlineKeyboardButton(i18n.t("pro.btn_grant", lang), callback_data="pro:add")]]
    for i in ids:
        rows.append([InlineKeyboardButton(i18n.t("pro.btn_revoke", lang, tg_id=i), callback_data=f"prorm:{i}")])
    await update.effective_message.reply_text(
        i18n.t("pro.list_header", lang, lines="\n".join(lines)), reply_markup=InlineKeyboardMarkup(rows))
    return ADD


async def rm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = context.user_data.get("lang") or await _lang_for(context, q.from_user.id)
    await q.answer(i18n.t("pro.revoked", lang))
    remove_pro(int(q.data.split(":", 1)[1]))
    await q.edit_message_text(i18n.t("pro.revoked_msg", lang))
    await show_menu(update, context)
    return ConversationHandler.END


async def ask_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = context.user_data.get("lang") or await _lang_for(context, q.from_user.id)
    await q.answer()
    await q.edit_message_text(i18n.t("pro.ask_tg_id", lang))
    return ADD


async def take_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ru")
    txt = (update.effective_message.text or "").strip()
    if not txt.isdigit():
        await update.effective_message.reply_text(i18n.t("pro.need_number", lang))
        return ADD
    add_pro(int(txt))
    await update.effective_message.reply_text(i18n.t("pro.granted", lang, tg_id=txt))
    await show_menu(update, context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await show_menu(update, context, "menu.cancelled_short")
    return ConversationHandler.END


def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text(menu.btn_variants("btn.pro")), entry),
            CallbackQueryHandler(ask_add, pattern=r"^pro:add$"),
            CallbackQueryHandler(rm, pattern=r"^prorm:"),
        ],
        states={
            ADD: [CallbackQueryHandler(ask_add, pattern=r"^pro:add$"),
                  CallbackQueryHandler(rm, pattern=r"^prorm:"),
                  MessageHandler(menu.not_menu_text(), take_id)],
        },
        fallbacks=menu.wizard_fallbacks(cancel=cancel),
    )
