from __future__ import annotations

import time
from datetime import date, datetime

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, Update, WebAppInfo)
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from tj import i18n

from .. import access
from .. import activity
from .. import db as botdb
from ..access import restricted
from . import menu
from .menu import miniapp_url, not_menu_text, wizard_fallbacks

NAME, DATE, CITY, DEDUP, CATEGORY, DIV_NAME, PICK_DIV = range(7)
FILL_STAGE_TEXT, FILL_RESULT_TEXT, FILL_TOTAL_EDIT = range(10, 13)
FILL_PICK_DIV = 13

_CATEGORY_CODES = ["newbie", "pro", "int", "rx", "custom"]
_CATEGORY_KEYS = {
    "newbie": "comp.cat_newbie",
    "pro": None,
    "int": None,
    "rx": None,
    "custom": "comp.cat_custom",
}
_CATEGORY_FIXED_LABELS = {"pro": "PRO", "int": "INT", "rx": "RX"}


def _category_label(code: str, lang: str) -> str:
    fixed = _CATEGORY_FIXED_LABELS.get(code)
    if fixed is not None:
        return fixed
    return i18n.t(_CATEGORY_KEYS[code], lang)


def comp_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[i18n.t("btn.comp", lang)], [i18n.t("btn.comp_fill", lang)], [i18n.t("btn.back", lang)]],
        resize_keyboard=True)


def _lang(context: ContextTypes.DEFAULT_TYPE, tg_id: int) -> str:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        return botdb.user_lang(con, tg_id)
    finally:
        con.close()


@restricted
async def open_comp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(context, update.effective_user.id)
    await update.effective_message.reply_text(
        i18n.t("comp.section_intro", lang), reply_markup=comp_kb(lang))


@restricted
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    context.user_data["comp"] = {}
    await update.effective_message.reply_text(i18n.t("comp.ask_name", lang))
    return NAME


async def got_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    context.user_data["comp"]["name"] = update.message.text.strip()
    await update.message.reply_text(i18n.t("comp.ask_date", lang))
    return DATE


def _parse_date(txt: str, today: date) -> date | None:
    txt = txt.strip()
    for fmt in ("%d.%m.%Y", "%d.%m"):
        try:
            d = datetime.strptime(txt, fmt).date()
            return d.replace(year=today.year) if fmt == "%d.%m" else d
        except ValueError:
            continue
    return None


async def got_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    d = _parse_date(update.message.text, date.today())
    if d is None:
        await update.message.reply_text(i18n.t("comp.date_invalid", lang))
        return DATE
    iso = d.isoformat()
    context.user_data["comp"]["date_start"] = iso
    context.user_data["comp"]["date_end"] = iso
    await update.message.reply_text(i18n.t("comp.ask_city", lang))
    return CITY


async def got_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    city = update.message.text.strip()
    context.user_data["comp"]["city"] = city
    con = botdb.connect(context.bot_data["db_path"])
    try:
        matches = botdb.find_events_by_city_date(
            con, city=city, date=context.user_data["comp"]["date_start"])
        if matches:
            ev = matches[0]
            full = botdb.get_event(con, ev["id"])
            context.user_data["comp"]["dedup_event"] = full
            divs = full["divisions"]
            div_text = ", ".join(d["name"] for d in divs) if divs else i18n.t("comp.dedup_none", lang)
            text = i18n.t("comp.dedup_prompt", lang, name=full["name"], city=full["city"],
                          date=full["date_start"], divs=div_text)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(i18n.t("comp.btn_yes", lang), callback_data=f"dd:yes:{full['id']}"),
                InlineKeyboardButton(i18n.t("comp.btn_no", lang), callback_data="dd:no"),
            ]])
            await update.message.reply_text(text, reply_markup=kb)
            return DEDUP
    finally:
        con.close()
    return await _ask_category(update.message, lang)


async def dedup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    parts = q.data.split(":", 2)
    if parts[1] == "no":
        return await _ask_category(q.message, lang)
    eid = int(parts[2])
    con = botdb.connect(context.bot_data["db_path"])
    try:
        full = botdb.get_event(con, eid)
        divs = full["divisions"] if full else []
        if len(divs) == 1:
            pid = botdb.add_participant(con, divs[0]["id"], tg_id=q.from_user.id, athlete=None)
            _store_fill_ctx(context, eid=eid, div_id=divs[0]["id"], pid=pid,
                            athlete=None, event_name=full["name"])
            await q.edit_message_text(
                i18n.t("comp.joined_division", lang, name=full["name"], div=divs[0]["name"]),
                reply_markup=_fill_kb(eid, lang))
            return ConversationHandler.END
        if not divs:
            await q.edit_message_text(i18n.t("comp.no_divisions", lang))
            return ConversationHandler.END
        context.user_data["comp"]["dedup_event"] = full
        buttons = [[InlineKeyboardButton(d["name"], callback_data=f"pdiv:{d['id']}")]
                   for d in divs]
        kb = InlineKeyboardMarkup(buttons)
        await q.edit_message_text(i18n.t("comp.pick_division", lang), reply_markup=kb)
        return PICK_DIV
    finally:
        con.close()


async def pick_div(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    div_id = int(q.data.split(":", 1)[1])
    full = context.user_data.get("comp", {}).get("dedup_event", {})
    eid = full.get("id", 0)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        pid = botdb.add_participant(con, div_id, tg_id=q.from_user.id, athlete=None)
    finally:
        con.close()
    _store_fill_ctx(context, eid=eid, div_id=div_id, pid=pid,
                    athlete=None, event_name=full.get("name", ""))
    await q.edit_message_text(i18n.t("comp.joined", lang), reply_markup=_fill_kb(eid, lang))
    return ConversationHandler.END


async def _ask_category(message, lang: str) -> int:
    buttons = [InlineKeyboardButton(_category_label(code, lang), callback_data=f"cat:{code}")
               for code in _CATEGORY_CODES]
    rows = [buttons[:3], buttons[3:]]
    kb = InlineKeyboardMarkup(rows)
    await message.reply_text(i18n.t("comp.ask_category", lang), reply_markup=kb)
    return CATEGORY


async def got_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    code = q.data.split(":", 1)[1]
    if code == "custom":
        await q.edit_message_text(i18n.t("comp.ask_div_name", lang))
        return DIV_NAME
    return await _create_and_join(q, context, _category_label(code, lang), lang)


async def got_div_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    cat = update.message.text.strip()
    uid = update.effective_user.id
    comp = context.user_data["comp"]
    con = botdb.connect(context.bot_data["db_path"])
    try:
        eid = botdb.create_event(
            con, name=comp["name"], city=comp["city"],
            date_start=comp["date_start"], date_end=comp["date_end"],
            sport="crossfit", fmt="", created_by=uid)
        div_id = botdb.add_division(con, eid, name=cat)
        pid = botdb.add_participant(con, div_id, tg_id=uid, athlete=None)
    finally:
        con.close()
    _store_fill_ctx(context, eid=eid, div_id=div_id, pid=pid,
                    athlete=None, event_name=comp["name"])
    context.user_data.pop("comp", None)
    activity.log(context, uid, activity.COMP_ADDED)
    await update.message.reply_text(i18n.t("comp.created", lang), reply_markup=_fill_kb(eid, lang))
    return ConversationHandler.END


async def _create_and_join(q, context: ContextTypes.DEFAULT_TYPE, cat: str, lang: str) -> int:
    comp = context.user_data["comp"]
    uid = q.from_user.id
    con = botdb.connect(context.bot_data["db_path"])
    try:
        eid = botdb.create_event(
            con, name=comp["name"], city=comp["city"],
            date_start=comp["date_start"], date_end=comp["date_end"],
            sport="crossfit", fmt="", created_by=uid)
        div_id = botdb.add_division(con, eid, name=cat)
        pid = botdb.add_participant(con, div_id, tg_id=uid, athlete=None)
    finally:
        con.close()
    _store_fill_ctx(context, eid=eid, div_id=div_id, pid=pid,
                    athlete=None, event_name=comp["name"])
    context.user_data.pop("comp", None)
    activity.log(context, uid, activity.COMP_ADDED)
    await q.edit_message_text(i18n.t("comp.created", lang), reply_markup=_fill_kb(eid, lang))
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    context.user_data.pop("comp", None)
    await update.effective_message.reply_text(i18n.t("comp.cancelled", lang))
    return ConversationHandler.END


def _store_fill_ctx(context, *, eid, div_id, pid, athlete, event_name) -> None:
    context.user_data["fill"] = {
        "eid": eid,
        "div_id": div_id,
        "pid": pid,
        "athlete": athlete or "Я",
        "event_name": event_name,
    }


def _fill_kb(eid: int, lang: str) -> InlineKeyboardMarkup:
    url = miniapp_url()
    rows = [
        [InlineKeyboardButton(i18n.t("comp.btn_stage", lang), callback_data="fill:stage"),
         InlineKeyboardButton(i18n.t("comp.btn_result", lang), callback_data="fill:result")],
        [InlineKeyboardButton(i18n.t("comp.btn_total", lang), callback_data="fill:total")],
    ]
    if url:
        full = f"{url.rstrip('/')}/?view=competition&id={eid}&v={int(time.time())}"
        rows.append([InlineKeyboardButton(i18n.t("comp.btn_analysis", lang), web_app=WebAppInfo(url=full))])
    return InlineKeyboardMarkup(rows)


def _others_btn(lang: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(i18n.t("comp.btn_others", lang), callback_data="others:list")


@restricted
async def fill_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(context, update.effective_user.id)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        comps = botdb.list_competitions(con, update.effective_user.id)
    finally:
        con.close()
    if not comps:
        await update.effective_message.reply_text(
            i18n.t("comp.no_events_yet", lang),
            reply_markup=InlineKeyboardMarkup([[_others_btn(lang)]]))
        return
    rows = [[InlineKeyboardButton(f"{c['name']} ({c['date_start']})",
                                  callback_data=f"fillpick:{c['id']}")] for c in comps]
    rows.append([_others_btn(lang)])
    await update.effective_message.reply_text(
        i18n.t("comp.pick_competition", lang), reply_markup=InlineKeyboardMarkup(rows))


async def fill_list_others(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    con = botdb.connect(context.bot_data["db_path"])
    try:
        comps = botdb.list_other_competitions(con, q.from_user.id)
    finally:
        con.close()
    if not comps:
        await q.edit_message_text(i18n.t("comp.no_other_events_yet", lang))
        return ConversationHandler.END
    rows = [[InlineKeyboardButton(f"{c['name']} ({c['date_start']})",
                                  callback_data=f"otherpick:{c['id']}")] for c in comps]
    await q.edit_message_text(i18n.t("comp.others_title", lang),
                              reply_markup=InlineKeyboardMarkup(rows))
    return ConversationHandler.END


async def other_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    eid = int(q.data.split(":", 1)[1])
    con = botdb.connect(context.bot_data["db_path"])
    try:
        full = botdb.get_event(con, eid)
    finally:
        con.close()
    if not full:
        await q.edit_message_text(i18n.t("comp.not_found", lang))
        return ConversationHandler.END
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("comp.btn_view", lang), callback_data=f"otherview:{eid}"),
        InlineKeyboardButton(i18n.t("comp.btn_join", lang), callback_data=f"fillpick:{eid}"),
    ]])
    await q.edit_message_text(
        i18n.t("comp.other_event_line", lang, name=full["name"], city=full["city"],
              date=full["date_start"]),
        reply_markup=kb)
    return ConversationHandler.END


def _format_other_view(full: dict, stages_by_div: dict, lang: str = "ru") -> str:
    lines = [full["name"], f"{full['city']}, {full['date_start']}"]
    for d in full.get("divisions", []):
        lines.append("")
        lines.append(i18n.t("comp.division_label", lang, name=d["name"]))
        stages = stages_by_div.get(d["id"], [])
        if not stages:
            lines.append(i18n.t("comp.no_stages", lang))
        else:
            for s in stages:
                lines.append(i18n.t("comp.stage_line", lang, idx=s["idx"], name=s["name"]))
    return "\n".join(lines)


async def other_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    eid = int(q.data.split(":", 1)[1])
    con = botdb.connect(context.bot_data["db_path"])
    try:
        full = botdb.get_event(con, eid)
        stages_by_div = {d["id"]: botdb.get_stages(con, d["id"])
                         for d in (full["divisions"] if full else [])}
    finally:
        con.close()
    if not full:
        await q.edit_message_text(i18n.t("comp.not_found", lang))
        return ConversationHandler.END
    await q.edit_message_text(_format_other_view(full, stages_by_div, lang))
    return ConversationHandler.END


async def _open_fill_card(q, context: ContextTypes.DEFAULT_TYPE, *, eid: int, div_id: int,
                          event_name: str, lang: str) -> int:
    con = botdb.connect(context.bot_data["db_path"])
    try:
        row = con.execute(
            'SELECT "id" FROM comp_participants WHERE "division_id"=? AND "tg_id"=? '
            'ORDER BY "id" LIMIT 1', (div_id, q.from_user.id)).fetchone()
        pid = row["id"] if row else botdb.add_participant(
            con, div_id, tg_id=q.from_user.id, athlete=None)
    finally:
        con.close()
    _store_fill_ctx(context, eid=eid, div_id=div_id, pid=pid,
                    athlete=None, event_name=event_name)
    await q.edit_message_text(i18n.t("comp.fill_intro", lang), reply_markup=_fill_kb(eid, lang))
    return ConversationHandler.END


async def fill_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    eid = int(q.data.split(":", 1)[1])
    con = botdb.connect(context.bot_data["db_path"])
    try:
        full = botdb.get_event(con, eid)
    finally:
        con.close()
    if not full:
        await q.edit_message_text(i18n.t("comp.not_found", lang))
        return ConversationHandler.END
    divs = full["divisions"]
    if not divs:
        await q.edit_message_text(i18n.t("comp.no_divisions", lang))
        return ConversationHandler.END
    if len(divs) == 1:
        return await _open_fill_card(q, context, eid=eid, div_id=divs[0]["id"],
                                     event_name=full["name"], lang=lang)
    context.user_data["fill_pick_event"] = {"id": eid, "name": full["name"]}
    buttons = [[InlineKeyboardButton(d["name"], callback_data=f"filldiv:{d['id']}")]
               for d in divs]
    await q.edit_message_text(i18n.t("comp.pick_division", lang), reply_markup=InlineKeyboardMarkup(buttons))
    return FILL_PICK_DIV


async def fill_pick_div(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    div_id = int(q.data.split(":", 1)[1])
    ev = context.user_data.pop("fill_pick_event", {})
    return await _open_fill_card(q, context, eid=ev.get("id", 0), div_id=div_id,
                                 event_name=ev.get("name", ""), lang=lang)


async def fill_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    action = q.data.split(":", 1)[1]
    if action == "stage":
        await q.message.reply_text(i18n.t("comp.ask_stage_text", lang))
        return FILL_STAGE_TEXT
    if action == "result":
        await q.message.reply_text(i18n.t("comp.ask_result_text", lang))
        return FILL_RESULT_TEXT
    if action == "total":
        return await _do_suggest_total(q, context, lang)
    return ConversationHandler.END


async def fill_stage_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from .. import vision
    lang = _lang(context, update.effective_user.id)
    fill = context.user_data.get("fill", {})
    if not fill.get("div_id"):
        await update.message.reply_text(i18n.t("comp.no_context", lang))
        return ConversationHandler.END
    if not vision.has_vision():
        await update.message.reply_text(i18n.t("comp.vision_unavailable_stage", lang))
        return FILL_STAGE_TEXT
    if not access.llm_quota_consume(update.effective_user.id):
        await update.message.reply_text(
            i18n.t("comp.llm_limit_stage", lang, limit=access.LLM_DAILY_LIMIT))
        return FILL_STAGE_TEXT
    await update.message.reply_text(i18n.t("comp.parsing_stages", lang))
    try:
        f = await context.bot.get_file(update.message.photo[-1].file_id)
        buf = await f.download_as_bytearray()
        stages = vision.parse_stages(bytes(buf),
                                     engine=vision.engine_for(update.effective_user.id))
    except Exception:
        stages = None
    if not stages:
        await update.message.reply_text(i18n.t("comp.stage_not_recognized", lang))
        return FILL_STAGE_TEXT
    context.user_data["stage_draft"] = stages
    dash = i18n.t("comp.stage_dash", lang)
    preview = "\n".join(
        i18n.t("comp.stage_preview_line", lang, idx=i + 1, name=s.get("name") or dash,
              presc=(s.get("prescription") or "")[:120])
        for i, s in enumerate(stages))
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.t("comp.btn_save", lang), callback_data="cstage:save")]])
    await update.message.reply_text(
        i18n.t("comp.stage_preview_intro", lang, preview=preview), reply_markup=kb)
    return FILL_STAGE_TEXT


async def confirm_stage_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    fill = context.user_data.get("fill", {})
    if not fill.get("div_id"):
        await q.edit_message_text(i18n.t("comp.context_lost", lang))
        return ConversationHandler.END
    drafts = context.user_data.get("stage_draft") or []
    con = botdb.connect(context.bot_data["db_path"])
    try:
        stages = botdb.get_stages(con, fill["div_id"])
        idx = max((s["idx"] for s in stages), default=0)
        for st in drafts:
            idx += 1
            botdb.add_stage(con, fill["div_id"], idx=idx,
                            name=(st.get("name") or f"Этап {idx}")[:80],
                            prescription=st.get("prescription") or "",
                            movements=st.get("movements") or [],
                            fmt=st.get("format") or "text")
    finally:
        con.close()
    context.user_data.pop("stage_draft", None)
    await q.edit_message_text(i18n.t("comp.stages_saved", lang, n=len(drafts)))
    await q.message.reply_text(i18n.t("comp.done", lang), reply_markup=_fill_kb(fill["eid"], lang))
    return ConversationHandler.END


async def fill_result_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from .. import vision
    lang = _lang(context, update.effective_user.id)
    fill = context.user_data.get("fill", {})
    if not fill.get("div_id"):
        await update.message.reply_text(i18n.t("comp.no_context", lang))
        return ConversationHandler.END
    if not vision.has_vision():
        await update.message.reply_text(i18n.t("comp.vision_unavailable_result", lang))
        return FILL_RESULT_TEXT
    if not access.llm_quota_consume(update.effective_user.id):
        await update.message.reply_text(
            i18n.t("comp.llm_limit_result", lang, limit=access.LLM_DAILY_LIMIT))
        return FILL_RESULT_TEXT
    await update.message.reply_text(i18n.t("comp.parsing_protocol", lang))
    try:
        f = await context.bot.get_file(update.message.photo[-1].file_id)
        buf = await f.download_as_bytearray()
        res = vision.parse_results(bytes(buf), fill["athlete"],
                                   engine=vision.engine_for(update.effective_user.id))
    except Exception:
        res = None
    rows = (res or {}).get("rows") or []
    if not rows:
        await update.message.reply_text(i18n.t("comp.results_not_found", lang))
        return FILL_RESULT_TEXT
    context.user_data["result_draft"] = rows
    preview = "\n".join(
        i18n.t("comp.result_preview_line", lang, stage=r.get("stage"), value=r.get("value"),
              place=r.get("place"))
        for r in rows)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(i18n.t("comp.btn_save", lang), callback_data="cres:save")]])
    await update.message.reply_text(
        i18n.t("comp.result_preview_intro", lang, athlete=fill["athlete"], preview=preview),
        reply_markup=kb)
    return FILL_RESULT_TEXT


async def confirm_result_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    fill = context.user_data.get("fill", {})
    if not fill.get("div_id"):
        await q.edit_message_text(i18n.t("comp.context_lost", lang))
        return ConversationHandler.END
    rows = context.user_data.get("result_draft") or []
    saved = 0
    con = botdb.connect(context.bot_data["db_path"])
    try:
        stages = botdb.get_stages(con, fill["div_id"])
        by_idx = {s["idx"]: s["id"] for s in stages}
        ordered = [s["id"] for s in sorted(stages, key=lambda s: s["idx"])]
        for i, r in enumerate(rows):
            st = r.get("stage")
            sid = None
            if isinstance(st, int) and st in by_idx:
                sid = by_idx[st]
            elif str(st).isdigit() and int(st) in by_idx:
                sid = by_idx[int(st)]
            else:
                sid = next((s["id"] for s in stages if (s["name"] or "").strip() == str(st).strip()), None)
            if sid is None and i < len(ordered):
                sid = ordered[i]
            if sid is None:
                continue
            try:
                place = int(r.get("place"))
            except (TypeError, ValueError):
                place = None
            botdb.add_comp_result(con, sid, athlete=fill["athlete"],
                                  value=str(r.get("value") or ""), place=place, points=place)
            saved += 1
    finally:
        con.close()
    context.user_data.pop("result_draft", None)
    await q.edit_message_text(i18n.t("comp.results_saved", lang, n=saved))
    await q.message.reply_text(i18n.t("comp.done", lang), reply_markup=_fill_kb(fill["eid"], lang))
    return ConversationHandler.END


async def fill_stage_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    text = update.message.text.strip()
    fill = context.user_data.get("fill", {})
    div_id = fill.get("div_id")
    if not div_id:
        await update.message.reply_text(i18n.t("comp.no_context", lang))
        return ConversationHandler.END
    first_line = text.splitlines()[0][:80]
    con = botdb.connect(context.bot_data["db_path"])
    try:
        stages = botdb.get_stages(con, div_id)
        next_idx = (max((s["idx"] for s in stages), default=0) + 1)
        botdb.add_stage(con, div_id, idx=next_idx, name=first_line,
                        prescription=text, movements=[], fmt="text")
    finally:
        con.close()
    await update.message.reply_text(i18n.t("comp.stage_added", lang, idx=next_idx),
                                    reply_markup=_fill_kb(fill["eid"], lang))
    return ConversationHandler.END


async def fill_result_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    fill = context.user_data.get("fill", {})
    div_id = fill.get("div_id")
    if not div_id:
        await update.message.reply_text(i18n.t("comp.no_context", lang))
        return ConversationHandler.END
    parts = [p.strip() for p in update.message.text.split(",")]
    if len(parts) < 2:
        await update.message.reply_text(i18n.t("comp.result_text_hint", lang))
        return FILL_RESULT_TEXT
    value = parts[0]
    try:
        place = int(parts[1])
    except ValueError:
        await update.message.reply_text(i18n.t("comp.place_invalid", lang))
        return FILL_RESULT_TEXT
    field_size = None
    if len(parts) >= 3:
        try:
            field_size = int(parts[2])
        except ValueError:
            pass
    athlete = fill["athlete"]
    con = botdb.connect(context.bot_data["db_path"])
    try:
        stages = botdb.get_stages(con, div_id)
        stage_id = None
        for s in reversed(stages):
            athlete_results = [r for r in s["results"] if r["athlete"] == athlete]
            if not athlete_results:
                stage_id = s["id"]
                break
        if stage_id is None:
            if stages:
                stage_id = stages[-1]["id"]
            else:
                await update.message.reply_text(i18n.t("comp.no_stages_add_first", lang))
                return ConversationHandler.END
        botdb.add_comp_result(con, stage_id, athlete=athlete, value=value,
                             place=place, points=place)
        if field_size:
            con.execute('UPDATE comp_divisions SET "field_size"=? WHERE "id"=? AND "field_size" IS NULL',
                        (field_size, div_id))
            con.commit()
    finally:
        con.close()
    await update.message.reply_text(i18n.t("comp.result_logged", lang, value=value, place=place),
                                    reply_markup=_fill_kb(fill["eid"], lang))
    return ConversationHandler.END


async def _do_suggest_total(q_or_msg, context: ContextTypes.DEFAULT_TYPE, lang: str) -> int:
    fill = context.user_data.get("fill", {})
    div_id = fill.get("div_id")
    pid = fill.get("pid")
    if not div_id:
        msg = q_or_msg.message if hasattr(q_or_msg, "message") else q_or_msg
        await msg.reply_text(i18n.t("comp.no_context", lang))
        return ConversationHandler.END
    athlete = fill["athlete"]
    con = botdb.connect(context.bot_data["db_path"])
    try:
        sug = botdb.suggest_total(con, div_id, athlete)
        div = con.execute('SELECT * FROM comp_divisions WHERE "id"=?', (div_id,)).fetchone()
        field_size = div["field_size"] if div else None
    finally:
        con.close()
    if sug["total_points"] is None:
        msg = q_or_msg.message if hasattr(q_or_msg, "message") else q_or_msg
        await msg.reply_text(i18n.t("comp.no_results_to_count", lang))
        return ConversationHandler.END
    place_str = f"{sug['final_place']}/{field_size}" if field_size else str(sug['final_place'])
    context.user_data["fill"]["_suggested"] = sug
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(i18n.t("comp.btn_yes", lang), callback_data="tot:yes"),
        InlineKeyboardButton(i18n.t("comp.btn_fix", lang), callback_data="tot:edit"),
    ]])
    msg = q_or_msg.message if hasattr(q_or_msg, "message") else q_or_msg
    await msg.reply_text(
        i18n.t("comp.total_suggested", lang, points=sug["total_points"], place=place_str),
        reply_markup=kb)
    return ConversationHandler.END


async def total_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    lang = _lang(context, q.from_user.id)
    action = q.data.split(":", 1)[1]
    fill = context.user_data.get("fill", {})
    if action == "yes":
        sug = fill.get("_suggested", {})
        pid = fill.get("pid")
        if pid and sug.get("total_points") is not None:
            con = botdb.connect(context.bot_data["db_path"])
            try:
                botdb.set_total(con, pid,
                                final_place=sug["final_place"],
                                total_points=sug["total_points"],
                                confirmed=1)
            finally:
                con.close()
        await q.edit_message_text(
            i18n.t("comp.total_confirmed", lang, points=sug.get("total_points"),
                  place=sug.get("final_place")),
            reply_markup=_fill_kb(fill.get("eid", 0), lang))
    else:
        await q.edit_message_text(i18n.t("comp.ask_total_manual", lang))
        return FILL_TOTAL_EDIT
    return ConversationHandler.END


async def fill_total_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context, update.effective_user.id)
    parts = [p.strip() for p in update.message.text.split(",")]
    fill = context.user_data.get("fill", {})
    pid = fill.get("pid")
    if len(parts) < 2 or not pid:
        await update.message.reply_text(i18n.t("comp.total_text_hint", lang))
        return FILL_TOTAL_EDIT
    try:
        pts = float(parts[0])
        pl = int(parts[1])
    except ValueError:
        await update.message.reply_text(i18n.t("comp.total_invalid", lang))
        return FILL_TOTAL_EDIT
    con = botdb.connect(context.bot_data["db_path"])
    try:
        botdb.set_total(con, pid, final_place=pl, total_points=pts, confirmed=1)
    finally:
        con.close()
    await update.message.reply_text(i18n.t("comp.total_logged", lang, points=pts, place=pl),
                                    reply_markup=_fill_kb(fill.get("eid", 0), lang))
    return ConversationHandler.END


def handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text(menu.btn_variants("btn.comp")), entry),
            MessageHandler(filters.Text(menu.btn_variants("btn.comp_fill")), fill_list),
            CallbackQueryHandler(fill_pick, pattern=r"^fillpick:"),
            CallbackQueryHandler(fill_list_others, pattern=r"^others:list$"),
            CallbackQueryHandler(other_pick, pattern=r"^otherpick:"),
            CallbackQueryHandler(other_view, pattern=r"^otherview:"),
            CallbackQueryHandler(fill_dispatch, pattern=r"^fill:"),
            CallbackQueryHandler(total_confirm, pattern=r"^tot:"),
            CallbackQueryHandler(confirm_stage_save, pattern=r"^cstage:save$"),
            CallbackQueryHandler(confirm_result_save, pattern=r"^cres:save$"),
        ],
        states={
            NAME: [MessageHandler(not_menu_text(), got_name)],
            DATE: [MessageHandler(not_menu_text(), got_date)],
            CITY: [MessageHandler(not_menu_text(), got_city)],
            DEDUP: [CallbackQueryHandler(dedup, pattern=r"^dd:")],
            CATEGORY: [CallbackQueryHandler(got_category, pattern=r"^cat:")],
            DIV_NAME: [MessageHandler(not_menu_text(), got_div_name)],
            PICK_DIV: [CallbackQueryHandler(pick_div, pattern=r"^pdiv:")],
            FILL_PICK_DIV: [CallbackQueryHandler(fill_pick_div, pattern=r"^filldiv:")],
            FILL_STAGE_TEXT: [
                MessageHandler(filters.PHOTO, fill_stage_photo),
                CallbackQueryHandler(confirm_stage_save, pattern=r"^cstage:save$"),
                MessageHandler(not_menu_text(), fill_stage_text)],
            FILL_RESULT_TEXT: [
                MessageHandler(filters.PHOTO, fill_result_photo),
                CallbackQueryHandler(confirm_result_save, pattern=r"^cres:save$"),
                MessageHandler(not_menu_text(), fill_result_text)],
            FILL_TOTAL_EDIT: [MessageHandler(not_menu_text(), fill_total_edit)],
        },
        fallbacks=wizard_fallbacks(),
        name="competition",
    )


def register(app) -> None:
    app.add_handler(MessageHandler(
        filters.Text(list(menu.btn_variants("btn.comp_section"))), open_comp))
    app.add_handler(handler())
