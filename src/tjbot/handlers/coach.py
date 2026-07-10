"""Раздел «Тренер» (только Pro): вопрос ИИ-тренеру с полным контекстом атлета
(профиль, питание, сводка, тренировки) + последние обращения.
Движок — Claude CLI с фолбэком на Gemini (tj.analysis.coach), не-админ под
дневной квотой ИИ. Ответы хранятся в coach_qa."""
from __future__ import annotations

import asyncio
from datetime import datetime

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters

from tj import i18n
from tj.analysis import coach as engine
from .. import access
from .. import db as botdb
from . import menu
from .menu import not_menu_text
from .record_workout import _tz

C_Q = 0

_ANSWER_CAP = 4000          # лимит текста сообщения Telegram 4096
COACH_DAILY_LIMIT = 3       # вопросов/день для не-админа


def _lang(context, uid: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


def _pro_only(uid: int) -> bool:
    return not (access.is_admin(uid) or access.is_pro(uid))


def coach_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[i18n.t("btn.coach_ask", lang)],
         [i18n.t("btn.coach_recent", lang)],
         [i18n.t("btn.back", lang)]],
        resize_keyboard=True)


@access.restricted
async def open_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    if _pro_only(uid):
        await update.effective_message.reply_text(i18n.t("coach.pro_only", lang))
        return
    await update.effective_message.reply_text(
        i18n.t("coach.intro", lang), reply_markup=coach_kb(lang))


@access.restricted
async def ask_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    if _pro_only(uid):
        await update.effective_message.reply_text(i18n.t("coach.pro_only", lang))
        return ConversationHandler.END
    await update.effective_message.reply_text(i18n.t("coach.ask_q", lang))
    return C_Q


async def question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    q = (update.message.text or "").strip()
    if not q:
        return C_Q
    if not access.is_admin(uid):
        day = datetime.now(_tz(context)).date().isoformat()
        con = botdb.connect(context.bot_data["db_path"])
        try:
            used_today = botdb.coach_count_today(con, uid, day)
        finally:
            con.close()
        if used_today >= COACH_DAILY_LIMIT:
            await update.message.reply_text(
                i18n.t("coach.day_limit", lang, limit=COACH_DAILY_LIMIT))
            return ConversationHandler.END
        if not access.llm_quota_consume(uid):
            await update.message.reply_text(
                i18n.t("coach.llm_limit", lang, limit=access.LLM_DAILY_LIMIT))
            return ConversationHandler.END
    await update.message.reply_text(i18n.t("coach.thinking", lang))
    try:
        answer, used = await asyncio.to_thread(
            engine.ask, context.bot_data["db_path"], uid, q, lang)
    except Exception:
        answer, used = None, None
    if not answer:
        await update.message.reply_text(i18n.t("coach.fail", lang))
        return ConversationHandler.END
    ts = datetime.now(_tz(context)).isoformat(timespec="seconds")
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.add_coach_qa(con, uid, ts, q, answer, lang, used)
    finally:
        con.close()
    await update.message.reply_text(answer[:_ANSWER_CAP])
    return ConversationHandler.END


@access.restricted
async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    lang = _lang(context, uid)
    if _pro_only(uid):
        await update.effective_message.reply_text(i18n.t("coach.pro_only", lang))
        return
    con = botdb.connect(context.bot_data["db_path"])
    try:
        rows = botdb.coach_recent(con, uid, limit=5)
    finally:
        con.close()
    if not rows:
        await update.effective_message.reply_text(i18n.t("coach.recent_empty", lang))
        return
    parts = []
    for r in rows:
        a = r["answer"] or ""
        if len(a) > 500:
            a = a[:500] + "…"
        parts.append(f"🗓 {r['ts'][:10]}\n❓ {r['question']}\n💬 {a}")
    await update.effective_message.reply_text("\n\n———\n\n".join(parts)[:_ANSWER_CAP])


def register(app) -> None:
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.coach")), open_menu))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Text(menu.btn_variants("btn.coach_ask")), ask_entry)],
        states={C_Q: [MessageHandler(not_menu_text(), question)]},
        fallbacks=menu.wizard_fallbacks(),
        name="coach_ask",
    ))
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.coach_recent")), recent))
