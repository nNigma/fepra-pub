"""Профиль: цель питания (инлайн-выбор) и город (текстом). Нормы от цели
считает tj.analysis.nutrition_goals — здесь только запись в users."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (CallbackQueryHandler, ContextTypes, ConversationHandler,
                          MessageHandler)

from tj import i18n
from .. import db as botdb
from ..access import restricted
from . import menu
from .menu import not_menu_text

C_CITY = 0


def _lang(context, uid: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


def goal_kb(current: str, lang: str) -> InlineKeyboardMarkup:
    rows = []
    for g in botdb.GOALS:
        label = i18n.t(f"goal.{g}", lang)
        if g == current:
            label += " ✓"
        rows.append([InlineKeyboardButton(label, callback_data=f"ngoal:{g}")])
    return InlineKeyboardMarkup(rows)


@restricted
async def goal_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = _lang(context, uid)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        cur = botdb.user_goal(con, uid)
    finally:
        con.close()
    await q.message.reply_text(i18n.t("goal.pick", lang), reply_markup=goal_kb(cur, lang))


@restricted
async def goal_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = _lang(context, uid)
    goal = q.data.split(":", 1)[1]
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.set_goal(con, uid, goal)
    finally:
        con.close()
    await q.edit_message_text(i18n.t("goal.saved", lang, goal=i18n.t(f"goal.{goal}", lang)))


@restricted
async def city_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    await q.message.reply_text(i18n.t("city.ask", lang))
    return C_CITY


async def city_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    city = (update.message.text or "").strip()
    if not city:
        return C_CITY
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.set_city(con, uid, city)
    finally:
        con.close()
    await update.message.reply_text(i18n.t("city.saved", lang, city=city[:60]))
    return ConversationHandler.END


def register(app) -> None:
    app.add_handler(CallbackQueryHandler(goal_open, pattern=r"^ngoal:open$"))
    app.add_handler(CallbackQueryHandler(goal_pick, pattern=r"^ngoal:(cut|maintain|bulk|recomp)$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(city_entry, pattern=r"^ncity:open$")],
        states={C_CITY: [MessageHandler(not_menu_text(), city_save)]},
        fallbacks=menu.wizard_fallbacks(),
        name="nutrition_city",
    ))
