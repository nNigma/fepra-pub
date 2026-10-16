"""Уточнение варианта неоднозначных максов (рывок в сед/в стойку, взятие с пола/с виса).
Однозначные лифты пишут сами хендлеры как раньше; сюда приходят только неоднозначные
(общий рывок/взятие). ask_ambiguous() спрашивает вариант инлайн-кнопкой, on_pick
(глобальный колбэк ^ldis:) дописывает выбранную дисциплину в цели (append, source=auto)."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from tj import i18n
from tj.analysis import standards
from tj.analysis.progression import epley_1rm
from .. import db as botdb

# family -> [(discipline_id, i18n_label_key)] — общий словарь с сервисами (tj.services.workouts)
from tj.services.workouts import FAMILY_VARIANTS  # noqa: E402
_ASK_KEY = {"snatch": "disambig.ask_snatch", "clean": "disambig.ask_clean"}


def _lang(context, uid):
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


async def _ask_next(update: Update, context) -> None:
    amb = context.user_data.get("ld_amb")
    if not amb or not amb["queue"]:
        context.user_data.pop("ld_amb", None)
        return
    item = amb["queue"][0]
    fam = item["family"]
    lang = _lang(context, amb["tg_id"])
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.t(k, lang), callback_data=f"ldis:{did}")
                                for did, k in FAMILY_VARIANTS[fam]]])
    await update.effective_message.reply_text(
        i18n.t(_ASK_KEY[fam], lang, w=int(item["weight"])), reply_markup=kb)


async def ask_ambiguous(update: Update, context, ambiguous, day, activity_id, tg_id) -> bool:
    """Есть неоднозначные -> спросить вариант первого (True). Нет -> ничего (False)."""
    if not ambiguous:
        return False
    context.user_data["ld_amb"] = {"queue": list(ambiguous), "day": day,
                                   "activity_id": activity_id, "tg_id": tg_id}
    await _ask_next(update, context)
    return True


async def on_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    did = q.data.split(":", 1)[1]
    amb = context.user_data.get("ld_amb")
    if not amb or not amb["queue"]:
        return
    item = amb["queue"].pop(0)
    name = standards.disciplines().get(did, {}).get("name_ru", did)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.add_result(con, tg_id=amb["tg_id"], discipline=did, value=item["weight"],
                         reps=item["reps"], est_1rm=epley_1rm(item["weight"], item["reps"]),
                         source="auto", day=amb["day"], activity_id=amb["activity_id"])
        con.commit()
    finally:
        con.close()
    lang = _lang(context, amb["tg_id"])
    await q.edit_message_text(i18n.t("disambig.saved", lang, name=name, w=int(item["weight"])))
    await _ask_next(update, context)


def handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(on_pick, pattern=r"^ldis:")
