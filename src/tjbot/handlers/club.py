"""Программа зала Universe: просмотр (всем) + добавление/правка (админ).

Под-меню (механизм из A): просмотр - обычные хендлеры, добавление -
ConversationHandler с распознаванием фото/текста через Gemini и стандартизацией
движений (онтология + runtime-алиасы). Закрывает баг сессии 7 (любой текст
сохранялся как программа): ввод в явных состояниях + отбраковка кнопок/пустого.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, Update)
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n, ontology

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

VIEW_DATE, ADD_DATE, ADD_DATE_INPUT, ADD_INPUT, ADD_ENGINE, ADD_CONFIRM, ADD_MOVE = range(7)


def _engine_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("record.btn_engine_fast", lang), callback_data="ceng:fast"),
        InlineKeyboardButton(i18n.t("record.btn_engine_slow", lang), callback_data="ceng:slow"),
    ]])


def _board_failed_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("record.btn_retry_recognize", lang), callback_data="cretry"),
    ]])


def _offer_engine_choice() -> bool:
    """Показывать ли выбор движка доски в club-флоу (Claude-vision доступен)."""
    from .. import vision
    return vision.has_claude()


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


_SLUG_RE = re.compile(r"[^0-9a-zа-яё]+")


def _slug(name: str) -> str:
    """Имя движения -> канон-id: нижний регистр, не-буквы/цифры -> «_»."""
    return _SLUG_RE.sub("_", (name or "").lower()).strip("_")


def _register_canon(con, slug: str) -> None:
    """Регистрирует лёгкий канон (self-alias), чтобы он резолвился и попадал в словарь."""
    botdb.add_alias(con, slug, slug, source="manual")


def _dictionary_text(con, lang: str = "ru") -> str:
    """Текст словаря «канон: алиас1, алиас2» — статические + рантайм-алиасы."""
    groups: dict[str, list[str]] = {}
    for canon, aliases in ontology.MOVEMENTS.items():
        groups.setdefault(canon, []).extend(aliases)
    for alias, canon in botdb.load_aliases(con).items():
        groups.setdefault(canon, [])
        if alias != canon:
            groups[canon].append(alias)
    lines = [i18n.t("club.dict_header", lang)]
    for canon in sorted(groups):
        al = list(dict.fromkeys(groups[canon]))
        lines.append(f"{canon}: {', '.join(al)}" if al else f"{canon}:")
    return "\n".join(lines)


def _chunks(text: str, limit: int = 3500) -> list[str]:
    out, buf = [], ""
    for line in text.split("\n"):
        if buf and len(buf) + len(line) + 1 > limit:
            out.append(buf)
            buf = line
        else:
            buf = line if not buf else f"{buf}\n{line}"
    if buf:
        out.append(buf)
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
    if msg.photo:
        context.user_data["club_photo"] = msg.photo[-1].file_id
        if not vision.has_vision():
            await msg.reply_text(i18n.t("club.photo_not_recognized", lang))
            return ADD_INPUT
        if _offer_engine_choice():
            await msg.reply_text(i18n.t("record.ask_engine", lang), reply_markup=_engine_kb(lang))
            return ADD_ENGINE
        return await _parse_add_photo(msg, context, lang, "gemini")
    text = (msg.text or "").strip()
    if _is_menu_text(text) or len(text) < 4:
        await msg.reply_text(i18n.t("club.send_text_or_photo", lang))
        return ADD_INPUT
    return await _finish_add_input(msg, context, text, "text")


async def _parse_add_photo(message, context: ContextTypes.DEFAULT_TYPE,
                           lang: str, engine: str) -> int:
    """Скачать фото программы зала и распознать выбранным движком. Общий код для
    выбора движка (Claude вкл) и прямого Gemini-пути (Claude выкл)."""
    from .. import vision
    file_id = context.user_data.get("club_photo")
    if not file_id:
        await message.reply_text(i18n.t("club.send_text_or_photo", lang))
        return ADD_INPUT
    await message.reply_text(i18n.t(
        "record.parsing_photo_slow" if engine == "claude" else "record.parsing_photo", lang))
    db = None
    try:
        f = await context.bot.get_file(file_id)
        buf = await f.download_as_bytearray()
        db = vision.parse_board(bytes(buf), engine=engine)
    except Exception:
        db = None
    raw_text = db.get("raw_text") if db else None
    if not raw_text:
        await message.reply_text(i18n.t("club.photo_not_recognized", lang),
                                 reply_markup=_board_failed_kb(lang))
        return ADD_INPUT
    if db.get("engine_used") and db["engine_used"] != engine:
        await message.reply_text(i18n.t("record.board_engine_swapped", lang))
    return await _finish_add_input(message, context, raw_text, "photo")


async def add_engine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор движка распознавания программы зала: быстрый Gemini / медленный Claude."""
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "ru")
    engine = "claude" if q.data == "ceng:slow" else "gemini"
    return await _parse_add_photo(q.message, context, lang, engine)


async def add_retry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """«Попробовать ещё раз» после сбоя распознавания программы: переспросить движок."""
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "ru")
    if not context.user_data.get("club_photo"):
        await q.edit_message_text(i18n.t("club.send_text_or_photo", lang))
        return ADD_INPUT
    if _offer_engine_choice():
        await q.edit_message_text(i18n.t("record.ask_engine", lang), reply_markup=_engine_kb(lang))
        return ADD_ENGINE
    return await _parse_add_photo(q.message, context, lang, "gemini")


async def _finish_add_input(msg, context: ContextTypes.DEFAULT_TYPE, raw_text: str, source: str) -> int:
    lang = context.user_data.get("lang", "ru")
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
        "canon": canon, "unknown": unknown, "source": source}
    await _show_confirm(msg, context)
    return ADD_CONFIRM


async def _show_confirm(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    from tj.analysis.wod_program import annotate
    lang = context.user_data.get("lang", "ru")
    d = context.user_data["draft"]
    await message.reply_text(
        i18n.t("club.program_body", lang, annotated=annotate(d["raw_text"])[:3500]))
    names = ", ".join(d["canon"]) or i18n.t("club.dash", lang)
    body = i18n.t("club.movements_line", lang, names=names)
    if d["unknown"]:
        body += i18n.t("club.unknown_movements", lang, names=", ".join(d["unknown"]))
    rows = [[
        InlineKeyboardButton(i18n.t("club.btn_confirm", lang), callback_data="cok"),
        InlineKeyboardButton(i18n.t("club.btn_fix", lang), callback_data="cedit"),
    ]]
    if d["unknown"]:
        rows.append([InlineKeyboardButton(i18n.t("club.btn_add_move", lang), callback_data="cmv")])
    await message.reply_text(body, reply_markup=InlineKeyboardMarkup(rows))


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


def _mv_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("club.btn_dict", lang), callback_data="mv:dict"),
        InlineKeyboardButton(i18n.t("club.btn_new_as_is", lang), callback_data="mv:new"),
        InlineKeyboardButton(i18n.t("club.btn_skip_move", lang), callback_data="mv:skip"),
    ]])


async def _mv_ask(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Спросить про следующую нераспознанную фразу; очередь пуста -> перепарс и подтверждение."""
    lang = context.user_data.get("lang", "ru")
    queue = context.user_data.get("mv_queue") or []
    if not queue:
        con = botdb.connect(context.bot_data["db_path"])
        try:
            _restandardize(con, context.user_data["draft"])
        finally:
            con.close()
        await message.reply_text(i18n.t("club.mv_all_done", lang))
        await _show_confirm(message, context)
        return ADD_CONFIRM
    await message.reply_text(
        i18n.t("club.mv_ask", lang, phrase=queue[0]), reply_markup=_mv_kb(lang))
    return ADD_MOVE


async def mv_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    d = context.user_data.get("draft") or {}
    context.user_data["mv_queue"] = list(d.get("unknown") or [])
    return await _mv_ask(q.message, context)


async def mv_dict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "ru")
    con = botdb.connect(context.bot_data["db_path"])
    try:
        text = _dictionary_text(con, lang)
    finally:
        con.close()
    for chunk in _chunks(text):
        await q.message.reply_text(chunk)
    return ADD_MOVE


async def mv_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "ru")
    queue = context.user_data.get("mv_queue") or []
    if not queue:
        return await _mv_ask(q.message, context)
    phrase = queue.pop(0)
    slug = _slug(phrase)
    if not slug:
        await q.message.reply_text(i18n.t("club.mv_empty_slug", lang))
        return await _mv_ask(q.message, context)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        _register_canon(con, slug)
        botdb.add_alias(con, phrase, slug, source="manual")
    finally:
        con.close()
    await q.message.reply_text(i18n.t("club.mv_new_canon", lang, slug=slug, phrase=phrase))
    return await _mv_ask(q.message, context)


async def mv_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "ru")
    queue = context.user_data.get("mv_queue") or []
    phrase = queue.pop(0) if queue else ""
    await q.message.reply_text(i18n.t("club.mv_skipped", lang, phrase=phrase))
    return await _mv_ask(q.message, context)


async def mv_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ru")
    queue = context.user_data.get("mv_queue") or []
    if not queue:
        return await _mv_ask(update.message, context)
    name = (update.message.text or "").strip()
    phrase = queue[0]
    con = botdb.connect(context.bot_data["db_path"])
    try:
        aliases = botdb.load_aliases(con)
        canon = ontology.resolve(name, aliases)
        name_is_alias = canon is not None
        if not canon:
            found = ontology.find(name, aliases)
            canon = found[-1] if found else None
        if canon:
            queue.pop(0)
            botdb.add_alias(con, phrase, canon, source="manual")
            if not name_is_alias:
                botdb.add_alias(con, name, canon, source="manual")
            msg = i18n.t("club.mv_mapped", lang, phrase=phrase, canon=canon)
        else:
            queue.pop(0)
            slug = _slug(name)
            if not slug:
                await update.message.reply_text(i18n.t("club.mv_empty_slug", lang))
                queue.insert(0, phrase)
                return await _mv_ask(update.message, context)
            _register_canon(con, slug)
            botdb.add_alias(con, name, slug, source="manual")
            botdb.add_alias(con, phrase, slug, source="manual")
            msg = i18n.t("club.mv_new_from_name", lang, slug=slug, phrase=phrase)
    finally:
        con.close()
    await update.message.reply_text(msg)
    return await _mv_ask(update.message, context)


async def add_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "ru")
    d = context.user_data.get("draft")
    day = context.user_data.get("cday")
    if not d or not day:
        return ConversationHandler.END
    from .. import vision
    from tj.analysis.wod_program import parse_program
    con = botdb.connect(context.bot_data["db_path"])
    try:
        aliases = botdb.load_aliases(con)
    finally:
        con.close()
    # Claude один раз выверяет блоки шаблона: участники получат исправленную
    # форму без своих обращений к ИИ. Сбой -> blocks NULL, перепарсят raw_text.
    vblocks = None
    blocks = parse_program(d["raw_text"], aliases)
    if blocks and vision.engine_for(update.effective_user.id) == "claude" and vision.has_claude():
        await q.edit_message_text(i18n.t("club.checking_template", lang))
        checked, verified = vision.verify_result_blocks(d["raw_text"], blocks, aliases)
        if verified:
            vblocks = checked
    con = botdb.connect(context.bot_data["db_path"])
    try:
        con.execute('DELETE FROM wod_programs WHERE "day"=? AND "gym"=?',
                    (day.isoformat(), "Universe"))
        botdb.add_program(con, day.isoformat(), "Universe", d["raw_text"],
                          fmt=d["format"], movements=d["canon"], source=d["source"],
                          confirmed=1, blocks=vblocks)
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
            ADD_INPUT: [
                CallbackQueryHandler(add_retry, pattern=r"^cretry$"),
                MessageHandler(menu.not_menu_text() | filters.PHOTO, add_input),
            ],
            ADD_ENGINE: [CallbackQueryHandler(add_engine, pattern=r"^ceng:")],
            ADD_CONFIRM: [
                CallbackQueryHandler(add_ok, pattern=r"^cok$"),
                CallbackQueryHandler(add_edit, pattern=r"^cedit$"),
                CallbackQueryHandler(mv_start, pattern=r"^cmv$"),
                MessageHandler(menu.not_menu_text(), add_map),
            ],
            ADD_MOVE: [
                CallbackQueryHandler(mv_dict, pattern=r"^mv:dict$"),
                CallbackQueryHandler(mv_new, pattern=r"^mv:new$"),
                CallbackQueryHandler(mv_skip, pattern=r"^mv:skip$"),
                MessageHandler(menu.not_menu_text(), mv_text),
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
