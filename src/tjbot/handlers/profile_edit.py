"""Редактирование профиля: мастер правки полей users без повторного /start.

Кнопка в карточке профиля -> inline-меню полей (ник, рост, вес, пол, возраст, зал)
-> правка с теми же валидациями, что в онбординге. Точечные UPDATE (не save_user,
он бы сбросил created_at и level). Вес правит опорный users.weight_kg; вес за дату
остаётся отдельной кнопкой bw:start.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (CallbackQueryHandler, ContextTypes, ConversationHandler,
                          MessageHandler)

from tj import i18n

from .. import db as botdb
from ..access import restricted
from . import menu
from .menu import not_menu_text, show_menu

MENU, VALUE = range(2)

_TEXT_FIELDS = ("nick", "height", "weight", "age")


def _lang(context, uid: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


def edit_menu_kb(con, lang: str, uid: int) -> InlineKeyboardMarkup:
    u = botdb.get_user(con, uid)
    sex_key = "onboarding.sex_m_label" if u["sex"] == "m" else "onboarding.sex_f_label"
    sex_label = i18n.t(sex_key, lang)
    rows = [
        [InlineKeyboardButton(i18n.t("profile.edit_nick", lang, v=u["nick"]), callback_data="pedit:nick")],
        [InlineKeyboardButton(i18n.t("profile.edit_height", lang, v=u["height_cm"]), callback_data="pedit:height")],
        [InlineKeyboardButton(i18n.t("profile.edit_weight", lang, v=u["weight_kg"]), callback_data="pedit:weight")],
        [InlineKeyboardButton(i18n.t("profile.edit_sex", lang, v=sex_label), callback_data="pedit:sex")],
        [InlineKeyboardButton(i18n.t("profile.edit_age", lang, v=u["age"]), callback_data="pedit:age")],
        [InlineKeyboardButton(i18n.t("profile.edit_gym", lang, v=u["gym"]), callback_data="pedit:gym")],
        [InlineKeyboardButton(i18n.t("profile.edit_done", lang), callback_data="pedit:done")],
    ]
    return InlineKeyboardMarkup(rows)


def _sex_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("onboarding.btn_sex_m", lang), callback_data="sedit:m"),
        InlineKeyboardButton(i18n.t("onboarding.btn_sex_f", lang), callback_data="sedit:f"),
    ]])


def _gym_kb(con, lang: str) -> InlineKeyboardMarkup:
    rows = []
    for g in botdb.list_gyms(con):
        label = (i18n.t("onboarding.btn_gym_default", lang, name=g["name"])
                 if g["is_default"] else g["name"])
        rows.append([InlineKeyboardButton(label, callback_data=f"pgym:{g['name']}")])
    rows.append([InlineKeyboardButton(i18n.t("onboarding.btn_gym_other", lang), callback_data="pgym:other")])
    rows.append([InlineKeyboardButton(i18n.t("onboarding.btn_gym_solo", lang), callback_data="pgym:solo")])
    return InlineKeyboardMarkup(rows)


@restricted
async def open_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        if not botdb.get_user(con, uid):
            await q.message.reply_text(i18n.t("profile.not_filled", lang))
            return ConversationHandler.END
        kb = edit_menu_kb(con, lang, uid)
    finally:
        con.close()
    await q.message.reply_text(i18n.t("profile.edit_pick", lang), reply_markup=kb)
    return MENU


async def _reshow_menu(message, context, uid: int) -> None:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        await message.reply_text(i18n.t("profile.edit_saved", lang))
        await message.reply_text(i18n.t("profile.edit_pick", lang),
                                 reply_markup=edit_menu_kb(con, lang, uid))
    finally:
        con.close()


async def field_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    field = q.data.split(":", 1)[1]
    uid = q.from_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        if field == "done":
            context.user_data.pop("pedit_field", None)
            await show_menu(update, context, "profile.edit_closed")
            return ConversationHandler.END
        if field == "sex":
            await q.message.reply_text(i18n.t("profile.edit_ask_sex", lang),
                                       reply_markup=_sex_kb(lang))
            return MENU
        if field == "gym":
            kb = _gym_kb(con, lang)
            await q.message.reply_text(i18n.t("profile.edit_ask_gym", lang), reply_markup=kb)
            return MENU
    finally:
        con.close()
    context.user_data["pedit_field"] = field
    await q.message.reply_text(i18n.t(f"profile.edit_ask_{field}", lang))
    return VALUE


async def save_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    field = context.user_data.get("pedit_field")
    if field not in _TEXT_FIELDS:
        return MENU
    uid = update.effective_user.id
    lang = _lang(context, uid)
    txt = (update.message.text or "").strip()
    con = botdb.connect(context.bot_data["db_path"])
    try:
        if field == "nick":
            if not txt:
                await update.message.reply_text(i18n.t("profile.edit_nick_invalid", lang))
                return VALUE
            botdb.set_nick(con, uid, txt)
        elif field == "height":
            if not txt.isdigit() or not (100 <= int(txt) <= 250):
                await update.message.reply_text(i18n.t("onboarding.height_invalid", lang))
                return VALUE
            botdb.set_height(con, uid, int(txt))
        elif field == "weight":
            try:
                kg = float(txt.replace(",", "."))
            except ValueError:
                await update.message.reply_text(i18n.t("onboarding.weight_invalid", lang))
                return VALUE
            botdb.set_weight(con, uid, kg)
        elif field == "age":
            if not txt.isdigit() or not (10 <= int(txt) <= 100):
                await update.message.reply_text(i18n.t("onboarding.age_invalid", lang))
                return VALUE
            botdb.set_age(con, uid, int(txt))
    finally:
        con.close()
    context.user_data.pop("pedit_field", None)
    await _reshow_menu(update.message, context, uid)
    return MENU


async def set_sex_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    sex = q.data.split(":", 1)[1]
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.set_sex(con, uid, sex)
    finally:
        con.close()
    await _reshow_menu(q.message, context, uid)
    return MENU


async def set_gym_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    gym = q.data.split(":", 1)[1]
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.set_gym(con, uid, gym)
    finally:
        con.close()
    await _reshow_menu(q.message, context, uid)
    return MENU


def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(open_edit, pattern=r"^pedit:open$")],
        states={
            MENU: [
                CallbackQueryHandler(field_router, pattern=r"^pedit:(nick|height|weight|age|sex|gym|done)$"),
                CallbackQueryHandler(set_sex_cb, pattern=r"^sedit:(m|f)$"),
                CallbackQueryHandler(set_gym_cb, pattern=r"^pgym:"),
            ],
            VALUE: [MessageHandler(not_menu_text(), save_value)],
        },
        fallbacks=menu.wizard_fallbacks(),
        name="profile_edit",
    )
