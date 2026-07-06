"""Мастер «🎯 Цель»: тип -> дисциплина/общий -> значение -> запись; список с удалением."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n
from tj.analysis import standards
from .. import activity
from .. import db as botdb
from ..access import restricted
from . import menu
from .menu import show_menu

GKIND, GDISC, GVALUE = range(3)
BTN_GOAL = "🎯 Цель"


async def _lang_for(context: ContextTypes.DEFAULT_TYPE, uid: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


@restricted
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    lang = await _lang_for(context, tg_id)
    context.user_data["lang"] = lang
    con = botdb.connect(context.bot_data["db_path"])
    try:
        goals = botdb.active_goals(con, tg_id)
    finally:
        con.close()
    lines = [i18n.t("goal.list_line", lang, title=g["title"]) for g in goals] or [i18n.t("goal.list_empty", lang)]
    rows = [[InlineKeyboardButton(i18n.t("goal.btn_new", lang), callback_data="g:new")]]
    for g in goals:
        rows.append([InlineKeyboardButton(i18n.t("goal.btn_del", lang, title=g["title"]), callback_data=f"gdel:{g['id']}")])
    await update.effective_message.reply_text(
        i18n.t("goal.list_header", lang, lines="\n".join(lines)), reply_markup=InlineKeyboardMarkup(rows))
    return GKIND


async def del_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = context.user_data.get("lang") or await _lang_for(context, q.from_user.id)
    await q.answer(i18n.t("goal.removed_alert", lang))
    gid = int(q.data.split(":", 1)[1])
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.archive_goal(con, gid)
    finally:
        con.close()
    await q.edit_message_text(i18n.t("goal.removed_msg", lang))
    await show_menu(update, context)
    return ConversationHandler.END


async def new_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = context.user_data.get("lang") or await _lang_for(context, q.from_user.id)
    context.user_data["lang"] = lang
    await q.answer()
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("goal.btn_numeric", lang), callback_data="gk:numeric"),
        InlineKeyboardButton(i18n.t("goal.btn_level", lang), callback_data="gk:level"),
    ]])
    await q.edit_message_text(i18n.t("goal.ask_kind", lang), reply_markup=kb)
    return GKIND


async def pick_kind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = context.user_data.get("lang") or await _lang_for(context, q.from_user.id)
    await q.answer()
    context.user_data["gkind"] = q.data.split(":", 1)[1]
    rows = [[InlineKeyboardButton(standards.discipline_name(d, lang), callback_data=f"gx:{d['id']}")]
            for d in sorted(standards.disciplines().values(), key=lambda m: m["order"])]
    await q.edit_message_text(i18n.t("goal.ask_discipline", lang), reply_markup=InlineKeyboardMarkup(rows))
    return GDISC


async def pick_disc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = context.user_data.get("lang") or await _lang_for(context, q.from_user.id)
    await q.answer()
    did = q.data.split(":", 1)[1]
    context.user_data["gdisc"] = did
    meta = standards.disciplines()[did]
    disc_name = standards.discipline_name(meta, lang)
    if context.user_data["gkind"] == "level":
        rows = [[InlineKeyboardButton(standards.tier_name(lvl, lang), callback_data=f"gl:{lvl}")]
                for lvl in standards.tiers()[1:]]
        await q.edit_message_text(i18n.t("goal.ask_level_target", lang, name=disc_name),
                                  reply_markup=InlineKeyboardMarkup(rows))
        return GVALUE
    unit = (i18n.t("goal.unit_kg", lang) if meta["unit"] == "kg"
            else (i18n.t("goal.unit_time", lang) if meta["unit"] == "time" else i18n.t("goal.unit_rounds", lang)))
    await q.edit_message_text(i18n.t("goal.ask_value_target", lang, name=disc_name, unit=unit))
    return GVALUE


async def take_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    did = context.user_data["gdisc"]
    gkind = context.user_data["gkind"]
    meta = standards.disciplines()[did]
    tg_id = update.effective_user.id
    lang = context.user_data.get("lang") or await _lang_for(context, tg_id)

    if update.callback_query:
        await update.callback_query.answer()
        target = update.callback_query.data.split(":", 1)[1]
        metric = "level"
        title = i18n.t("goal.title_level", lang, name=standards.discipline_name(meta, lang), target=target)
    else:
        from .record_result import parse_lift, parse_benchmark
        raw = update.effective_message.text
        if meta["kind"] == "lift":
            p = parse_lift(raw)
            target = p[0] if p else None
            metric = "kg"
        else:
            target = parse_benchmark(raw, meta["unit"])
            metric = meta["basis"]
        if target is None:
            await update.effective_message.reply_text(i18n.t("goal.value_invalid", lang))
            return GVALUE
        title = i18n.t("goal.title_value", lang, name=standards.discipline_name(meta, lang), target=target)

    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.add_goal(con, tg_id=tg_id, kind=gkind, discipline=did,
                       target_value=target, metric=metric, title=title)
    finally:
        con.close()
    activity.log(context, tg_id, activity.GOAL_SET)
    msg = update.callback_query.message if update.callback_query else update.effective_message
    await msg.reply_text(i18n.t("goal.set_confirm", lang, title=title))
    await show_menu(update, context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await show_menu(update, context, "menu.cancelled_short")
    return ConversationHandler.END


def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text(menu.btn_variants("btn.goal_single")), entry),
            CallbackQueryHandler(del_goal, pattern=r"^gdel:"),
            CallbackQueryHandler(new_goal, pattern=r"^g:new$"),
            CallbackQueryHandler(pick_kind, pattern=r"^gk:"),
            CallbackQueryHandler(pick_disc, pattern=r"^gx:"),
        ],
        states={
            GKIND: [CallbackQueryHandler(new_goal, pattern=r"^g:new$"),
                    CallbackQueryHandler(pick_kind, pattern=r"^gk:"),
                    CallbackQueryHandler(del_goal, pattern=r"^gdel:")],
            GDISC: [CallbackQueryHandler(pick_disc, pattern=r"^gx:")],
            GVALUE: [CallbackQueryHandler(take_value, pattern=r"^gl:"),
                     MessageHandler(menu.not_menu_text(), take_value)],
        },
        fallbacks=menu.wizard_fallbacks(cancel=cancel),
    )
