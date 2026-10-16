"""Онбординг: /start -> мастер знакомства (ник, рост, вес, пол, возраст, зал) -> users.

Пол и возраст нужны для зон пульса/TRIMP в анализе (а не только глобальный config).
Уже зарегистрированному /start просто показывает меню.
"""
from __future__ import annotations

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove,
                      Update)
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n

from .. import db as botdb
from ..access import is_allowed
from .menu import show_menu

NICK, HEIGHT, WEIGHT, SEX, AGE, GYM, GUIDE = range(7)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, user.id)
    if not is_allowed(user.id):
        con.close()
        await update.effective_message.reply_text(
            i18n.t("onboarding.access_denied", lang, tg_id=user.id)
        )
        return ConversationHandler.END
    existing = botdb.get_user(con, user.id)
    con.close()
    if existing:
        if context.args and context.args[0] == "pm":
            from .record_result import send_kind_prompt
            await send_kind_prompt(update.effective_message, lang)
            return ConversationHandler.END
        await show_menu(update, context, "menu.welcome_back", nick=existing["nick"])
        return ConversationHandler.END
    await update.effective_message.reply_text(
        i18n.t("onboarding.ask_nick", lang), reply_markup=ReplyKeyboardRemove()
    )
    return NICK


async def get_nick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["nick"] = update.message.text.strip()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    await update.message.reply_text(i18n.t("onboarding.ask_height", lang))
    return HEIGHT


async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    txt = update.message.text.strip()
    if not txt.isdigit() or not (100 <= int(txt) <= 250):
        await update.message.reply_text(i18n.t("onboarding.height_invalid", lang))
        return HEIGHT
    context.user_data["height_cm"] = int(txt)
    await update.message.reply_text(i18n.t("onboarding.ask_weight", lang))
    return WEIGHT


async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    try:
        context.user_data["weight_kg"] = float(update.message.text.strip().replace(",", "."))
    except ValueError:
        await update.message.reply_text(i18n.t("onboarding.weight_invalid", lang))
        return WEIGHT
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.t("onboarding.btn_sex_m", lang), callback_data="sex:m"),
                                InlineKeyboardButton(i18n.t("onboarding.btn_sex_f", lang), callback_data="sex:f")]])
    await update.message.reply_text(i18n.t("onboarding.ask_sex", lang), reply_markup=kb)
    return SEX


async def get_sex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    context.user_data["sex"] = q.data.split(":")[1]
    sex_label = i18n.t("onboarding.sex_m_label", lang) if context.user_data["sex"] == "m" \
        else i18n.t("onboarding.sex_f_label", lang)
    await q.edit_message_text(i18n.t("onboarding.sex_chosen", lang, sex=sex_label))
    await q.message.reply_text(i18n.t("onboarding.ask_age", lang))
    return AGE


def _gym_kb(con, lang: str) -> InlineKeyboardMarkup:
    rows = []
    for g in botdb.list_gyms(con):
        label = (i18n.t("onboarding.btn_gym_default", lang, name=g["name"])
                 if g["is_default"] else g["name"])
        rows.append([InlineKeyboardButton(label, callback_data=f"gym:{g['name']}")])
    rows.append([InlineKeyboardButton(i18n.t("onboarding.btn_gym_other", lang), callback_data="gym:other")])
    rows.append([InlineKeyboardButton(i18n.t("onboarding.btn_gym_solo", lang), callback_data="gym:solo")])
    return InlineKeyboardMarkup(rows)


async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, update.effective_user.id)
        txt = update.message.text.strip()
        if not txt.isdigit() or not (10 <= int(txt) <= 100):
            await update.message.reply_text(i18n.t("onboarding.age_invalid", lang))
            return AGE
        context.user_data["age"] = int(txt)
        kb = _gym_kb(con, lang)
    finally:
        con.close()
    await update.message.reply_text(i18n.t("onboarding.ask_gym", lang), reply_markup=kb)
    return GYM


async def get_gym(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    gym = q.data.split(":", 1)[1]
    ud = context.user_data
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    botdb.save_user(con, q.from_user.id, nick=ud["nick"], height_cm=ud["height_cm"],
                    weight_kg=ud["weight_kg"], sex=ud["sex"], age=ud["age"], gym=gym)
    con.close()
    await q.edit_message_text(i18n.t("onboarding.gym_chosen", lang, gym=gym))
    ud.clear()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
        i18n.t("onboarding.btn_guide_ok", lang), callback_data="guideok")]])
    msg = await q.message.reply_text(i18n.t("onboarding.results_guide", lang), reply_markup=kb)
    if msg is not None:
        ud["guide_msg_id"] = msg.message_id
    return GUIDE


async def guide_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    context.user_data.pop("guide_msg_id", None)
    await q.edit_message_text(i18n.t("onboarding.results_guide", lang))
    await show_menu(update, context, "menu.profile_saved")
    return ConversationHandler.END


async def guide_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    mid = context.user_data.pop("guide_msg_id", None)
    if mid is not None:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=update.effective_chat.id, message_id=mid, reply_markup=None)
        except Exception:
            pass
    await show_menu(update, context, "menu.profile_saved")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await show_menu(update, context, "menu.cancelled_short")
    return ConversationHandler.END


def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nick)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
            SEX: [CallbackQueryHandler(get_sex, pattern=r"^sex:")],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            GYM: [CallbackQueryHandler(get_gym, pattern=r"^gym:")],
            GUIDE: [CallbackQueryHandler(guide_ok, pattern=r"^guideok$"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, guide_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="onboarding",
    )
