"""Admin-подменю: пустить/убрать из бота (allowlist) + Pro + статистика. Только админу."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
                      Update)
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n
from tj.analysis import activity_stats

from .. import db as botdb
from ..access import add_user, is_admin, load_admins, load_allow, remove_user
from . import menu, pro
from .menu import show_menu

BTN_ADD_USER = "➕ Добавить в бота"
BTN_DEL_USER = "➖ Удалить из бота"
ADD = range(1)[0]

_PERIOD_DAYS = {"7": 7, "30": 30}


def admin_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[i18n.t("btn.admin_add_user", lang), i18n.t("btn.admin_del_user", lang)],
         [i18n.t("btn.admin_stats", lang), i18n.t("btn.pro", lang)],
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
    claude-вызовы сериализуются общим файловым локом (не столкнётся с кроном)."""
    import asyncio

    from tj import llm

    from .. import claude_review

    uid = update.effective_user.id
    lang = await _lang_for(context, uid)
    if not is_admin(uid):
        await update.effective_message.reply_text(i18n.t("admin.only_admin", lang))
        return
    if not llm.has_llm():
        await update.effective_message.reply_text(i18n.t("admin.review_no_claude", lang))
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


def register(app) -> None:
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.admin")), open_admin))
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.back")), back))
    app.add_handler(_add_conv())
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.admin_del_user")), del_list))
    app.add_handler(CallbackQueryHandler(del_do, pattern=r"^delu:"))
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.admin_stats")), stats_open))
    app.add_handler(CallbackQueryHandler(stats_switch, pattern=r"^stats:(7|30|all)$"))
    app.add_handler(MessageHandler(filters.Text(menu.btn_variants("btn.admin_review")), review_run))
