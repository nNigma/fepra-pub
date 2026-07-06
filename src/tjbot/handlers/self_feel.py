"""Кнопка «Самочувствие»: инлайн-шкала 1-10 -> daily.extra.self_feel за сегодня."""
from __future__ import annotations

from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from tj import i18n
from .. import db as botdb
from ..access import restricted

BTN_FEEL = "🩺 Самочувствие"


def _kb() -> InlineKeyboardMarkup:
    row1 = [InlineKeyboardButton(str(n), callback_data=f"feel:{n}") for n in range(1, 6)]
    row2 = [InlineKeyboardButton(str(n), callback_data=f"feel:{n}") for n in range(6, 11)]
    return InlineKeyboardMarkup([row1, row2])


def _parse_score(data: str):
    try:
        n = int((data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        return None
    return n if 1 <= n <= 10 else None


async def _lang_for(context: ContextTypes.DEFAULT_TYPE, uid: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


@restricted
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = await _lang_for(context, update.effective_user.id)
    await update.effective_message.reply_text(i18n.t("self_feel.ask", lang), reply_markup=_kb())


@restricted
async def got(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    score = _parse_score(update.callback_query.data)
    if score is None:
        return
    lang = await _lang_for(context, update.effective_user.id)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.set_self_feel(con, date.today().isoformat(), score, update.effective_user.id)
    finally:
        con.close()
    await update.effective_message.reply_text(i18n.t("self_feel.recorded", lang, score=score))


def register(app) -> None:
    from . import menu
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.feel")), ask))
    app.add_handler(CallbackQueryHandler(got, pattern=r"^feel:\d+$"))
