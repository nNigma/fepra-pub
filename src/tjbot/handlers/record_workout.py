"""Мастер "Записать тренировку": дата -> тип -> (кроссфит: программа зала Universe
или своя доска) -> результат -> (силовые в уровни) -> вес тела.

Пишет тренировку в training.db (source=manual). Данные с часов (пульс/калории)
прилетят отдельно при синхронизации и смёрджатся по дате.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, Update)
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n
from tj.models import (BOARD_SPORTS, Activity, Scaling, Sport,
                       StrengthWodDetails, WodFormat, WodPerformed,
                       WodPrescription)
from .. import access
from .. import activity
from .. import db as botdb
from ..access import restricted

from . import menu
from .menu import not_menu_text, show_menu, wizard_fallbacks
from .record_result import parse_lift


(DATE, DATE_INPUT, SPORT, UNIVERSE_ASK, BOARD, BOARD_ENGINE, BOARD_CONFIRM, RESULT,
 MAX_CONFIRM, MAX_EDIT, BODYWEIGHT) = range(11)

_SPORTS = {"crossfit": Sport.CROSSFIT, "weightlifting": Sport.WEIGHTLIFTING,
           "hyrox": Sport.HYROX, "run": Sport.RUN, "bike": Sport.BIKE}


def _llm_limit_msg(lang: str) -> str:
    return i18n.t("record.llm_limit", lang, limit=access.LLM_DAILY_LIMIT)


@restricted
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("record.btn_today", lang), callback_data="d:today"),
        InlineKeyboardButton(i18n.t("record.btn_yesterday", lang), callback_data="d:yesterday"),
        InlineKeyboardButton(i18n.t("record.btn_other_date", lang), callback_data="d:other"),
    ]])
    await update.effective_message.reply_text(i18n.t("record.ask_date", lang), reply_markup=kb)
    return DATE


def _tz(context) -> ZoneInfo:
    return ZoneInfo(context.bot_data.get("tz", "UTC"))


async def pick_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    choice = q.data.split(":", 1)[1]
    today = datetime.now(_tz(context)).date()
    if choice == "today":
        context.user_data["date"] = today
    elif choice == "yesterday":
        context.user_data["date"] = today - timedelta(days=1)
    else:
        await q.edit_message_text(i18n.t("record.ask_date_input", lang))
        return DATE_INPUT
    await q.edit_message_text(i18n.t("record.date_chosen", lang, date=context.user_data["date"]))
    return await _ask_sport(q.message, context, lang)


def _parse_date(txt: str, today: date) -> date | None:
    txt = txt.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m"):
        try:
            d = datetime.strptime(txt, fmt).date()
            return d.replace(year=today.year) if fmt == "%d.%m" else d
        except ValueError:
            continue
    return None


async def date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    d = _parse_date(update.message.text, datetime.now(_tz(context)).date())
    if d is None:
        await update.message.reply_text(i18n.t("record.date_invalid", lang))
        return DATE_INPUT
    context.user_data["date"] = d
    await update.message.reply_text(i18n.t("record.date_chosen", lang, date=d))
    return await _ask_sport(update.message, context, lang)


async def _ask_sport(message, context: ContextTypes.DEFAULT_TYPE, lang: str) -> int:
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(i18n.t("record.btn_crossfit", lang), callback_data="s:crossfit"),
            InlineKeyboardButton(i18n.t("record.btn_weightlifting", lang),
                                 callback_data="s:weightlifting"),
            InlineKeyboardButton(i18n.t("record.btn_hyrox", lang), callback_data="s:hyrox"),
        ],
        [
            InlineKeyboardButton(i18n.t("record.btn_run", lang), callback_data="s:run"),
            InlineKeyboardButton(i18n.t("record.btn_bike", lang), callback_data="s:bike"),
        ],
    ])
    await message.reply_text(i18n.t("record.ask_sport", lang), reply_markup=kb)
    return SPORT


async def pick_sport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    context.user_data["sport"] = _SPORTS[q.data.split(":", 1)[1]]
    await q.edit_message_text(i18n.t("record.sport_chosen", lang, sport=context.user_data["sport"].value))
    if context.user_data["sport"] in BOARD_SPORTS:
        await q.message.reply_text(i18n.t("record.ask_board", lang))
        return BOARD
    await q.message.reply_text(i18n.t("record.ask_result_cardio", lang))
    return RESULT


def _board_confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("record.btn_board_yes", lang), callback_data="bconf:ok"),
        InlineKeyboardButton(i18n.t("record.btn_board_edit", lang), callback_data="bconf:edit"),
    ]])


def _engine_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("record.btn_engine_fast", lang), callback_data="beng:fast"),
        InlineKeyboardButton(i18n.t("record.btn_engine_slow", lang), callback_data="beng:slow"),
    ]])


def _board_failed_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("record.btn_retry_recognize", lang), callback_data="bretry"),
    ]])


def _offer_engine_choice() -> bool:
    """Показывать ли выбор движка доски: только когда Claude-vision доступен
    (включён и есть CLI). Иначе фото идёт сразу в Gemini."""
    from .. import vision
    return vision.has_claude()


def _result_prompt(lang: str) -> str:
    return i18n.t("record.ask_result_strength", lang)


async def _ask_board_confirm(message, context: ContextTypes.DEFAULT_TYPE, lang: str) -> int:
    from tj.analysis.wod_program import annotate
    board_text = context.user_data.get("board_text", "—")
    shown = annotate(board_text)
    await message.reply_text(
        i18n.t("record.board_recognized", lang, shown=shown),
        reply_markup=_board_confirm_kb(lang))
    return BOARD_CONFIRM


async def board(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from .. import vision
    msg = update.message
    context.user_data["board_source"] = "own"
    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid)
    con.close()
    editing = context.user_data.pop("board_editing", False)
    if msg.photo:
        context.user_data["board_photo"] = msg.photo[-1].file_id
        if not vision.has_vision():
            context.user_data["board_text"] = "[фото доски — не распознано]"
            await msg.reply_text(
                i18n.t("record.board_not_recognized_head", lang)
                + i18n.t("record.ask_board_text_fallback", lang))
            return BOARD
        if _offer_engine_choice():
            await msg.reply_text(i18n.t("record.ask_engine", lang), reply_markup=_engine_kb(lang))
            return BOARD_ENGINE
        return await _parse_board_photo(msg, context, lang, "gemini", uid)
    if msg.text and msg.text.strip().lower() != "пропустить":
        text = msg.text.strip()
        if editing:
            context.user_data["board_text"] = text          # правку берём как есть, без ИИ
        else:
            allow = vision.has_vision() and access.llm_quota_consume(uid)
            draft = vision.parse_text(text, use_llm=allow)
            context.user_data["board_text"] = draft.get("raw_text") or text
            if draft.get("format"):
                context.user_data["wod_format"] = draft["format"]
        return await _ask_board_confirm(msg, context, lang)
    await msg.reply_text(_result_prompt(lang))                 # «пропустить» — без доски
    return RESULT


async def _parse_board_photo(message, context: ContextTypes.DEFAULT_TYPE,
                             lang: str, engine: str, uid: int) -> int:
    """Скачать фото доски и распознать выбранным движком. Общий код для выбора
    движка (Claude вкл) и прямого Gemini-пути (Claude выкл)."""
    file_id = context.user_data.get("board_photo")
    if not file_id:
        await message.reply_text(_result_prompt(lang))
        return RESULT
    if not access.llm_quota_consume(uid):
        context.user_data["board_text"] = "[фото доски — не распознано]"
        await message.reply_text(_llm_limit_msg(lang) + i18n.t("record.ask_board_text_fallback", lang))
        return BOARD
    await message.reply_text(i18n.t(
        "record.parsing_photo_slow" if engine == "claude" else "record.parsing_photo", lang))
    from .. import vision
    draft = None
    try:
        f = await context.bot.get_file(file_id)
        buf = await f.download_as_bytearray()
        draft = vision.parse_board(bytes(buf), engine=engine)
    except Exception:
        draft = None
    if draft and draft.get("raw_text"):
        context.user_data["board_text"] = draft["raw_text"]
        if draft.get("format"):
            context.user_data["wod_format"] = draft["format"]
        if draft.get("engine_used") and draft["engine_used"] != engine:
            await message.reply_text(i18n.t("record.board_engine_swapped", lang))
        return await _ask_board_confirm(message, context, lang)
    context.user_data["board_text"] = "[фото доски — не распознано]"
    await message.reply_text(
        i18n.t("record.board_not_recognized_head", lang)
        + i18n.t("record.ask_board_text_fallback", lang),
        reply_markup=_board_failed_kb(lang))
    return BOARD


async def board_engine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор движка распознавания доски: быстрый Gemini или медленный Claude."""
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid)
    con.close()
    engine = "claude" if q.data == "beng:slow" else "gemini"
    return await _parse_board_photo(q.message, context, lang, engine, uid)


async def board_retry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """«Попробовать ещё раз» после сбоя распознавания: переспрашиваем движок по
    сохранённому фото (разовый залёт Gemini/деплой не выкидывает из распознавания)."""
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid)
    con.close()
    if not context.user_data.get("board_photo"):
        await q.edit_message_text(_result_prompt(lang))
        return RESULT
    if _offer_engine_choice():
        await q.edit_message_text(i18n.t("record.ask_engine", lang), reply_markup=_engine_kb(lang))
        return BOARD_ENGINE
    return await _parse_board_photo(q.message, context, lang, "gemini", uid)


async def board_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    if q.data != "bconf:ok":
        context.user_data["board_editing"] = True
        await q.edit_message_text(i18n.t("record.board_edit_intro", lang))
        await q.message.reply_text(context.user_data.get("board_text", "—"))
        await q.message.reply_text(i18n.t("record.board_edit_instruction", lang))
        return BOARD
    await q.edit_message_text(i18n.t("record.board_accepted", lang))
    board_text = context.user_data.get("board_text", "")
    tmpl = None
    context.user_data["blocks_verified"] = False
    if board_text and board_text != "[фото доски — не распознано]":
        from tj.analysis.wod_program import parse_program, render_template
        from .. import vision
        con = botdb.connect(context.bot_data["db_path"])
        try:
            aliases = vision.enrich_aliases(con, board_text)
        finally:
            con.close()
        blocks = parse_program(board_text, aliases)
        # админ = свой контент: Claude молча сверяет шаблон с доской (фолбэк — как распарсилось)
        if blocks and vision.engine_for(q.from_user.id) == "claude" and vision.has_claude():
            await q.message.reply_text(i18n.t("record.checking_template", lang))
            blocks, verified = vision.verify_result_blocks(board_text, blocks, aliases)
            context.user_data["blocks_verified"] = verified
        if blocks:
            context.user_data["result_blocks"] = blocks
            tmpl = render_template(blocks)
    if tmpl:
        await q.message.reply_text(i18n.t("record.fill_results_template", lang))
        await q.message.reply_text(tmpl[:3500], reply_markup=results_help_kb(lang))
    else:
        await q.message.reply_text(_result_prompt(lang))
    return RESULT


def results_help_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        i18n.t("record.btn_results_help", lang), callback_data="reshelp")]])


async def results_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    await q.message.reply_text(i18n.t("onboarding.results_guide", lang))
    return None


_RPE_RE = re.compile(r"rpe\s*[:=]?\s*(\d{1,2})", re.IGNORECASE)


def _build_activity(ud: dict, tz: ZoneInfo, tg_id: int) -> Activity:
    d: date = ud["date"]
    sport: Sport = ud["sport"]
    start = datetime.combine(d, time(12, 0), tzinfo=tz)
    act = Activity(source="manual", sport=sport, start=start,
                   activity_id=f"manual-{tg_id}-{d.isoformat()}-{sport.value}")
    result = ud.get("result", "")
    rpe = int(m.group(1)) if (m := _RPE_RE.search(result)) else None
    if sport in BOARD_SPORTS:
        scaling = Scaling.SCALED if "scal" in result.lower() or "скейл" in result.lower() else (
            Scaling.RX if "rx" in result.lower() else None)
        presc = WodPrescription(raw_text=ud.get("board_text"))
        if wf := ud.get("wod_format"):
            try:
                presc.format = WodFormat(wf)
            except ValueError:
                pass
        act.strength = StrengthWodDetails(
            presc, WodPerformed(scaling=scaling, score=result or None, rpe=rpe))
        act.extra = {"board_text": ud.get("board_text"),
                     "board_source": ud.get("board_source", "own")}
    return act


def _board_activity(day, board_text, board_source, result_text, tz: ZoneInfo,
                    tg_id: int, wod_format=None, sport: Sport = Sport.CROSSFIT) -> Activity:
    """Активность с доской (source=manual) из даты, доски и текста результата.
    Кроссфит, ТА и Hyrox проходят одним путём — отличается только тип."""
    start = datetime.combine(day, time(12, 0), tzinfo=tz)
    act = Activity(source="manual", sport=sport, start=start,
                   activity_id=f"manual-{tg_id}-{day.isoformat()}-{sport.value}")
    rpe = int(m.group(1)) if (m := _RPE_RE.search(result_text or "")) else None
    low = (result_text or "").lower()
    scaling = Scaling.SCALED if "scal" in low or "скейл" in low else (
        Scaling.RX if "rx" in low else None)
    presc = WodPrescription(raw_text=board_text)
    if wod_format:
        try:
            presc.format = WodFormat(wod_format)
        except ValueError:
            pass
    act.strength = StrengthWodDetails(
        presc, WodPerformed(scaling=scaling, score=result_text or None, rpe=rpe))
    act.extra = {"board_text": board_text, "board_source": board_source}
    return act


async def save_filled_result(update, context, day, board_text, board_source,
                             result_text, blocks, verified=False,
                             sport: Sport = Sport.CROSSFIT):
    """Сохранить заполненный результат кроссфит-тренировки: активность + метконы + максы.
    Максы пишутся сразу в уровни (record_lift_results), как в edit_workout.
    Возвращает (results, metcon_lines, activity_id). Общее для record и add_result."""
    from tj.analysis.wod_results import summarize_filled, extract_maxes
    tg_id = update.effective_user.id
    act = _board_activity(day, board_text, board_source, result_text, _tz(context),
                          tg_id, sport=sport)
    mdata, metcon_lines = summarize_filled(blocks, result_text)
    act.extra["metcon"] = mdata
    act.extra["result_blocks"] = blocks
    if verified:
        act.extra["blocks_verified"] = "claude"
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.insert_activity(con, act, tg_id)
        maxes = extract_maxes(blocks, result_text)
        results, ambiguous = botdb.split_lifts(con, maxes)
        if results:
            botdb.record_lift_results(con, tg_id, results,
                                      day.isoformat(), act.activity_id)
    finally:
        con.close()
    from . import lift_disambig
    await lift_disambig.ask_ambiguous(update, context, ambiguous,
                                      day.isoformat(), act.activity_id, tg_id)
    return results, metcon_lines, act.activity_id


async def result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from .. import vision
    context.user_data["result"] = update.message.text.strip()
    tg_id = update.effective_user.id
    act = _build_activity(context.user_data, _tz(context), tg_id)
    filled_blocks = context.user_data.get("result_blocks")
    metcon_lines = []
    results = []
    context.user_data["lift_ambiguous"] = []
    max_limited = False
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, tg_id)
        if filled_blocks:
            from tj.analysis.wod_results import summarize_filled, extract_maxes
            mdata, metcon_lines = summarize_filled(filled_blocks, context.user_data["result"])
            if act.extra is None:
                act.extra = {}
            act.extra["metcon"] = mdata
            act.extra["result_blocks"] = filled_blocks
            if context.user_data.get("blocks_verified"):
                act.extra["blocks_verified"] = "claude"
            botdb.insert_activity(con, act, tg_id)
            maxes = extract_maxes(filled_blocks, context.user_data["result"])
            results, ambiguous = botdb.split_lifts(con, maxes)
            context.user_data["lift_ambiguous"] = ambiguous
        else:
            botdb.insert_activity(con, act, tg_id)
            if act.sport in BOARD_SPORTS and any(c.isdigit() for c in context.user_data["result"]):
                if vision.has_vision() and access.llm_quota_consume(update.effective_user.id, con):
                    parsed = vision.parse_lifts(context.user_data["result"])
                    results, ambiguous = botdb.split_lifts(con, parsed or [])
                    context.user_data["lift_ambiguous"] = ambiguous
                elif vision.has_vision():
                    max_limited = True
    finally:
        con.close()
    activity.log(context, tg_id, activity.WORKOUT_RECORDED)
    context.user_data["activity_id"] = act.activity_id
    context.user_data["activity_day"] = act.start.date().isoformat()
    summary = i18n.t("record.workout_summary", lang, sport=act.sport.value, date=act.start.date())
    if act.strength and act.strength.performed.rpe:
        summary += i18n.t("record.rpe_suffix", lang, rpe=act.strength.performed.rpe)
    await update.message.reply_text(summary + ".")
    if metcon_lines:
        await update.message.reply_text("\n".join(metcon_lines))
    if results:
        context.user_data["lift_results"] = results
        await _show_max_confirm(update.message, results, lang)
        return MAX_CONFIRM
    if context.user_data.get("lift_ambiguous"):
        from . import lift_disambig
        await lift_disambig.ask_ambiguous(update, context, context.user_data["lift_ambiguous"],
                                          context.user_data["activity_day"],
                                          context.user_data["activity_id"], tg_id)
    if max_limited:
        await update.message.reply_text(_llm_limit_msg(lang) + i18n.t("record.max_skip_note", lang))
    await update.message.reply_text(i18n.t("record.ask_bodyweight", lang))
    return BODYWEIGHT


from tj.analysis.parse_input import parse_lift_lines as _parse_lift_lines  # noqa: E402,F401  реэкспорт


async def _ask_bodyweight(message, lang: str) -> None:
    await message.reply_text(i18n.t("record.ask_bodyweight", lang))


async def _show_max_confirm(message, results, lang: str) -> None:
    if results:
        lines = "\n".join(
            i18n.t("record.max_lift_line", lang, name=r["name"], weight=r["weight"], reps=r["reps"])
            for r in results)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(i18n.t("record.btn_max_yes", lang), callback_data="max:ok"),
             InlineKeyboardButton(i18n.t("record.btn_max_edit", lang), callback_data="max:edit")],
            [InlineKeyboardButton(i18n.t("record.btn_max_skip", lang), callback_data="max:skip")]])
        await message.reply_text(i18n.t("record.max_confirm_intro", lang, lines=lines), reply_markup=kb)
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(i18n.t("record.btn_max_edit_manual", lang), callback_data="max:edit"),
             InlineKeyboardButton(i18n.t("record.btn_max_skip", lang), callback_data="max:skip")]])
        await message.reply_text(i18n.t("record.max_not_recognized", lang), reply_markup=kb)


async def max_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    results = context.user_data.get("lift_results") or []
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, q.from_user.id)
        botdb.record_lift_results(con, q.from_user.id, results,
                                  context.user_data["activity_day"],
                                  context.user_data["activity_id"])
    finally:
        con.close()
    await q.edit_message_text(i18n.t("record.max_saved", lang))
    from . import lift_disambig
    await lift_disambig.ask_ambiguous(update, context, context.user_data.get("lift_ambiguous") or [],
                                      context.user_data["activity_day"],
                                      context.user_data["activity_id"], q.from_user.id)
    context.user_data.pop("lift_ambiguous", None)
    await _ask_bodyweight(q.message, lang)
    return BODYWEIGHT


async def max_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    context.user_data.pop("lift_ambiguous", None)
    await q.edit_message_text(i18n.t("record.max_skipped", lang))
    await _ask_bodyweight(q.message, lang)
    return BODYWEIGHT


async def max_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, q.from_user.id)
    con.close()
    await q.message.reply_text(i18n.t("record.ask_max_edit", lang))
    return MAX_EDIT


async def max_edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    parsed = _parse_lift_lines(update.message.text)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, update.effective_user.id)
        results, ambiguous = botdb.split_lifts(con, parsed)
    finally:
        con.close()
    context.user_data["lift_results"] = results
    context.user_data["lift_ambiguous"] = ambiguous
    await _show_max_confirm(update.message, results, lang)
    return MAX_CONFIRM


async def bodyweight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    try:
        kg = float(txt.replace(",", "."))
    except ValueError:
        await update.message.reply_text(i18n.t("record.bodyweight_invalid", lang))
        return BODYWEIGHT
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.set_bodyweight(con, context.user_data["activity_day"], kg,
                             update.effective_user.id)
    finally:
        con.close()
    context.user_data.clear()
    await show_menu(update, context, "menu.workout_saved")
    return ConversationHandler.END


async def skip_bodyweight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await show_menu(update, context, "menu.workout_saved")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await show_menu(update, context, "menu.cancelled_short")
    return ConversationHandler.END


def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Text(menu.btn_variants("btn.add_workout")), entry)],
        states={
            DATE: [CallbackQueryHandler(pick_date, pattern=r"^d:")],
            DATE_INPUT: [MessageHandler(not_menu_text(), date_input)],
            SPORT: [CallbackQueryHandler(pick_sport, pattern=r"^s:")],
            BOARD: [
                CallbackQueryHandler(board_retry, pattern=r"^bretry$"),
                MessageHandler(not_menu_text() | filters.PHOTO, board),
            ],
            BOARD_ENGINE: [CallbackQueryHandler(board_engine, pattern=r"^beng:")],
            BOARD_CONFIRM: [CallbackQueryHandler(board_confirm, pattern=r"^bconf:")],
            RESULT: [MessageHandler(not_menu_text(), result),
                     CallbackQueryHandler(results_help, pattern=r"^reshelp$")],
            MAX_CONFIRM: [
                CallbackQueryHandler(max_ok, pattern=r"^max:ok$"),
                CallbackQueryHandler(max_edit, pattern=r"^max:edit$"),
                CallbackQueryHandler(max_skip, pattern=r"^max:skip$"),
            ],
            MAX_EDIT: [MessageHandler(not_menu_text(), max_edit_save)],
            BODYWEIGHT: [
                MessageHandler(not_menu_text(), bodyweight),
                CommandHandler("skip", skip_bodyweight),
            ],
        },
        fallbacks=wizard_fallbacks(),
        name="record_workout",
    )
