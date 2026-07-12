"""Питание: подменю «🍽 Питание» — запись еды по фото (за дату), вода,
редактирование, просмотр дня, отчёт в Mini App.

Фото принимается ТОЛЬКО внутри потока «📸 Записать» (случайные фото в чат
больше не считаются едой), но вместо фото можно прислать текстовое описание
еды — оно сохраняется в note и по нему же идёт перепарс при правке. Разбор
еды — только Pro (запись/правка за гейтом); движок — Claude с фолбэком на
Gemini, не-админ под дневной квотой. «Поправить» — текст-уточнение, парс
повторяется с ним (у сохранённого приёма — по хранимому фото или note).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, Update)
from telegram.ext import (CallbackQueryHandler, ContextTypes, ConversationHandler,
                          MessageHandler, filters)

from tj import i18n
from tj.analysis import nutrition as nutr
from .. import access
from .. import activity
from .. import db as botdb
from .. import vision
from . import menu
from .menu import not_menu_text
from .record_workout import _parse_date, _tz

R_DATE, R_DATE_INPUT, R_PHOTO, R_CONFIRM, R_CORR = range(5)          # запись
E_DATE, E_DATE_INPUT, E_PICK, E_CORR, E_CONFIRM = range(10, 15)      # редактор
V_DATE, V_DATE_INPUT = range(20, 22)                                 # просмотр


# --- общее -----------------------------------------------------------------

def _lang(context, uid: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


def _fmt_num(x) -> str:
    if x is None:
        return "—"
    return str(int(x)) if float(x) == int(x) else str(round(x, 1))


def nutrition_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[i18n.t("btn.meal_record", lang), i18n.t("btn.meal_water", lang)],
         [i18n.t("btn.meal_edit", lang), i18n.t("btn.meal_view", lang)],
         [i18n.t("btn.meal_report", lang)],
         [i18n.t("btn.back", lang)]],
        resize_keyboard=True)


def _date_kb(prefix: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("record.btn_today", lang), callback_data=f"{prefix}:today"),
        InlineKeyboardButton(i18n.t("record.btn_yesterday", lang), callback_data=f"{prefix}:yest"),
        InlineKeyboardButton(i18n.t("record.btn_other_date", lang), callback_data=f"{prefix}:other"),
    ]])


def _resolve_day(choice: str, context) -> str | None:
    today = datetime.now(_tz(context)).date()
    if choice == "today":
        return today.isoformat()
    if choice == "yest":
        return (today - timedelta(days=1)).isoformat()
    return None


def _pro_only(uid: int) -> bool:
    return not (access.is_admin(uid) or access.is_pro(uid))


@access.restricted
async def open_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    if _pro_only(uid):
        await update.effective_message.reply_text(i18n.t("meal.pro_only", lang))
        return
    await update.effective_message.reply_text(
        i18n.t("meal.menu_intro", lang), reply_markup=nutrition_kb(lang))


# --- запись: дата -> фото -> карточка -> подтверждение ----------------------


@access.restricted
async def rec_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    if _pro_only(uid):
        await update.effective_message.reply_text(i18n.t("meal.pro_only", lang))
        return ConversationHandler.END
    await update.effective_message.reply_text(
        i18n.t("meal.ask_date", lang), reply_markup=_date_kb("mrd", lang))
    return R_DATE


async def rec_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    day = _resolve_day(q.data.split(":", 1)[1], context)
    if day is None:
        await q.edit_message_text(i18n.t("record.ask_date_input", lang))
        return R_DATE_INPUT
    context.user_data["meal_day"] = day
    await q.edit_message_text(i18n.t("record.date_chosen", lang, date=day))
    await q.message.reply_text(i18n.t("meal.ask_photo", lang))
    return R_PHOTO


async def rec_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    d = _parse_date(update.message.text, datetime.now(_tz(context)).date())
    if d is None:
        await update.message.reply_text(i18n.t("record.date_invalid", lang))
        return R_DATE_INPUT
    context.user_data["meal_day"] = d.isoformat()
    await update.message.reply_text(i18n.t("record.date_chosen", lang, date=d))
    await update.message.reply_text(i18n.t("meal.ask_photo", lang))
    return R_PHOTO


def _card_text(draft: dict, lang: str) -> str:
    lines = [i18n.t("meal.card_head", lang)]
    for f in draft["foods"]:
        lines.append(i18n.t("meal.card_food", lang, name=f["name"],
                            grams=_fmt_num(f.get("grams")), kcal=_fmt_num(f.get("kcal"))))
    t = draft["totals"]
    lines.append("")
    lines.append(i18n.t("meal.card_totals", lang, kcal=_fmt_num(t["kcal"]),
                        p=_fmt_num(t["protein_g"]), f=_fmt_num(t["fat_g"]),
                        c=_fmt_num(t["carb_g"])))
    if draft.get("question"):
        lines.append("")
        lines.append(i18n.t("meal.card_question", lang, q=draft["question"]))
    return "\n".join(lines)


def _card_kb(prefix: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("meal.btn_save", lang), callback_data=f"{prefix}:ok"),
        InlineKeyboardButton(i18n.t("meal.btn_edit", lang), callback_data=f"{prefix}:edit"),
        InlineKeyboardButton(i18n.t("meal.btn_cancel", lang), callback_data=f"{prefix}:cancel"),
    ]])


async def _parse_draft(msg, context, uid: int, lang: str, prefix: str):
    """Парсит приём из user_data: meal_photo (фото) или meal_desc (описание
    словами), с НАКОПЛЕННЫМИ уточнениями (meal_notes - каждый пересчёт видит
    их все), показывает карточку. -> True, если карточка показана."""
    photo_id = context.user_data.get("meal_photo")
    desc = context.user_data.get("meal_desc")
    if not photo_id and not desc:
        return False
    notes = context.user_data.get("meal_notes") or []
    correction = "; ".join(notes) if notes else None
    await msg.reply_text(i18n.t("meal.parsing", lang))
    try:
        if photo_id:
            f = await context.bot.get_file(photo_id)
            buf = await f.download_as_bytearray()
            draft = vision.parse_meal(bytes(buf), engine=vision.engine_for(uid),
                                      correction=correction)
        else:
            draft = vision.parse_meal_text(desc, engine=vision.engine_for(uid),
                                           correction=correction)
    except Exception as e:
        print(f"[meal] парс не удался: {type(e).__name__}", flush=True)
        draft = None
    if not draft:
        await msg.reply_text(i18n.t("meal.not_recognized", lang))
        return False
    context.user_data["meal_draft"] = draft
    await msg.reply_text(_card_text(draft, lang), reply_markup=_card_kb(prefix, lang))
    return True


async def rec_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    if not access.is_admin(uid) and not access.llm_quota_consume(uid):
        await update.message.reply_text(
            i18n.t("meal.llm_limit", lang, limit=access.LLM_DAILY_LIMIT))
        return ConversationHandler.END
    context.user_data.pop("meal_desc", None)
    context.user_data["meal_photo"] = update.message.photo[-1].file_id
    caption = (update.message.caption or "").strip()   # подпись к фото = уточнение
    context.user_data["meal_notes"] = [caption] if caption else []
    ok = await _parse_draft(update.message, context, uid, lang, "mr")
    return R_CONFIRM if ok else R_PHOTO


async def rec_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    text = (update.message.text or "").strip()
    if len(text) < 3:
        await update.message.reply_text(i18n.t("meal.ask_photo", lang))
        return R_PHOTO
    if not access.is_admin(uid) and not access.llm_quota_consume(uid):
        await update.message.reply_text(
            i18n.t("meal.llm_limit", lang, limit=access.LLM_DAILY_LIMIT))
        return ConversationHandler.END
    context.user_data.pop("meal_photo", None)
    context.user_data["meal_desc"] = text[:600]
    context.user_data["meal_notes"] = []
    ok = await _parse_draft(update.message, context, uid, lang, "mr")
    return R_CONFIRM if ok else R_PHOTO


def _meal_ts(day: str, context) -> str:
    now = datetime.now(_tz(context))
    if day == now.date().isoformat():
        return now.isoformat(timespec="seconds")
    return f"{day}T12:00:00"


async def rec_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = _lang(context, uid)
    action = q.data.split(":", 1)[1]
    if action == "cancel":
        await q.edit_message_text(i18n.t("meal.cancelled", lang))
        return _clear_end(context)
    if action == "edit":
        await q.edit_message_text(i18n.t("meal.ask_correction", lang))
        return R_CORR
    draft = context.user_data.get("meal_draft")
    day = context.user_data.get("meal_day")
    if not draft or not day:
        await q.edit_message_text(i18n.t("meal.context_lost", lang))
        return _clear_end(context)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.add_meal(con, uid, day, _meal_ts(day, context),
                       draft["foods"], draft["totals"],
                       note=context.user_data.get("meal_desc"),
                       photo_id=context.user_data.get("meal_photo"),
                       engine=vision.engine_for(uid),
                       quality=draft.get("quality"), quality_note=draft.get("quality_note"))
        day_rows = botdb.meals_for_day(con, uid, day)
    finally:
        con.close()
    activity.log(context, uid, activity.MEAL_ADDED)
    day_tot = nutr.day_totals(day_rows)
    await q.edit_message_text(
        i18n.t("meal.saved", lang, kcal=_fmt_num(draft["totals"]["kcal"]))
        + i18n.t("meal.saved_day", lang, day=day, kcal=_fmt_num(day_tot["kcal"]),
                 p=_fmt_num(day_tot["protein_g"])))
    return _clear_end(context)


async def rec_correction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    text = (update.message.text or "").strip()
    if len(text) < 2:
        await update.message.reply_text(i18n.t("meal.ask_correction", lang))
        return R_CORR
    context.user_data.setdefault("meal_notes", []).append(text)
    ok = await _parse_draft(update.message, context, uid, lang, "mr")
    return R_CONFIRM if ok else _clear_end(context)


def _clear_end(context) -> int:
    for k in ("meal_draft", "meal_photo", "meal_desc", "meal_day",
              "meal_edit_id", "meal_edit_ts", "meal_notes"):
        context.user_data.pop(k, None)
    return ConversationHandler.END


# --- вода -------------------------------------------------------------------

def _water_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("+0.25", callback_data="water:0.25"),
        InlineKeyboardButton("+0.5", callback_data="water:0.5"),
        InlineKeyboardButton("−0.25", callback_data="water:-0.25"),
    ]])


@access.restricted
async def water_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    if _pro_only(uid):
        await update.effective_message.reply_text(i18n.t("meal.pro_only", lang))
        return
    day = datetime.now(_tz(context)).date().isoformat()
    con = botdb.connect(context.bot_data["db_path"])
    try:
        cur = botdb.water_for_day(con, uid, day)
    finally:
        con.close()
    await update.effective_message.reply_text(
        i18n.t("meal.water_head", lang, v=cur), reply_markup=_water_kb(lang))


async def water_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    uid = q.from_user.id
    lang = _lang(context, uid)
    try:
        delta = float(q.data.split(":", 1)[1])
    except ValueError:
        await q.answer()
        return
    day = datetime.now(_tz(context)).date().isoformat()
    con = botdb.connect(context.bot_data["db_path"])
    try:
        total = botdb.add_water(con, uid, day, delta)
    finally:
        con.close()
    await q.answer(f"{'+' if delta > 0 else ''}{delta} л")
    try:
        await q.edit_message_text(i18n.t("meal.water_head", lang, v=total),
                                  reply_markup=_water_kb(lang))
    except Exception:
        pass                                   # текст не изменился — не страшно


# --- просмотр дня -------------------------------------------------------------

def _day_report(con, uid: int, day: str, lang: str) -> str:
    meals = botdb.meals_for_day(con, uid, day)
    water = botdb.water_for_day(con, uid, day)
    weight = botdb.latest_weight(con, uid, day)
    if not meals and not water:
        return i18n.t("meal.view_empty", lang, day=day)
    t = nutr.day_totals(meals)
    lines = [i18n.t("meal.view_head", lang, day=day),
             i18n.t("meal.card_totals", lang, kcal=_fmt_num(t["kcal"]),
                    p=_fmt_num(t["protein_g"]), f=_fmt_num(t["fat_g"]),
                    c=_fmt_num(t["carb_g"])),
             i18n.t("meal.view_water", lang, v=water)]
    if weight and t["protein_g"]:
        lines.append(i18n.t("meal.view_ppk", lang,
                            v=round(t["protein_g"] / weight, 2)))
    if meals:
        lines.append("")
        for m in meals:
            foods = ", ".join(f"{f['name']} ~{_fmt_num(f.get('grams'))}г"
                              for f in m["foods"])
            lines.append(i18n.t("meal.view_meal", lang, time=(m["ts"] or "")[11:16],
                                kcal=_fmt_num(m["kcal"]), foods=foods))
    lines.append("")
    lines.append(i18n.t("meal.view_micro", lang,
                        fiber=_fmt_num(t["fiber_g"]), sugar=_fmt_num(t["sugar_g"]),
                        sodium=_fmt_num(t["sodium_mg"])))
    advice = nutr.day_advice(t, water, weight, lang)
    if advice:
        lines.append("")
        lines.append(i18n.t("meal.view_advice_hd", lang))
        lines.extend(f"• {a}" for a in advice)
    return "\n".join(lines)


@access.restricted
async def view_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    if _pro_only(uid):
        await update.effective_message.reply_text(i18n.t("meal.pro_only", lang))
        return ConversationHandler.END
    await update.effective_message.reply_text(
        i18n.t("meal.ask_view_date", lang), reply_markup=_date_kb("mvd", lang))
    return V_DATE


async def _view_show(msg_or_q, context, uid: int, day: str, lang: str,
                     edit: bool) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        text = _day_report(con, uid, day, lang)
    finally:
        con.close()
    if edit:
        await msg_or_q.edit_message_text(text)
    else:
        await msg_or_q.reply_text(text)
    return ConversationHandler.END


async def view_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    day = _resolve_day(q.data.split(":", 1)[1], context)
    if day is None:
        await q.edit_message_text(i18n.t("record.ask_date_input", lang))
        return V_DATE_INPUT
    return await _view_show(q, context, q.from_user.id, day, lang, edit=True)


async def view_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    d = _parse_date(update.message.text, datetime.now(_tz(context)).date())
    if d is None:
        await update.message.reply_text(i18n.t("record.date_invalid", lang))
        return V_DATE_INPUT
    return await _view_show(update.message, context, update.effective_user.id,
                            d.isoformat(), lang, edit=False)


# --- редактирование -----------------------------------------------------------

@access.restricted
async def edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    if _pro_only(uid):
        await update.effective_message.reply_text(i18n.t("meal.pro_only", lang))
        return ConversationHandler.END
    await update.effective_message.reply_text(
        i18n.t("meal.ask_edit_date", lang), reply_markup=_date_kb("med", lang))
    return E_DATE


async def _edit_list(msg_or_q, context, uid: int, day: str, lang: str,
                     edit: bool) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        meals = botdb.meals_for_day(con, uid, day)
    finally:
        con.close()
    if not meals:
        text = i18n.t("meal.view_empty", lang, day=day)
        await (msg_or_q.edit_message_text(text) if edit else msg_or_q.reply_text(text))
        return ConversationHandler.END
    context.user_data["meal_day"] = day
    rows = [[InlineKeyboardButton(
        f"{(m['ts'] or '')[11:16]} · {_fmt_num(m['kcal'])} ккал · "
        + (m["foods"][0]["name"][:25] if m["foods"] else "—"),
        callback_data=f"mem:{m['id']}")] for m in meals]
    text = i18n.t("meal.edit_pick", lang, day=day)
    kb = InlineKeyboardMarkup(rows)
    if edit:
        await msg_or_q.edit_message_text(text, reply_markup=kb)
    else:
        await msg_or_q.reply_text(text, reply_markup=kb)
    return E_PICK


async def edit_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    day = _resolve_day(q.data.split(":", 1)[1], context)
    if day is None:
        await q.edit_message_text(i18n.t("record.ask_date_input", lang))
        return E_DATE_INPUT
    return await _edit_list(q, context, q.from_user.id, day, lang, edit=True)


async def edit_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    d = _parse_date(update.message.text, datetime.now(_tz(context)).date())
    if d is None:
        await update.message.reply_text(i18n.t("record.date_invalid", lang))
        return E_DATE_INPUT
    return await _edit_list(update.message, context, update.effective_user.id,
                            d.isoformat(), lang, edit=False)


async def edit_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = _lang(context, uid)
    if q.data.startswith("mem:"):
        meal_id = int(q.data.split(":", 1)[1])
        context.user_data["meal_edit_id"] = meal_id
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(i18n.t("meal.btn_delete", lang), callback_data="mea:del"),
            InlineKeyboardButton(i18n.t("meal.btn_fix", lang), callback_data="mea:fix"),
        ]])
        await q.edit_message_text(i18n.t("meal.edit_what", lang), reply_markup=kb)
        return E_PICK
    action = q.data.split(":", 1)[1]
    meal_id = context.user_data.get("meal_edit_id")
    day = context.user_data.get("meal_day")
    if not meal_id or not day:
        await q.edit_message_text(i18n.t("meal.context_lost", lang))
        return _clear_end(context)
    if action == "del":
        con = botdb.connect(context.bot_data["db_path"])
        try:
            botdb.delete_meal(con, uid, meal_id)
        finally:
            con.close()
        await q.edit_message_text(i18n.t("meal.deleted", lang))
        return _clear_end(context)
    # fix: перепарс по сохранённому фото с текст-уточнением
    con = botdb.connect(context.bot_data["db_path"])
    try:
        meals = {m["id"]: m for m in botdb.meals_for_day(con, uid, day)}
    finally:
        con.close()
    m = meals.get(meal_id)
    if not m or not (m.get("photo_id") or m.get("note")):
        await q.edit_message_text(i18n.t("meal.fix_no_photo", lang))
        return _clear_end(context)
    context.user_data.pop("meal_photo", None)
    context.user_data.pop("meal_desc", None)
    if m.get("photo_id"):
        context.user_data["meal_photo"] = m["photo_id"]
    else:
        context.user_data["meal_desc"] = m["note"]
    context.user_data["meal_edit_ts"] = m["ts"]
    context.user_data["meal_notes"] = []
    await q.edit_message_text(i18n.t("meal.ask_correction", lang))
    return E_CORR


async def edit_correction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    text = (update.message.text or "").strip()
    if len(text) < 2:
        await update.message.reply_text(i18n.t("meal.ask_correction", lang))
        return E_CORR
    context.user_data.setdefault("meal_notes", []).append(text)
    ok = await _parse_draft(update.message, context, uid, lang, "me")
    return E_CONFIRM if ok else _clear_end(context)


async def edit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = _lang(context, uid)
    action = q.data.split(":", 1)[1]
    if action == "cancel":
        await q.edit_message_text(i18n.t("meal.cancelled", lang))
        return _clear_end(context)
    if action == "edit":
        await q.edit_message_text(i18n.t("meal.ask_correction", lang))
        return E_CORR
    draft = context.user_data.get("meal_draft")
    day = context.user_data.get("meal_day")
    meal_id = context.user_data.get("meal_edit_id")
    if not draft or not day or not meal_id:
        await q.edit_message_text(i18n.t("meal.context_lost", lang))
        return _clear_end(context)
    ts = context.user_data.get("meal_edit_ts") or _meal_ts(day, context)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.delete_meal(con, uid, meal_id)          # правка = замена приёма
        botdb.add_meal(con, uid, day, ts, draft["foods"], draft["totals"],
                       note=context.user_data.get("meal_desc"),
                       photo_id=context.user_data.get("meal_photo"),
                       engine=vision.engine_for(uid),
                       quality=draft.get("quality"), quality_note=draft.get("quality_note"))
    finally:
        con.close()
    await q.edit_message_text(
        i18n.t("meal.fixed", lang, kcal=_fmt_num(draft["totals"]["kcal"])))
    return _clear_end(context)


# --- регистрация ---------------------------------------------------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_end(context)
    from .menu import show_menu
    await show_menu(update, context, "menu.cancelled_short")
    return ConversationHandler.END


@access.restricted
async def report_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if _pro_only(uid):
        await update.effective_message.reply_text(i18n.t("meal.pro_only", _lang(context, uid)))
        return
    await menu._nutrition(update, context)


def register(app) -> None:
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.nutrition")), open_menu))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Text(menu.btn_variants("btn.meal_record")), rec_entry)],
        states={
            R_DATE: [CallbackQueryHandler(rec_date, pattern=r"^mrd:")],
            R_DATE_INPUT: [MessageHandler(not_menu_text(), rec_date_input)],
            R_PHOTO: [MessageHandler(filters.PHOTO, rec_photo),
                      MessageHandler(not_menu_text(), rec_text)],
            R_CONFIRM: [CallbackQueryHandler(rec_confirm, pattern=r"^mr:")],
            R_CORR: [MessageHandler(not_menu_text(), rec_correction)],
        },
        fallbacks=menu.wizard_fallbacks(),
        name="meal_record",
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Text(menu.btn_variants("btn.meal_edit")), edit_entry)],
        states={
            E_DATE: [CallbackQueryHandler(edit_date, pattern=r"^med:")],
            E_DATE_INPUT: [MessageHandler(not_menu_text(), edit_date_input)],
            E_PICK: [CallbackQueryHandler(edit_pick, pattern=r"^me[ma]:")],
            E_CORR: [MessageHandler(not_menu_text(), edit_correction)],
            E_CONFIRM: [CallbackQueryHandler(edit_confirm, pattern=r"^me:")],
        },
        fallbacks=menu.wizard_fallbacks(),
        name="meal_edit",
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Text(menu.btn_variants("btn.meal_view")), view_entry)],
        states={
            V_DATE: [CallbackQueryHandler(view_date, pattern=r"^mvd:")],
            V_DATE_INPUT: [MessageHandler(not_menu_text(), view_date_input)],
        },
        fallbacks=menu.wizard_fallbacks(),
        name="meal_view",
    ))
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.meal_water")), water_open))
    app.add_handler(CallbackQueryHandler(water_cb, pattern=r"^water:"))
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.meal_report")), report_open))
