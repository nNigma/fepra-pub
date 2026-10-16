"""Admin-подменю: пустить/убрать из бота (allowlist) + Pro + статистика. Только админу."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
                      Update)
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n
from tj.analysis import activity_stats

from .. import access
from .. import db as botdb
from ..access import add_user, is_admin, load_admins, load_allow, remove_user
from . import menu, pro
from .menu import show_menu

BTN_ADD_USER = "➕ Добавить в бота"
BTN_DEL_USER = "➖ Удалить из бота"
ADD = range(1)[0]
GYM_ADD = range(1)[0]
COACH_ID, COACH_GYM = range(2)
GYM_NAME_LIMIT = 25
_RESERVED_GYMS = {"other", "solo"}

_PERIOD_DAYS = {"7": 7, "30": 30}


def admin_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[i18n.t("btn.admin_add_user", lang), i18n.t("btn.admin_del_user", lang)],
         [i18n.t("btn.admin_stats", lang), i18n.t("btn.pro", lang)],
         [i18n.t("btn.admin_gyms", lang)],
         [i18n.t("btn.admin_review", lang)],
         [i18n.t("btn.back", lang)]],
        resize_keyboard=True)


def _period_since(period: str, now: datetime):
    if period in _PERIOD_DAYS:
        since = (now - timedelta(days=_PERIOD_DAYS[period])).isoformat(timespec="seconds")
        return since, f"stat.period.{period}"
    return None, "stat.period.all"


def _stats_text(con, period: str, now: datetime, lang: str) -> str:
    since, period_key = _period_since(period, now)
    counts = botdb.action_counts(con, since)
    rows = con.execute('SELECT "tg_id","nick" FROM users').fetchall()
    nick_by_id = {int(r["tg_id"]): r["nick"] for r in rows if r["nick"]}
    return activity_stats.render(counts, nick_by_id, i18n.t(period_key, lang), lang)


def _stats_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("stat.period.7", lang), callback_data="stats:7"),
        InlineKeyboardButton(i18n.t("stat.period.30", lang), callback_data="stats:30"),
        InlineKeyboardButton(i18n.t("stat.period.all", lang), callback_data="stats:all"),
    ]])


async def stats_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    lang = await _lang_for(context, uid)
    if not is_admin(uid):
        await update.effective_message.reply_text(i18n.t("admin.only_admin", lang))
        return
    con = botdb.connect(context.bot_data["db_path"])
    try:
        text = _stats_text(con, "30", datetime.now(timezone.utc), lang)
    finally:
        con.close()
    await update.effective_message.reply_text(text, reply_markup=_stats_kb(lang))


async def stats_switch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    lang = await _lang_for(context, q.from_user.id)
    if not is_admin(q.from_user.id):
        await q.answer(i18n.t("admin.only_admin", lang), show_alert=True)
        return
    period = q.data.split(":", 1)[1]
    con = botdb.connect(context.bot_data["db_path"])
    try:
        text = _stats_text(con, period, datetime.now(timezone.utc), lang)
    finally:
        con.close()
    await q.answer()
    await q.edit_message_text(text, reply_markup=_stats_kb(lang))


def _removable(allowed, admins, nick_by_id) -> list:
    out = []
    for uid in sorted(allowed - admins):
        nick = nick_by_id.get(uid)
        out.append((f"{nick} ({uid})" if nick else str(uid), uid))
    return out


async def _lang_for(context: ContextTypes.DEFAULT_TYPE, uid: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, uid)
    finally:
        con.close()


async def open_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    lang = await _lang_for(context, uid)
    if not is_admin(uid):
        await update.effective_message.reply_text(i18n.t("admin.only_admin", lang))
        return
    await update.effective_message.reply_text(i18n.t("admin.section_intro", lang), reply_markup=admin_kb(lang))


async def back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_menu(update, context)


async def add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = await _lang_for(context, uid)
    context.user_data["lang"] = lang
    if not is_admin(uid):
        await update.effective_message.reply_text(i18n.t("admin.only_admin", lang))
        return ConversationHandler.END
    await update.effective_message.reply_text(i18n.t("admin.ask_tg_id", lang))
    return ADD


async def add_take(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ru")
    txt = (update.effective_message.text or "").strip()
    if not txt.isdigit():
        await update.effective_message.reply_text(i18n.t("admin.need_number", lang))
        return ADD
    add_user(int(txt))
    await update.effective_message.reply_text(
        i18n.t("admin.user_added", lang, tg_id=txt), reply_markup=admin_kb(lang))
    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    lang = await _lang_for(context, uid)
    await update.effective_message.reply_text(i18n.t("admin.cancelled", lang), reply_markup=admin_kb(lang))
    return ConversationHandler.END


def _nicks(context) -> dict:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        rows = con.execute('SELECT tg_id, nick FROM users').fetchall()
    finally:
        con.close()
    return {int(r["tg_id"]): r["nick"] for r in rows if r["nick"]}


async def del_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    lang = await _lang_for(context, uid)
    if not is_admin(uid):
        await update.effective_message.reply_text(i18n.t("admin.only_admin", lang))
        return
    items = _removable(load_allow(), load_admins(), _nicks(context))
    if not items:
        await update.effective_message.reply_text(
            i18n.t("admin.nobody_to_remove", lang), reply_markup=admin_kb(lang))
        return
    rows = [[InlineKeyboardButton(i18n.t("admin.remove_label", lang, label=label), callback_data=f"delu:{uid}")]
            for label, uid in items]
    await update.effective_message.reply_text(
        i18n.t("admin.pick_to_remove", lang), reply_markup=InlineKeyboardMarkup(rows))


async def del_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    lang = await _lang_for(context, q.from_user.id)
    if not is_admin(q.from_user.id):
        await q.answer(i18n.t("admin.only_admin", lang), show_alert=True)
        return
    uid = int(q.data.split(":", 1)[1])
    if uid in load_admins():
        await q.answer(i18n.t("admin.cannot_remove_admin", lang), show_alert=True)
        return
    remove_user(uid)
    await q.answer(i18n.t("admin.removed_alert", lang))
    await q.edit_message_text(i18n.t("admin.user_removed", lang, tg_id=uid))


def _gyms_text(con, lang: str) -> str:
    counts = {r["gym"]: r["n"] for r in con.execute(
        'SELECT "gym", COUNT(*) AS n FROM users GROUP BY "gym"')}
    lines = [i18n.t("admin.gyms_header", lang)]
    for g in botdb.list_gyms(con):
        lines.append(i18n.t("admin.gym_line", lang, name=g["name"], n=counts.get(g["name"], 0)))
    return "\n".join(lines)


def _gym_name_error(con, name: str) -> str | None:
    if not name or "\n" in name:
        return "admin.gym_name_invalid"
    if len(name) > GYM_NAME_LIMIT or len(f"gym:{name}".encode()) > 64:
        return "admin.gym_name_too_long"
    if name.casefold() in _RESERVED_GYMS:
        return "admin.gym_name_reserved"
    if botdb.gym_exists(con, name):
        return "admin.gym_exists"
    return None


async def gyms_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    lang = await _lang_for(context, uid)
    if not is_admin(uid):
        await update.effective_message.reply_text(i18n.t("admin.only_admin", lang))
        return
    con = botdb.connect(context.bot_data["db_path"])
    try:
        text = _gyms_text(con, lang)
    finally:
        con.close()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(i18n.t("admin.gym_add_btn", lang), callback_data="gymadd")],
        [InlineKeyboardButton(i18n.t("admin.gym_coaches_btn", lang), callback_data="coaches")],
    ])
    await update.effective_message.reply_text(text, reply_markup=kb)


async def gym_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = await _lang_for(context, q.from_user.id)
    if not is_admin(q.from_user.id):
        await q.answer(i18n.t("admin.only_admin", lang), show_alert=True)
        return ConversationHandler.END
    context.user_data["lang"] = lang
    await q.answer()
    await update.effective_message.reply_text(i18n.t("admin.ask_gym_name", lang))
    return GYM_ADD


async def gym_add_take(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ru")
    name = (update.effective_message.text or "").strip()
    con = botdb.connect(context.bot_data["db_path"])
    try:
        err = _gym_name_error(con, name)
        if err:
            await update.effective_message.reply_text(i18n.t(err, lang, limit=GYM_NAME_LIMIT))
            return GYM_ADD
        botdb.add_gym(con, name)
    finally:
        con.close()
    await update.effective_message.reply_text(
        i18n.t("admin.gym_added", lang, name=name), reply_markup=admin_kb(lang))
    return ConversationHandler.END


def _coach_label(nick_by_id: dict, tg_id: int) -> str:
    nick = nick_by_id.get(tg_id)
    return f"{nick} ({tg_id})" if nick else str(tg_id)


def _coaches_text(con, lang: str) -> str:
    coaches = access.load_coaches()
    if not coaches:
        return i18n.t("admin.coaches_empty", lang)
    rows = con.execute('SELECT "tg_id","nick" FROM users').fetchall()
    nick_by_id = {int(r["tg_id"]): r["nick"] for r in rows if r["nick"]}
    lines = [i18n.t("admin.coach_line", lang, label=_coach_label(nick_by_id, tg_id), gym=gym)
             for tg_id, gym in sorted(coaches.items())]
    return i18n.t("admin.coaches_header", lang, lines="\n".join(lines))


async def coaches_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    lang = await _lang_for(context, q.from_user.id)
    if not is_admin(q.from_user.id):
        await q.answer(i18n.t("admin.only_admin", lang), show_alert=True)
        return
    await q.answer()
    con = botdb.connect(context.bot_data["db_path"])
    try:
        text = _coaches_text(con, lang)
        rows = con.execute('SELECT "tg_id","nick" FROM users').fetchall()
    finally:
        con.close()
    nick_by_id = {int(r["tg_id"]): r["nick"] for r in rows if r["nick"]}
    kb = [[InlineKeyboardButton(i18n.t("admin.coach_grant_btn", lang), callback_data="coach:add")]]
    for tg_id in sorted(access.load_coaches()):
        kb.append([InlineKeyboardButton(
            i18n.t("admin.coach_revoke_btn", lang, label=_coach_label(nick_by_id, tg_id)),
            callback_data=f"coachrm:{tg_id}")])
    await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def coach_rm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    lang = await _lang_for(context, q.from_user.id)
    if not is_admin(q.from_user.id):
        await q.answer(i18n.t("admin.only_admin", lang), show_alert=True)
        return
    access.remove_coach(int(q.data.split(":", 1)[1]))
    await q.answer()
    await q.edit_message_text(i18n.t("admin.coach_revoked", lang))


async def coach_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = await _lang_for(context, q.from_user.id)
    if not is_admin(q.from_user.id):
        await q.answer(i18n.t("admin.only_admin", lang), show_alert=True)
        return ConversationHandler.END
    context.user_data["lang"] = lang
    await q.answer()
    await update.effective_message.reply_text(i18n.t("admin.coach_ask_id", lang))
    return COACH_ID


async def coach_add_take(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ru")
    txt = (update.effective_message.text or "").strip()
    if not txt.isdigit():
        await update.effective_message.reply_text(i18n.t("admin.need_number", lang))
        return COACH_ID
    context.user_data["coach_id"] = int(txt)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        gyms = botdb.list_gyms(con)
    finally:
        con.close()
    kb = [[InlineKeyboardButton(g["name"], callback_data=f"cg:{g['name']}")] for g in gyms]
    await update.effective_message.reply_text(
        i18n.t("admin.coach_pick_gym", lang), reply_markup=InlineKeyboardMarkup(kb))
    return COACH_GYM


async def coach_pick_gym(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    lang = context.user_data.get("lang", "ru")
    gym = q.data.split(":", 1)[1]
    tg_id = context.user_data.pop("coach_id", None)
    if tg_id is None:
        await q.answer()
        return ConversationHandler.END
    access.add_coach(tg_id, gym)
    await q.answer()
    await q.edit_message_text(i18n.t("admin.coach_granted", lang, tg_id=tg_id, gym=gym))
    return ConversationHandler.END


def _review_report(res: list[dict], lang: str) -> str:
    lines = [i18n.t("admin.review_done", lang)]
    for u in res:
        if "error" in u and "tg_id" not in u:
            return i18n.t("admin.review_failed", lang, err=u["error"])
        days = u.get("days") or []
        ok = sum(1 for d in days if d.get("ok"))
        skipped = sum(1 for d in days if d.get("skip"))
        errors = sum(1 for d in days if d.get("error")) + (1 if u.get("error") else 0)
        summary = "✅" if u.get("summary") else "—"
        lines.append(i18n.t("admin.review_user_line", lang, tg_id=u.get("tg_id"),
                            ok=ok, skipped=skipped, errors=errors, summary=summary))
    return "\n".join(lines)


async def review_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«Разбор полётов»: принудительный прогон авторазборов по всем Pro, в фоне.
    Текстовые вызовы — через llm.text_complete (agent/claude → Gemini)."""
    import asyncio

    from tj import llm

    from .. import claude_review

    uid = update.effective_user.id
    lang = await _lang_for(context, uid)
    if not is_admin(uid):
        await update.effective_message.reply_text(i18n.t("admin.only_admin", lang))
        return
    if not llm.has_text_llm():
        await update.effective_message.reply_text(i18n.t("admin.review_no_llm", lang))
        return
    if context.bot_data.get("review_running"):
        await update.effective_message.reply_text(i18n.t("admin.review_busy", lang))
        return
    context.bot_data["review_running"] = True
    await update.effective_message.reply_text(i18n.t("admin.review_started", lang))
    db_path = context.bot_data["db_path"]
    chat_id = update.effective_chat.id

    async def _bg():
        try:
            res = await asyncio.to_thread(claude_review.run_all, db_path)
            text = _review_report(res, lang)
        except Exception as e:
            text = i18n.t("admin.review_failed", lang, err=type(e).__name__)
        finally:
            context.bot_data["review_running"] = False
        await context.bot.send_message(chat_id, text)

    context.application.create_task(_bg())


def _add_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Text(menu.btn_variants("btn.admin_add_user")), add_entry)],
        states={ADD: [MessageHandler(menu.not_menu_text(), add_take)]},
        fallbacks=menu.wizard_fallbacks(),
    )


def _gym_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(gym_add_entry, pattern=r"^gymadd$")],
        states={GYM_ADD: [MessageHandler(menu.not_menu_text(), gym_add_take)]},
        fallbacks=menu.wizard_fallbacks(),
    )


def _coach_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(coach_add_entry, pattern=r"^coach:add$")],
        states={
            COACH_ID: [MessageHandler(menu.not_menu_text(), coach_add_take)],
            COACH_GYM: [CallbackQueryHandler(coach_pick_gym, pattern=r"^cg:")],
        },
        fallbacks=menu.wizard_fallbacks(),
    )


def register(app) -> None:
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.admin")), open_admin))
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.back")), back))
    app.add_handler(_add_conv())
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.admin_gyms")), gyms_open))
    app.add_handler(_gym_conv())
    app.add_handler(CallbackQueryHandler(coaches_open, pattern=r"^coaches$"))
    app.add_handler(_coach_conv())
    app.add_handler(CallbackQueryHandler(coach_rm, pattern=r"^coachrm:"))
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.admin_del_user")), del_list))
    app.add_handler(CallbackQueryHandler(del_do, pattern=r"^delu:"))
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.admin_stats")), stats_open))
    app.add_handler(CallbackQueryHandler(stats_switch, pattern=r"^stats:(7|30|all)$"))
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.admin_review")), review_run))
