"""Мастер «➕ Результат»: вид -> дисциплина -> значение -> запись макса (source=manual)."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n
from tj.analysis import standards
from tj.analysis.levels import tier
from tj.analysis.progression import epley_1rm
from .. import db as botdb
from ..access import restricted
from . import menu
from .menu import show_menu

KIND, DISC, VALUE = range(3)
BTN_RESULT = "➕ Результат"


def parse_lift(txt: str):
    s = txt.strip().lower().replace("кг", "").strip()
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*[xхXХ×* ]\s*(\d+)$", s)
    if m:
        load = float(m.group(1).replace(",", "."))
        reps = int(m.group(2))
        return (load, reps) if load > 0 and reps >= 1 else None
    m = re.match(r"^(\d+(?:[.,]\d+)?)$", s)
    if m:
        load = float(m.group(1).replace(",", "."))
        return (load, 1) if load > 0 else None
    return None


def parse_benchmark(txt: str, unit: str):
    s = txt.strip().lower()
    if unit == "rounds":
        m = re.match(r"^(\d+)", s)
        return float(m.group(1)) if m else None
    if ":" in s:
        m = re.match(r"^(\d+):(\d{1,2})$", s)
        if not m:
            return None
        mm, ss = int(m.group(1)), int(m.group(2))
        if ss >= 60:
            return None
        return float(mm * 60 + ss)
    m = re.match(r"^(\d+)$", s)
    return float(m.group(1)) if m else None


def _tz(context):
    return ZoneInfo(context.bot_data.get("tz", "UTC"))


@restricted
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("recresult.btn_lift", lang), callback_data="k:lift"),
        InlineKeyboardButton(i18n.t("recresult.btn_benchmark", lang), callback_data="k:benchmark"),
    ]])
    await update.effective_message.reply_text(i18n.t("recresult.ask_kind", lang), reply_markup=kb)
    return KIND


async def pick_kind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    kind = q.data.split(":", 1)[1]
    context.user_data["kind"] = kind
    discs = [d for d in standards.disciplines().values() if d["kind"] == kind]
    rows = [[InlineKeyboardButton(standards.discipline_name(d, lang), callback_data=f"x:{d['id']}")]
            for d in sorted(discs, key=lambda m: m["order"])]
    await q.edit_message_text(i18n.t("recresult.ask_discipline", lang), reply_markup=InlineKeyboardMarkup(rows))
    return DISC


async def pick_disc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, update.effective_user.id)
    con.close()
    did = q.data.split(":", 1)[1]
    context.user_data["disc"] = did
    meta = standards.disciplines()[did]
    if meta["kind"] == "lift":
        hint = i18n.t("recresult.hint_lift", lang)
    elif meta["unit"] == "rounds":
        hint = i18n.t("recresult.hint_rounds", lang)
    else:
        hint = i18n.t("recresult.hint_time", lang)
    await q.edit_message_text(i18n.t("recresult.discipline_hint", lang,
                                      name=standards.discipline_name(meta, lang), hint=hint))
    return VALUE


async def take_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    did = context.user_data["disc"]
    meta = standards.disciplines()[did]
    txt = update.effective_message.text
    day = datetime.now(_tz(context)).date().isoformat()
    tg_id = update.effective_user.id

    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, tg_id)
        u = dict(botdb.get_user(con, tg_id) or {})
        sex = u.get("sex") or "m"
        bw = u.get("weight_kg")
        if meta["kind"] == "lift":
            parsed = parse_lift(txt)
            if not parsed:
                await update.effective_message.reply_text(i18n.t("recresult.lift_invalid", lang))
                return VALUE
            load, reps = parsed
            est = epley_1rm(load, reps)
            botdb.add_result(con, tg_id=tg_id, discipline=did, value=load, reps=reps,
                             est_1rm=est, source="manual", day=day)
            best = botdb.best_results(con, tg_id)
            t = tier(did, best[did]["value"], sex, bw, lang=lang) if did in best else None
            msg = i18n.t("recresult.logged_lift", lang, name=standards.discipline_name(meta, lang), est=est)
        else:
            val = parse_benchmark(txt, meta["unit"])
            if val is None:
                await update.effective_message.reply_text(i18n.t("recresult.benchmark_invalid", lang))
                return VALUE
            botdb.add_result(con, tg_id=tg_id, discipline=did, value=val,
                             source="manual", day=day)
            best = botdb.best_results(con, tg_id)
            t = tier(did, best[did]["value"], sex, bw, lang=lang) if did in best else None
            msg = i18n.t("recresult.logged_benchmark", lang, name=standards.discipline_name(meta, lang))
        if t:
            msg += i18n.t("recresult.level_suffix", lang, level=t["level"])
            if t["distance"] is not None:
                unit = (i18n.t("recresult.unit_kg", lang) if meta["unit"] == "kg"
                        else (i18n.t("recresult.unit_sec", lang) if meta["unit"] == "time"
                              else i18n.t("recresult.unit_rounds", lang)))
                msg += i18n.t("recresult.distance_suffix", lang, distance=t["distance"], unit=unit)
    finally:
        con.close()

    await update.effective_message.reply_text(msg)
    await show_menu(update, context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await show_menu(update, context, "menu.cancelled_short")
    return ConversationHandler.END


def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text(menu.btn_variants("btn.result")), entry),
            CallbackQueryHandler(pick_kind, pattern=r"^k:"),
            CallbackQueryHandler(pick_disc, pattern=r"^x:"),
        ],
        states={
            KIND: [CallbackQueryHandler(pick_kind, pattern=r"^k:")],
            DISC: [CallbackQueryHandler(pick_disc, pattern=r"^x:")],
            VALUE: [MessageHandler(menu.not_menu_text(), take_value)],
        },
        fallbacks=menu.wizard_fallbacks(cancel=cancel),
    )
