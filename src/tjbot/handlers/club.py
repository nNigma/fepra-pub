"""Программа зала Universe: просмотр (всем) + добавление/правка (админ).

Под-меню (механизм из A): просмотр - обычные хендлеры, добавление -
ConversationHandler с распознаванием фото/текста через Gemini и стандартизацией
движений (онтология + runtime-алиасы). Закрывает баг сессии 7 (любой текст
сохранялся как программа): ввод в явных состояниях + отбраковка кнопок/пустого.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, Update)
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n

from .. import activity
from .. import db as botdb
from ..access import is_admin
from . import menu
from .menu import show_menu
from .record_workout import _parse_date, _tz

BTN_CLUB = "Программа зала"
BTN_CLUB_DATE = "📅 На дату"
BTN_CLUB_STATS = "📊 Стата зала"
BTN_CLUB_ADD = "➕ Добавить"
BTN_CLUB_EDIT = "✏️ Редактировать программу"

VIEW_DATE, ADD_DATE, ADD_DATE_INPUT, ADD_INPUT, ADD_CONFIRM = range(5)


def club_kb(admin: bool, lang: str = "ru") -> ReplyKeyboardMarkup:
    rows = [[i18n.t("btn.club_date", lang), i18n.t("btn.club_stats", lang)]]
    if admin:
        rows.append([i18n.t("btn.club_add", lang), i18n.t("btn.club_edit", lang)])
    rows.append([i18n.t("btn.back", lang)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _is_menu_text(text: str) -> bool:
    return (text or "").strip() in menu.all_menu_variants()


def _parse_alias_lines(text: str):
    out = []
    for line in (text or "").splitlines():
        if "=" not in line:
            continue
        alias, canon = line.split("=", 1)
        alias, canon = alias.strip().lower(), canon.strip()
        if alias and canon:
            out.append((alias, canon))
    return out


def _fmt_program(row, lang: str = "ru") -> str:
    if not row:
        return ""
    return i18n.t("club.program_header", lang, day=row["day"], text=row["raw_text"])


def _fmt_stats(rows, lang: str = "ru") -> str:
    if not rows:
        return i18n.t("club.no_stats_yet", lang)
    lines = [i18n.t("club.stats_line", lang, name=name, n=n) for _, n, name in rows[:20]]
    return i18n.t("club.stats_header", lang, lines="\n".join(lines))


def _restandardize(con, draft) -> None:
    from tj.analysis.wod_program import movements_of, parse_program
    aliases = botdb.load_aliases(con)
    blocks = parse_program(draft["raw_text"], aliases)
    draft["canon"], draft["unknown"] = movements_of(blocks)


async def open_club(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        today = datetime.now(_tz(context)).date().isoformat()
        row = botdb.get_program(con, today, "Universe")
        last = None if row else botdb.last_program(con)
    finally:
        con.close()
    if row:
        msg = _fmt_program(row, lang)
    elif last:
        msg = i18n.t("club.no_program_last", lang, day=last["day"])
    else:
        msg = i18n.t("club.no_program_yet", lang)
    await update.effective_message.reply_text(msg, reply_markup=club_kb(is_admin(uid), lang))


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from tj.analysis import gym
    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        rows = gym.movement_frequency(con, "Universe", lang=lang)
    finally:
        con.close()
    await update.effective_message.reply_text(
        _fmt_stats(rows, lang), reply_markup=club_kb(is_admin(uid), lang))


async def view_date_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
    finally:
        con.close()
    context.user_data["lang"] = lang
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(i18n.t("club.today", lang), callback_data="cvd:today"),
         InlineKeyboardButton(i18n.t("club.yesterday", lang), callback_data="cvd:yest")],
        [InlineKeyboardButton(i18n.t("club.other_date", lang), callback_data="cvd:other")],
    ])
    await update.effective_message.reply_text(i18n.t("club.view_date_prompt", lang), reply_markup=kb)
    return VIEW_DATE


async def view_date_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "ru")
    if q.data == "cvd:other":
        await q.edit_message_text(i18n.t("club.ask_date_input", lang))
        return VIEW_DATE
    today = datetime.now(_tz(context)).date()
    d = today if q.data == "cvd:today" else today - timedelta(days=1)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        row = botdb.get_program(con, d.isoformat(), "Universe")
    finally:
        con.close()
    text = _fmt_program(row, lang) if row else i18n.t("club.no_program_on_date", lang, day=d)
    await q.edit_message_text(text)
    return ConversationHandler.END


async def view_date_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ru")
    d = _parse_date(update.message.text, datetime.now(_tz(context)).date())
    if d is None:
        await update.message.reply_text(i18n.t("club.date_invalid", lang))
        return VIEW_DATE
    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        row = botdb.get_program(con, d.isoformat(), "Universe")
    finally:
        con.close()
    admin = is_admin(uid)
    text = _fmt_program(row, lang) if row else i18n.t("club.no_program_on_date", lang, day=d)
    await update.message.reply_text(text, reply_markup=club_kb(admin, lang))
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await show_menu(update, context, "menu.cancelled_short")
    return ConversationHandler.END


async def _lang_for(context: ContextTypes.DEFAULT_TYPE, uid: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


async def add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = await _lang_for(context, uid)
    if not is_admin(uid):
        await update.effective_message.reply_text(i18n.t("club.admin_only", lang))
        return ConversationHandler.END
    context.user_data["cedit"] = False
    context.user_data["lang"] = lang
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("club.today", lang), callback_data="cadd:today"),
        InlineKeyboardButton(i18n.t("club.yesterday", lang), callback_data="cadd:yesterday"),
        InlineKeyboardButton(i18n.t("club.other", lang), callback_data="cadd:other"),
    ]])
    await update.effective_message.reply_text(i18n.t("club.ask_add_date", lang), reply_markup=kb)
    return ADD_DATE


async def edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = await _lang_for(context, uid)
    if not is_admin(uid):
        await update.effective_message.reply_text(i18n.t("club.admin_only", lang))
        return ConversationHandler.END
    context.user_data["cedit"] = True
    context.user_data["lang"] = lang
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("club.today", lang), callback_data="cadd:today"),
        InlineKeyboardButton(i18n.t("club.yesterday", lang), callback_data="cadd:yesterday"),
        InlineKeyboardButton(i18n.t("club.other", lang), callback_data="cadd:other"),
    ]])
    await update.effective_message.reply_text(i18n.t("club.ask_edit_date", lang), reply_markup=kb)
    return ADD_DATE


async def _show_existing_program(message, context: ContextTypes.DEFAULT_TYPE, day) -> None:
    if not context.user_data.get("cedit"):
        return
    lang = context.user_data.get("lang", "ru")
    con = botdb.connect(context.bot_data["db_path"])
    try:
        row = botdb.get_program(con, day.isoformat(), "Universe")
    finally:
        con.close()
    if row:
        await message.reply_text(i18n.t("club.current_program", lang, text=row["raw_text"]))
    else:
        await message.reply_text(i18n.t("club.no_program_on_day", lang, day=day))


async def add_pick_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "ru")
    choice = q.data.split(":", 1)[1]
    today = datetime.now(_tz(context)).date()
    if choice == "today":
        context.user_data["cday"] = today
    elif choice == "yesterday":
        context.user_data["cday"] = today - timedelta(days=1)
    else:
        await q.edit_message_text(i18n.t("club.ask_date_input", lang))
        return ADD_DATE_INPUT
    await q.edit_message_text(i18n.t("club.date_set", lang, day=context.user_data["cday"]))
    await _show_existing_program(q.message, context, context.user_data["cday"])
    await q.message.reply_text(i18n.t("club.send_board", lang))
    return ADD_INPUT


async def add_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ru")
    d = _parse_date(update.message.text, datetime.now(_tz(context)).date())
    if d is None:
        await update.message.reply_text(i18n.t("club.ask_date_input", lang))
        return ADD_DATE_INPUT
    context.user_data["cday"] = d
    await _show_existing_program(update.message, context, d)
    await update.message.reply_text(i18n.t("club.date_set_send_board", lang, day=d))
    return ADD_INPUT


async def add_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from .. import vision
    lang = context.user_data.get("lang", "ru")
    msg = update.message
    raw_text = None
    if msg.photo:
        if vision.has_vision():
            await msg.reply_text(i18n.t("club.parsing_photo", lang))
            try:
                f = await context.bot.get_file(msg.photo[-1].file_id)
                buf = await f.download_as_bytearray()
                db = vision.parse_board(bytes(buf))
            except Exception:
                db = None
            raw_text = db.get("raw_text") if db else None
        if not raw_text:
            await msg.reply_text(i18n.t("club.photo_not_recognized", lang))
            return ADD_INPUT
    else:
        text = (msg.text or "").strip()
        if _is_menu_text(text) or len(text) < 4:
            await msg.reply_text(i18n.t("club.send_text_or_photo", lang))
            return ADD_INPUT
        raw_text = text
    if not raw_text or len(raw_text.strip()) < 4:
        await msg.reply_text(i18n.t("club.empty_send_again", lang))
        return ADD_INPUT
    con = botdb.connect(context.bot_data["db_path"])
    try:
        aliases = botdb.load_aliases(con)
    finally:
        con.close()
    from tj.analysis.wod_program import movements_of, parse_program
    blocks = parse_program(raw_text, aliases)
    canon, unknown = movements_of(blocks)
    fmt = "+".join(dict.fromkeys(b["format"] for b in blocks)) or "other"
    context.user_data["draft"] = {
        "raw_text": raw_text, "format": fmt,
        "canon": canon, "unknown": unknown,
        "source": "photo" if msg.photo else "text"}
    await _show_confirm(msg, context)
    return ADD_CONFIRM


async def _show_confirm(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    from tj.analysis.wod_program import annotate
    lang = context.user_data.get("lang", "ru")
    d = context.user_data["draft"]
    names = ", ".join(d["canon"]) or i18n.t("club.dash", lang)
    body = i18n.t("club.confirm_header", lang, day=context.user_data["cday"],
                  annotated=annotate(d["raw_text"])[:900], names=names)
    if d["unknown"]:
        body += i18n.t("club.unknown_movements", lang, names=", ".join(d["unknown"]))
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("club.btn_confirm", lang), callback_data="cok"),
        InlineKeyboardButton(i18n.t("club.btn_fix", lang), callback_data="cedit"),
    ]])
    await message.reply_text(body, reply_markup=kb)


async def add_map(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ru")
    pairs = _parse_alias_lines(update.message.text)
    if not pairs:
        await update.message.reply_text(i18n.t("club.alias_format_hint", lang))
        return ADD_CONFIRM
    con = botdb.connect(context.bot_data["db_path"])
    try:
        for alias, canon in pairs:
            botdb.add_alias(con, alias, canon, source="manual")
        _restandardize(con, context.user_data["draft"])
    finally:
        con.close()
    await update.message.reply_text(i18n.t("club.aliases_added", lang))
    await _show_confirm(update.message, context)
    return ADD_CONFIRM


async def add_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "ru")
    d = context.user_data.get("draft")
    day = context.user_data.get("cday")
    if not d or not day:
        return ConversationHandler.END
    con = botdb.connect(context.bot_data["db_path"])
    try:
        con.execute('DELETE FROM wod_programs WHERE "day"=? AND "gym"=?',
                    (day.isoformat(), "Universe"))
        botdb.add_program(con, day.isoformat(), "Universe", d["raw_text"],
                          fmt=d["format"], movements=d["canon"], source=d["source"], confirmed=1)
    finally:
        con.close()
    activity.log(context, update.effective_user.id, activity.CLUB_PROGRAM_ADDED)
    await q.edit_message_text(i18n.t("club.program_saved", lang, day=day))
    context.user_data.clear()
    await show_menu(update, context, "menu.done")
    return ConversationHandler.END


async def add_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "ru")
    await q.message.reply_text(i18n.t("club.send_fixed_board", lang))
    return ADD_INPUT


def _view_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Text(menu.btn_variants("btn.club_date")), view_date_entry)],
        states={VIEW_DATE: [
            CallbackQueryHandler(view_date_pick, pattern=r"^cvd:"),
            MessageHandler(menu.not_menu_text(), view_date_show),
        ]},
        fallbacks=menu.wizard_fallbacks(),
        name="club_view",
    )


def _add_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text(menu.btn_variants("btn.club_add")), add_entry),
            MessageHandler(filters.Text(menu.btn_variants("btn.club_edit")), edit_entry),
        ],
        states={
            ADD_DATE: [CallbackQueryHandler(add_pick_date, pattern=r"^cadd:")],
            ADD_DATE_INPUT: [MessageHandler(menu.not_menu_text(), add_date_input)],
            ADD_INPUT: [MessageHandler(menu.not_menu_text() | filters.PHOTO, add_input)],
            ADD_CONFIRM: [
                CallbackQueryHandler(add_ok, pattern=r"^cok$"),
                CallbackQueryHandler(add_edit, pattern=r"^cedit$"),
                MessageHandler(menu.not_menu_text(), add_map),
            ],
        },
        fallbacks=menu.wizard_fallbacks(),
        name="club_add",
    )


def register(app) -> None:
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.club_section")), open_club))
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.club_stats")), stats))
    app.add_handler(_view_conv())
    app.add_handler(_add_conv())
