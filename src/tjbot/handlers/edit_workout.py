"""Редактирование записанной тренировки: выбор -> меню полей -> правка поля.

Правит только ручные тренировки (source=manual). Права: текст доски доступен
только для своей тренировки (board_source=own); из зала (gym) - программа зала
правится в club.py, тут только результаты. Максы/доска/вес переиспользуют C1/B.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n
from .. import access
from .. import activity
from .. import db as botdb
from ..access import restricted
from . import menu
from .menu import BTN_EDIT, not_menu_text, show_menu, wizard_fallbacks
from .record_workout import _parse_lift_lines

PICK, MENU, ED_SCORE, ED_RPE, ED_BOARD, ED_MAXES, ED_WEIGHT = range(7)


def _label(r) -> str:
    day = r.get("day") or ""
    bits = [day[5:] if len(day) >= 10 else day, r.get("sport") or ""]
    if r.get("perf_score"):
        bits.append(str(r["perf_score"])[:20])
    return " · ".join(b for b in bits if b)


def _list_kb(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(_label(r), callback_data=f"ew:{r['activity_id']}")]
         for r in rows])


def field_menu(board_source: str, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(i18n.t("editworkout.field_score", lang), callback_data="ef:score"),
         InlineKeyboardButton(i18n.t("editworkout.field_rpe", lang), callback_data="ef:rpe")],
        [InlineKeyboardButton(i18n.t("editworkout.field_scaling", lang), callback_data="ef:scaling"),
         InlineKeyboardButton(i18n.t("editworkout.field_maxes", lang), callback_data="ef:maxes")],
    ]
    if board_source == "own":
        rows.append([InlineKeyboardButton(i18n.t("editworkout.field_board", lang), callback_data="ef:board")])
    rows.append([InlineKeyboardButton(i18n.t("editworkout.field_weight", lang), callback_data="ef:weight"),
                 InlineKeyboardButton(i18n.t("editworkout.field_done", lang), callback_data="ef:done")])
    return InlineKeyboardMarkup(rows)


async def _show_menu(message, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    await message.reply_text(
        i18n.t("editworkout.show_menu_prompt", lang),
        reply_markup=field_menu(context.user_data["edit_src"], lang))


def recompute(board_text: str, result_text: str, aliases):
    from tj.analysis.wod_program import parse_program
    from tj.analysis.wod_results import summarize_filled, extract_maxes
    blocks = parse_program(board_text or "", aliases)
    mdata, lines = summarize_filled(blocks, result_text)
    maxes = extract_maxes(blocks, result_text)
    return mdata, lines, maxes


@restricted
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, update.effective_user.id)
        rows = botdb.recent_manual_workouts(con, update.effective_user.id, 10)
    finally:
        con.close()
    if not rows:
        await update.effective_message.reply_text(i18n.t("editworkout.nothing_to_edit", lang))
        return ConversationHandler.END
    await update.effective_message.reply_text(i18n.t("editworkout.pick_workout", lang),
                                              reply_markup=_list_kb(rows))
    return PICK


def _log_edit_once(context, tg_id: int) -> None:
    """Одна правка на сессию редактирования: логируем при первом применённом
    изменении, дальше в этой же сессии — тихо. Флаг сбрасывается в pick()."""
    if not context.user_data.get("_edit_logged"):
        activity.log(context, tg_id, activity.WORKOUT_EDITED)
        context.user_data["_edit_logged"] = True


async def pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    activity_id = q.data.split(":", 1)[1]
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, update.effective_user.id)
        act = botdb.get_activity(con, activity_id, tg_id=update.effective_user.id)
    finally:
        con.close()
    if not act:
        await q.edit_message_text(i18n.t("editworkout.not_found", lang))
        return ConversationHandler.END
    context.user_data["edit_id"] = activity_id
    context.user_data["edit_day"] = act["day"]
    context.user_data["edit_src"] = act["board_source"]
    context.user_data["_edit_logged"] = False
    await q.edit_message_text(i18n.t("editworkout.editing_label", lang, label=_label(act)))
    await _show_menu(q.message, context, lang)
    return MENU


async def choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    field = q.data.split(":", 1)[1]
    prompts = {
        "score": i18n.t("editworkout.prompt_score", lang),
        "rpe": i18n.t("editworkout.prompt_rpe", lang),
        "board": i18n.t("editworkout.prompt_board", lang),
        "maxes": i18n.t("editworkout.prompt_maxes", lang),
        "weight": i18n.t("editworkout.prompt_weight", lang),
    }
    states = {"score": ED_SCORE, "rpe": ED_RPE, "board": ED_BOARD,
              "maxes": ED_MAXES, "weight": ED_WEIGHT}
    if field == "done":
        context.user_data.clear()
        await show_menu(update, context, "menu.done")
        return ConversationHandler.END
    if field == "scaling":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(i18n.t("editworkout.scaling_rx", lang), callback_data="es:rx"),
            InlineKeyboardButton(i18n.t("editworkout.scaling_scaled", lang), callback_data="es:scaled"),
            InlineKeyboardButton(i18n.t("editworkout.scaling_none", lang), callback_data="es:none"),
        ]])
        await q.message.reply_text(i18n.t("editworkout.ask_scaling", lang), reply_markup=kb)
        return MENU
    if field not in states:
        return MENU
    await q.message.reply_text(prompts[field])
    return states[field]


async def set_scaling(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    val = q.data.split(":", 1)[1]
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, update.effective_user.id)
        botdb.update_activity(con, context.user_data["edit_id"], tg_id=update.effective_user.id,
                              scaling=None if val == "none" else val)
    finally:
        con.close()
    _log_edit_once(context, update.effective_user.id)
    await q.edit_message_text(i18n.t("editworkout.scaling_updated", lang))
    await _show_menu(q.message, context, lang)
    return MENU


async def save_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_result = update.message.text.strip()
    activity_id = context.user_data["edit_id"]
    metcon_lines = []
    lift_lines = []
    con = botdb.connect(context.bot_data["db_path"])
    try:
        tg_id = update.effective_user.id
        lang = botdb.user_lang(con, tg_id)
        botdb.update_activity(con, activity_id, tg_id=tg_id, score=new_result)
        act = botdb.get_activity(con, activity_id, tg_id=tg_id)
        aliases = botdb.load_aliases(con)
        mdata, metcon_lines, maxes = recompute(
            (act or {}).get("board_text"), new_result, aliases)
        botdb.set_activity_metcon(con, activity_id, tg_id=tg_id, mdata=mdata)
        results, ambiguous = botdb.split_lifts(con, maxes)
        if results:
            botdb.record_lift_results(con, update.effective_user.id, results,
                                      context.user_data["edit_day"], activity_id)
            lift_lines = [i18n.t("editworkout.lift_line", lang, name=r["name"], weight=r["weight"])
                          for r in results]
    finally:
        con.close()
    from . import lift_disambig
    await lift_disambig.ask_ambiguous(update, context, ambiguous,
                                      context.user_data["edit_day"], activity_id, tg_id)
    _log_edit_once(context, update.effective_user.id)
    await update.message.reply_text(i18n.t("editworkout.score_updated", lang))
    if metcon_lines:
        await update.message.reply_text("\n".join(metcon_lines))
    if lift_lines:
        await update.message.reply_text(i18n.t("editworkout.credited_levels", lang, lines="\n".join(lift_lines)))
    await _show_menu(update.message, context, lang)
    return MENU


async def save_rpe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    txt = update.message.text.strip()
    if not txt.isdigit() or not (1 <= int(txt) <= 10):
        await update.message.reply_text(i18n.t("editworkout.rpe_invalid", lang))
        return ED_RPE
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.update_activity(con, context.user_data["edit_id"], tg_id=update.effective_user.id, rpe=int(txt))
    finally:
        con.close()
    _log_edit_once(context, update.effective_user.id)
    await update.message.reply_text(i18n.t("editworkout.rpe_updated", lang))
    await _show_menu(update.message, context, lang)
    return MENU


async def save_board(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from .. import vision
    text = update.message.text.strip()
    allow = vision.has_vision() and access.llm_quota_consume(update.effective_user.id)
    draft = vision.parse_text(text, use_llm=allow)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, update.effective_user.id)
        botdb.set_activity_board(con, context.user_data["edit_id"], tg_id=update.effective_user.id,
                                 raw_text=draft.get("raw_text") or text, fmt=draft.get("format"))
    finally:
        con.close()
    _log_edit_once(context, update.effective_user.id)
    await update.message.reply_text(i18n.t("editworkout.board_updated", lang))
    await _show_menu(update.message, context, lang)
    return MENU


async def save_maxes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from .. import vision
    text = update.message.text
    parsed = None
    if vision.has_vision() and access.llm_quota_consume(update.effective_user.id):
        parsed = vision.parse_lifts(text)
    if not parsed:
        parsed = _parse_lift_lines(text)
    results, ambiguous = [], []
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, update.effective_user.id)
        results, ambiguous = botdb.split_lifts(con, parsed)
        if results:
            botdb.record_lift_results(con, update.effective_user.id, results,
                                      context.user_data["edit_day"],
                                      context.user_data["edit_id"])
    finally:
        con.close()
    from . import lift_disambig
    await lift_disambig.ask_ambiguous(update, context, ambiguous,
                                      context.user_data["edit_day"],
                                      context.user_data["edit_id"], update.effective_user.id)
    if results:
        _log_edit_once(context, update.effective_user.id)
        lines = "\n".join(i18n.t("editworkout.lift_line", lang, name=r["name"], weight=r["weight"])
                           for r in results)
        await update.message.reply_text(i18n.t("editworkout.maxes_credited", lang, lines=lines))
    else:
        await update.message.reply_text(i18n.t("editworkout.maxes_not_recognized", lang))
    await _show_menu(update.message, context, lang)
    return MENU


async def save_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    txt = update.message.text.strip()
    try:
        kg = float(txt.replace(",", "."))
    except ValueError:
        await update.message.reply_text(i18n.t("editworkout.weight_invalid", lang))
        return ED_WEIGHT
    if kg <= 0:
        await update.message.reply_text(i18n.t("editworkout.weight_invalid", lang))
        return ED_WEIGHT
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.set_bodyweight(con, context.user_data["edit_day"], kg, tg_id=update.effective_user.id)
    finally:
        con.close()
    _log_edit_once(context, update.effective_user.id)
    await update.message.reply_text(i18n.t("editworkout.weight_updated", lang))
    await _show_menu(update.message, context, lang)
    return MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await show_menu(update, context, "menu.cancelled_short")
    return ConversationHandler.END


def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Text(menu.btn_variants("btn.edit")), entry)],
        states={
            PICK: [CallbackQueryHandler(pick, pattern=r"^ew:")],
            MENU: [
                CallbackQueryHandler(choose_field, pattern=r"^ef:"),
                CallbackQueryHandler(set_scaling, pattern=r"^es:"),
            ],
            ED_SCORE: [MessageHandler(not_menu_text(), save_score)],
            ED_RPE: [MessageHandler(not_menu_text(), save_rpe)],
            ED_BOARD: [MessageHandler(not_menu_text(), save_board)],
            ED_MAXES: [MessageHandler(not_menu_text(), save_maxes)],
            ED_WEIGHT: [MessageHandler(not_menu_text(), save_weight)],
        },
        fallbacks=wizard_fallbacks(),
        name="edit_workout",
    )
