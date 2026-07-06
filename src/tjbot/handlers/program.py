"""Подтверждение/правка черновика программы Universe.

Userbot (ingest_universe) шлёт фото доски + кнопки Подтвердить/Поправить;
эти колбэки обрабатывает работающий бот (общая training.db).
"""
from __future__ import annotations

from telegram import Update
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n
from .. import db as botdb
from ..access import is_allowed
from . import menu

EDIT = 0


async def _lang_for(context: ContextTypes.DEFAULT_TYPE, uid: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not is_allowed(q.from_user.id):
        return
    lang = context.user_data.get("lang") or await _lang_for(context, q.from_user.id)
    pid = int(q.data.split(":")[1])
    con = botdb.connect(context.bot_data["db_path"])
    botdb.confirm_program(con, pid)
    row = botdb.get_program_by_id(con, pid)
    con.close()
    day = row["day"] if row else i18n.t("program.day_unknown", lang)
    await q.edit_message_caption(caption=i18n.t("program.confirmed", lang, day=day))


async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not is_allowed(q.from_user.id):
        return ConversationHandler.END
    lang = context.user_data.get("lang") or await _lang_for(context, q.from_user.id)
    context.user_data["lang"] = lang
    context.user_data["edit_prog"] = int(q.data.split(":")[1])
    await q.message.reply_text(i18n.t("program.ask_edit_text", lang))
    return EDIT


async def edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang") or await _lang_for(context, update.effective_user.id)
    pid = context.user_data.pop("edit_prog", None)
    if pid is None:
        return ConversationHandler.END
    con = botdb.connect(context.bot_data["db_path"])
    botdb.confirm_program(con, pid, raw_text=update.message.text.strip())
    con.close()
    await update.message.reply_text(i18n.t("program.updated", lang))
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang") or await _lang_for(context, update.effective_user.id)
    context.user_data.pop("edit_prog", None)
    await update.message.reply_text(i18n.t("program.cancelled", lang))
    return ConversationHandler.END


def handlers() -> list:
    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_start, pattern=r"^progedit:")],
        states={EDIT: [MessageHandler(menu.not_menu_text(), edit_save)]},
        fallbacks=menu.wizard_fallbacks(cancel=cancel),
        name="program_edit",
    )
    return [CallbackQueryHandler(confirm, pattern=r"^prog:"), edit_conv]
