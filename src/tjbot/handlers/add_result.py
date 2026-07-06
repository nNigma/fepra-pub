"""«Добавить результат»: внести свой результат по программе зала (Universe) за дату."""
from __future__ import annotations


def template_from_program(raw_text: str, aliases: dict | None = None):
    """Текст программы зала -> (шаблон результатов | None, блоки). Пусто -> (None, [])."""
    from tj.analysis.wod_program import parse_program, render_template
    blocks = parse_program(raw_text or "", aliases)
    if not blocks:
        return None, []
    return render_template(blocks), blocks


from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (CallbackQueryHandler, ContextTypes, ConversationHandler,
                          MessageHandler, filters)

from tj import i18n
from .. import activity
from .. import db as botdb
from ..access import restricted
from . import menu
from .menu import show_menu
from .record_workout import _parse_date, _tz, save_filled_result

AR_DATE, AR_CONFIRM, AR_RESULT, AR_INGYM = range(4)


def _date_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("addresult.btn_today", lang), callback_data="ard:today"),
        InlineKeyboardButton(i18n.t("addresult.btn_yesterday", lang), callback_data="ard:yest"),
        InlineKeyboardButton(i18n.t("addresult.btn_other_date", lang), callback_data="ard:other"),
    ]])


@restricted
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    await update.message.reply_text(i18n.t("addresult.ask_date", lang), reply_markup=_date_kb(lang))
    return AR_DATE


async def _after_date(context: ContextTypes.DEFAULT_TYPE, message, d, lang: str) -> int:
    context.user_data["ar_day"] = d.isoformat()
    con = botdb.connect(context.bot_data["db_path"])
    try:
        prog = botdb.get_program(con, d.isoformat(), "Universe")
    finally:
        con.close()
    if not prog:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.t("addresult.btn_yes", lang), callback_data="arg:y"),
                                    InlineKeyboardButton(i18n.t("addresult.btn_no", lang), callback_data="arg:n")]])
        await message.reply_text(
            i18n.t("addresult.no_program_ask_gym", lang), reply_markup=kb)
        return AR_INGYM
    context.user_data["ar_prog"] = prog["raw_text"]
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.t("addresult.btn_yes", lang), callback_data="arc:y"),
                                InlineKeyboardButton(i18n.t("addresult.btn_no", lang), callback_data="arc:n")]])
    await message.reply_text(
        i18n.t("addresult.program_confirm", lang, shown=(prog["raw_text"] or "")[:1500]),
        reply_markup=kb)
    return AR_CONFIRM


async def pick_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    choice = q.data.split(":", 1)[1]
    if choice == "other":
        await q.edit_message_text(i18n.t("addresult.ask_date_input", lang))
        return AR_DATE
    today = datetime.now(_tz(context)).date()
    d = today if choice == "today" else today - timedelta(days=1)
    await q.edit_message_text(i18n.t("addresult.date_chosen", lang, date=d))
    return await _after_date(context, q.message, d, lang)


async def got_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    d = _parse_date(update.message.text, datetime.now(_tz(context)).date())
    if not d:
        await update.message.reply_text(i18n.t("addresult.date_invalid", lang))
        return AR_DATE
    return await _after_date(context, update.message, d, lang)


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    if q.data == "arc:n":
        await q.edit_message_text(i18n.t("addresult.confirm_no", lang))
        return ConversationHandler.END
    from .. import vision
    con = botdb.connect(context.bot_data["db_path"])
    try:
        aliases = vision.enrich_aliases(con, context.user_data["ar_prog"])
    finally:
        con.close()
    tmpl, blocks = template_from_program(context.user_data["ar_prog"], aliases)
    context.user_data["ar_blocks"] = blocks
    await q.edit_message_text(i18n.t("addresult.accepted", lang))
    await q.message.reply_text(
        i18n.t("addresult.fill_results_template", lang, tmpl=(tmpl or "—")[:1500]))
    return AR_RESULT


async def in_gym(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    if q.data == "arg:y":
        await q.edit_message_text(i18n.t("addresult.no_program_admin", lang))
    else:
        await q.edit_message_text(i18n.t("addresult.not_gym_hint", lang))
    return ConversationHandler.END


async def got_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    day = datetime.strptime(context.user_data["ar_day"], "%Y-%m-%d").date()
    board_text = context.user_data.get("ar_prog")
    blocks = context.user_data.get("ar_blocks") or []
    text = update.message.text.strip()
    results, metcon_lines, _ = await save_filled_result(
        update, context, day, board_text, "gym", text, blocks)
    context.user_data.clear()
    activity.log(context, update.effective_user.id, activity.RESULT_ADDED)
    await update.message.reply_text(i18n.t("addresult.result_logged", lang, day=day.isoformat()))
    if metcon_lines:
        await update.message.reply_text("\n".join(metcon_lines))
    if results:
        lines = "\n".join(i18n.t("addresult.lift_line", lang, name=r["name"], weight=r["weight"])
                           for r in results)
        await update.message.reply_text(i18n.t("addresult.credited_levels", lang, lines=lines))
    await show_menu(update, context, "menu.done")
    return ConversationHandler.END


def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Text(menu.btn_variants("btn.add_result")), entry)],
        states={
            AR_DATE: [CallbackQueryHandler(pick_date, pattern=r"^ard:"),
                      MessageHandler(menu.not_menu_text(), got_date)],
            AR_CONFIRM: [CallbackQueryHandler(confirm, pattern=r"^arc:")],
            AR_INGYM: [CallbackQueryHandler(in_gym, pattern=r"^arg:")],
            AR_RESULT: [MessageHandler(menu.not_menu_text(), got_result)],
        },
        fallbacks=menu.wizard_fallbacks(),
        name="add_result",
    )
