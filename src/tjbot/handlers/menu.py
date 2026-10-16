"""Главное меню (нижняя клавиатура) + заглушки для пунктов следующих этапов.

Отчётные пункты (Тренировки/Сводка/Соревнования/Цели) откроются в Mini App (M2+).
Питание и подключение часов — отдельные этапы (M7).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
                      Update, WebAppInfo)
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n

from ..access import is_admin, restricted
from .self_feel import BTN_FEEL

BTN_RECORD = "Записать тренировку"
BTN_EDIT = "✏️ Редактировать тренировку"
BTN_COMP = "➕ Соревнование"
BTN_ADMIN = "👑 Admin"
BTN_BACK = "← Назад"
BTN_ANALYTICS = "📊 Аналитика"
BTN_CLUB_SECTION = "Программа зала"
BTN_COMP_SECTION = "Соревнования"
BTN_ADD_RESULT = "Добавить результат"
BTN_ADD_WORKOUT = "Добавить тренировку"
BTN_ENTER_PM = "✍️ Ввести ПМ"
BTN_COMP_SUMMARY = "Старты"
BTN_LEADERBOARD = "🏆 Лидерборд"
BTN_LANG_RU = "🇷🇺 Русский"
BTN_LANG_EN = "🇬🇧 English"

# Все тексты кнопок-меню (главное меню + под-меню зала/админа). Нужны, чтобы любой
# мастер (ConversationHandler) отпускал юзера: нажатие кнопки меню = выход из мастера.
MENU_BUTTONS = frozenset({
    BTN_RECORD, BTN_EDIT, BTN_COMP, BTN_ADMIN, BTN_BACK,
    "Программа зала", "Тренировки", "Сводка", "Соревнования", "Цели", "Питание", "Профиль",
    "📅 На дату", "📊 Стата зала", "➕ Добавить",           # под-меню «Программа зала»
    "➕ Добавить в бота", "➖ Удалить из бота", "Pro", "📊 Статистика",  # под-меню «Admin»
    BTN_ANALYTICS, BTN_ADD_RESULT, BTN_ADD_WORKOUT, BTN_COMP_SUMMARY, BTN_LEADERBOARD,
    "✏️ Редактировать программу", "📝 Наполнить соревнование", "🎯 Цель",
    "Сегодня", "Вчера", "Другая дата", BTN_FEEL,
    BTN_LANG_RU, BTN_LANG_EN,                               # под-меню «Выбор языка»
})

_MENU_KEYS = [
    "btn.analytics", "btn.record", "btn.back", "btn.lang",
    "btn.club_section", "btn.comp_section", "btn.nutrition", "btn.profile",
    "btn.admin", "btn.edit", "btn.comp", "btn.add_result", "btn.add_workout",
    "btn.comp_summary", "btn.leaderboard", "btn.enter_pm", "btn.comp_fill",
    "btn.svodka", "btn.trenirovki", "btn.tseli", "btn.goal_single", "btn.feel",
    "btn.coach",
    "btn.club_date", "btn.club_add", "btn.club_edit", "btn.club_stats",
    "btn.club_athletes",
    "btn.admin_add_user", "btn.admin_del_user", "btn.pro", "btn.admin_stats",
    "btn.meal_record", "btn.meal_water", "btn.meal_edit",   # под-меню «Питание»
    "btn.meal_view", "btn.meal_report",
]


def btn_variants(key: str) -> set[str]:
    e = i18n.STRINGS.get(key, {})
    return {v for v in (e.get("ru"), e.get("en")) if v}


def all_menu_variants() -> set[str]:
    out: set[str] = set()
    for k in _MENU_KEYS:
        out |= btn_variants(k)
    return out


def not_menu_text():
    """Фильтр свободного текста внутри мастера: любой текст, кроме команд и кнопок меню.
    Благодаря нему нажатие кнопки меню не считается ответом на шаг мастера."""
    return filters.TEXT & ~filters.COMMAND & ~filters.Text(list(all_menu_variants() | set(MENU_BUTTONS)))


async def cancel_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Общий выход из любого мастера: чистим состояние и возвращаем главное меню."""
    context.user_data.clear()
    await show_menu(update, context, "menu.cancelled")
    return ConversationHandler.END


def wizard_fallbacks(*extra, cancel=None):
    """Стандартные точки выхода для ConversationHandler: /cancel, /start и любая кнопка меню.
    `extra` — дополнительные fallback-хендлеры конкретного мастера.
    `cancel` — своя функция отмены (со своей очисткой/сообщением); по умолчанию cancel_wizard."""
    cb = cancel or cancel_wizard
    return [
        CommandHandler("cancel", cb),
        CommandHandler("start", cb),
        MessageHandler(filters.Text(list(all_menu_variants() | set(MENU_BUTTONS))), cb),
        *extra,
    ]


@restricted
async def open_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open_app(update, context, "summary", "app.open_analytics_btn", "menu.analytics_intro")


def record_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[i18n.t("btn.enter_pm", lang)],
         [i18n.t("btn.add_result", lang)], [i18n.t("btn.add_workout", lang)],
         [i18n.t("btn.edit", lang)], [i18n.t("btn.back", lang)]],
        resize_keyboard=True)


@restricted
async def open_record(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    uid = update.effective_user.id if update.effective_user else 0
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid)
    con.close()
    await update.effective_message.reply_text(
        i18n.t("menu.record_intro", lang), reply_markup=record_kb(lang))


def main_kb(tg_id: int, lang: str) -> ReplyKeyboardMarkup:
    rows = [[i18n.t("btn.analytics", lang), i18n.t("btn.record", lang)],
            [i18n.t("btn.nutrition", lang), i18n.t("btn.club_section", lang)],
            [i18n.t("btn.coach", lang), i18n.t("btn.goal_single", lang)],
            [i18n.t("btn.comp_section", lang), i18n.t("btn.feel", lang)],
            [i18n.t("btn.profile", lang), i18n.t("btn.lang", lang)]]
    if is_admin(tg_id):
        rows.append([i18n.t("btn.admin", lang)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def miniapp_url() -> str | None:
    """URL Mini App из runtime-файла (его пишет запуск тоннеля) или из env.
    Читаем на лету — смена URL тоннеля не требует перезапуска бота."""
    f = Path(__file__).resolve().parents[3] / "miniapp_url.txt"
    if f.exists() and (u := f.read_text(encoding="utf-8").strip()):
        return u
    return os.environ.get("MINIAPP_URL")


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     text_key: str = "menu.title", **kwargs) -> None:
    from .. import db as botdb
    uid = update.effective_user.id if update.effective_user else 0
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid)
    con.close()
    await update.effective_message.reply_text(
        i18n.t(text_key, lang, **kwargs), reply_markup=main_kb(uid, lang))


@restricted
async def _dev_stub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    uid = update.effective_user.id if update.effective_user else 0
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid)
    con.close()
    await update.effective_message.reply_text(i18n.t("menu.in_dev", lang))


def lang_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[BTN_LANG_RU, BTN_LANG_EN], [i18n.t("btn.back", lang)]],
        resize_keyboard=True)


@restricted
async def _open_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid); con.close()
    await update.effective_message.reply_text(
        i18n.t("lang.choose", lang), reply_markup=lang_kb(lang))


@restricted
async def _pick_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    uid = update.effective_user.id
    new = "ru" if update.effective_message.text == BTN_LANG_RU else "en"
    con = botdb.connect(context.bot_data["db_path"])
    botdb.set_lang(con, uid, new); con.close()
    await update.effective_message.reply_text(
        i18n.t("menu.lang_switched", new), reply_markup=main_kb(uid, new))


def disconnect_garmin(con, tg_id) -> None:
    import shutil
    from .. import db as botdb
    ts = botdb.garmin_tokenstore(tg_id)
    if ts.exists():
        shutil.rmtree(ts, ignore_errors=True)
    botdb.garmin_account_delete(con, tg_id)


@restricted
async def _profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    from ..garmin_sync import last_watch_date

    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    u = botdb.get_user(con, uid)
    last = last_watch_date(con, uid)
    acc = botdb.garmin_account_get(con, uid)
    sam = botdb.watch_account_get(con, uid, "samsung")
    wh = botdb.watch_account_get(con, uid, "whoop")
    ap = botdb.watch_account_get(con, uid, "apple")
    lang = botdb.user_lang(con, uid)
    astro = botdb.user_astro(con, uid)
    goal = botdb.user_goal(con, uid)
    city = botdb.user_city(con, uid)
    con.close()
    if not u:
        await update.effective_message.reply_text(i18n.t("profile.not_filled", lang))
        return
    text = i18n.t("profile.card", lang, nick=u["nick"], height=u["height_cm"],
                   weight=u["weight_kg"], sex=u["sex"], age=u["age"], gym=u["gym"],
                   last=last or "—")
    sam_connected = bool(sam and sam["status"] == "connected")
    whoop_connected = bool(wh and wh["status"] == "connected")
    apple_connected = bool(ap and ap["status"] == "connected")
    await update.effective_message.reply_text(
        text, reply_markup=_profile_kb(lang, bool(acc), astro, goal, city, sam_connected,
                                        whoop_connected, apple_connected,
                                        acc_expired=bool(acc and acc["status"] == "expired")))


def _profile_kb(lang: str, has_acc: bool, astro: bool, goal: str = "maintain",
                city: str = "Москва", sam_connected: bool = False,
                whoop_connected: bool = False, apple_connected: bool = False,
                acc_expired: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if has_acc:
        # Токены протухли — синк молчит, пока владелец не залогинится заново.
        # Кнопку подключения даём прямо здесь: отключать аккаунт заранее не надо,
        # garminconnect сам выбросит мёртвый tokenstore при логине по паролю.
        if acc_expired:
            rows += [[InlineKeyboardButton(i18n.t("profile.btn_connect", lang),
                                           callback_data="gconnect")]]
        rows += [[InlineKeyboardButton(i18n.t("profile.btn_sync", lang), callback_data="gsync")],
                 [InlineKeyboardButton(i18n.t("profile.btn_history", lang), callback_data="ghist")],
                 [InlineKeyboardButton(i18n.t("profile.btn_disconnect", lang), callback_data="gdisc")]]
    elif not sam_connected and not whoop_connected and not apple_connected:
        rows += [[InlineKeyboardButton(i18n.t("profile.btn_connect", lang), callback_data="gconnect")]]
    rows.append([InlineKeyboardButton(i18n.t("profile.btn_edit", lang), callback_data="pedit:open")])
    rows.append([InlineKeyboardButton(i18n.t("profile.btn_bodyweight", lang), callback_data="bw:start")])
    rows.append([InlineKeyboardButton(
        i18n.t("profile.btn_goal", lang, goal=i18n.t(f"goal.{goal}", lang)),
        callback_data="ngoal:open")])
    rows.append([InlineKeyboardButton(
        i18n.t("profile.btn_city", lang, city=city), callback_data="ncity:open")])
    if sam_connected:
        rows.append([InlineKeyboardButton(
            i18n.t("profile.btn_samsung_disconnect", lang), callback_data="wdisc:samsung")])
    elif not has_acc and not whoop_connected and not apple_connected:
        rows.append([InlineKeyboardButton(
            i18n.t("profile.btn_samsung_connect", lang), callback_data="wconnect:samsung")])
    if whoop_connected:
        rows.append([InlineKeyboardButton(
            i18n.t("profile.btn_whoop_sync", lang), callback_data="wsync:whoop")])
        rows.append([InlineKeyboardButton(
            i18n.t("profile.btn_whoop_disconnect", lang), callback_data="wdisc:whoop")])
    elif not has_acc and not sam_connected and not apple_connected:
        rows.append([InlineKeyboardButton(
            i18n.t("profile.btn_whoop_connect", lang), callback_data="wconnect:whoop")])
    if apple_connected:
        rows.append([InlineKeyboardButton(
            i18n.t("profile.btn_apple_disconnect", lang), callback_data="wdisc:apple")])
    elif not has_acc and not sam_connected and not whoop_connected:
        rows.append([InlineKeyboardButton(
            i18n.t("profile.btn_apple_connect", lang), callback_data="wconnect:apple")])
    astro_key = "profile.btn_astro_on" if astro else "profile.btn_astro_off"
    rows.append([InlineKeyboardButton(i18n.t(astro_key, lang), callback_data="astro:toggle")])
    return InlineKeyboardMarkup(rows)


@restricted
async def astro_toggle_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    q = update.callback_query
    uid = q.from_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        new = not botdb.user_astro(con, uid)
        botdb.set_astro(con, uid, new)
        acc = botdb.garmin_account_get(con, uid)
        sam = botdb.watch_account_get(con, uid, "samsung")
        wh = botdb.watch_account_get(con, uid, "whoop")
        ap = botdb.watch_account_get(con, uid, "apple")
        goal = botdb.user_goal(con, uid)
        city = botdb.user_city(con, uid)
    finally:
        con.close()
    sam_connected = bool(sam and sam["status"] == "connected")
    whoop_connected = bool(wh and wh["status"] == "connected")
    apple_connected = bool(ap and ap["status"] == "connected")
    await q.answer(i18n.t("profile.astro_on" if new else "profile.astro_off", lang))
    await q.edit_message_reply_markup(
        reply_markup=_profile_kb(lang, bool(acc), new, goal, city, sam_connected,
                                  whoop_connected, apple_connected))


@restricted
async def gsync_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import asyncio
    from .. import db as botdb
    from ..garmin_sync import sync_recent
    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid)
    con.close()
    await update.callback_query.answer()
    await update.effective_message.reply_text(i18n.t("garmin.syncing", lang))
    try:
        res = await asyncio.to_thread(sync_recent, context.bot_data["db_path"], uid, str(botdb.garmin_tokenstore(uid)))
        from .. import activity
        activity.log(context, uid, activity.GARMIN_SYNC)
        await update.effective_message.reply_text(
            i18n.t("garmin.sync_done", lang, days=res["days"], activities=res["activities"], last=res["last"]))
    except Exception:
        con = botdb.connect(context.bot_data["db_path"])
        try:
            botdb.garmin_account_set_status(con, uid, "expired")
        finally:
            con.close()
        await update.effective_message.reply_text(i18n.t("garmin.sync_failed", lang))


@restricted
async def ghist_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import asyncio
    from .. import db as botdb
    from ..garmin_sync import sync_history
    uid = update.effective_user.id
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid)
    con.close()
    await update.callback_query.answer()
    await update.effective_message.reply_text(i18n.t("garmin.history_loading", lang))
    try:
        res = await asyncio.to_thread(sync_history, context.bot_data["db_path"], uid, str(botdb.garmin_tokenstore(uid)))
        from .. import activity
        activity.log(context, uid, activity.GARMIN_HISTORY)
        await update.effective_message.reply_text(
            i18n.t("garmin.sync_done", lang, days=res["days"], activities=res["activities"], last=res["last"]))
    except Exception:
        con = botdb.connect(context.bot_data["db_path"])
        try:
            botdb.garmin_account_set_status(con, uid, "expired")
        finally:
            con.close()
        await update.effective_message.reply_text(i18n.t("garmin.sync_failed", lang))


@restricted
async def gdisc_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .. import db as botdb
    uid = update.effective_user.id
    await update.callback_query.answer()
    con = botdb.connect(context.bot_data["db_path"])
    try:
        lang = botdb.user_lang(con, uid)
        disconnect_garmin(con, uid)
    finally:
        con.close()
    await update.effective_message.reply_text(i18n.t("garmin.disconnected", lang))


async def _open_app(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     view: str, label_key: str, intro_key: str) -> None:
    from .. import db as botdb
    uid = update.effective_user.id if update.effective_user else 0
    con = botdb.connect(context.bot_data["db_path"])
    lang = botdb.user_lang(con, uid)
    con.close()
    url = miniapp_url()
    if not url:
        await update.effective_message.reply_text(i18n.t("app.not_running", lang))
        return
    full = f"{url.rstrip('/')}/?view={view}&v={int(time.time())}"
    label = i18n.t(label_key, lang)
    intro = i18n.t(intro_key, lang)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(label, web_app=WebAppInfo(url=full))]])
    await update.effective_message.reply_text(intro, reply_markup=kb)
    from .. import activity
    activity.log(context, uid, activity.MINIAPP_OPEN)


@restricted
async def _svodka(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open_app(update, context, "summary", "app.open_summary_btn", "app.open_summary_intro")


@restricted
async def _trenirovki(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open_app(update, context, "workouts", "app.open_workouts_btn", "app.open_workouts_intro")


@restricted
async def _sorevnovaniya(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open_app(update, context, "competitions", "app.open_comps_btn", "app.open_comps_intro")


@restricted
async def _tseli(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open_app(update, context, "goals", "app.open_goals_btn", "app.open_goals_intro")


@restricted
async def _leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open_app(update, context, "leaderboard", "app.open_leaderboard_btn", "app.open_leaderboard_intro")


@restricted
async def _nutrition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open_app(update, context, "nutrition", "app.open_nutrition_btn", "app.open_nutrition_intro")


def register_stubs(app) -> None:
    app.add_handler(MessageHandler(filters.Text(btn_variants("btn.record")), open_record))
    app.add_handler(MessageHandler(filters.Text(btn_variants("btn.analytics")), open_analytics))
    app.add_handler(MessageHandler(filters.Text(btn_variants("btn.svodka")), _svodka))
    app.add_handler(MessageHandler(filters.Text(btn_variants("btn.trenirovki")), _trenirovki))
    app.add_handler(MessageHandler(filters.Text(btn_variants("btn.comp_summary")), _sorevnovaniya))
    app.add_handler(MessageHandler(filters.Text(btn_variants("btn.tseli")), _tseli))
    app.add_handler(MessageHandler(filters.Text(btn_variants("btn.leaderboard")), _leaderboard))
    app.add_handler(MessageHandler(filters.Text(btn_variants("btn.nutrition")), _nutrition))
    app.add_handler(MessageHandler(filters.Text(btn_variants("btn.profile")), _profile))
    app.add_handler(MessageHandler(filters.Text(btn_variants("btn.lang")), _open_lang))
    app.add_handler(MessageHandler(filters.Text([BTN_LANG_RU, BTN_LANG_EN]), _pick_lang))
    app.add_handler(CallbackQueryHandler(gsync_cb, pattern=r"^gsync$"))
    app.add_handler(CallbackQueryHandler(ghist_cb, pattern=r"^ghist$"))
    app.add_handler(CallbackQueryHandler(gdisc_cb, pattern=r"^gdisc$"))
    app.add_handler(CallbackQueryHandler(astro_toggle_cb, pattern=r"^astro:toggle$"))
