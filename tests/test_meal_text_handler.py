"""Поведенческие тесты текстового ввода еды (async напрямую)."""
from __future__ import annotations

import asyncio

from telegram.ext import ConversationHandler

import tjbot.vision as vision
from tjbot import db as botdb
from tjbot.handlers import meal as meal_h

DRAFT = {"foods": [{"name": "овощной суп", "grams": 300, "kcal": 150,
                    "protein_g": 5, "fat_g": 5, "carb_g": 20,
                    "fiber_g": None, "sugar_g": None, "sodium_mg": None,
                    "iron_mg": None, "calcium_mg": None, "magnesium_mg": None,
                    "potassium_mg": None}],
         "totals": {"kcal": 150, "protein_g": 5, "fat_g": 5, "carb_g": 20},
         "question": None, "confidence": "medium",
         "quality": 2, "quality_note": "лёгкий суп"}


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMsg:
    def __init__(self, text=None):
        self.text = text
        self.photo = None
        self.caption = None
        self.replies: list[str] = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, uid, text=None):
        self.effective_user = FakeUser(uid)
        self.message = FakeMsg(text=text)


class FakeCbQuery:
    def __init__(self, uid, data):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMsg()
        self.edits: list[str] = []

    async def answer(self, *a, **k):
        pass

    async def edit_message_text(self, text, **kw):
        self.edits.append(text)


class FakeCbUpdate:
    def __init__(self, uid, data):
        self.effective_user = FakeUser(uid)
        self.callback_query = FakeCbQuery(uid, data)


class FakeCtx:
    def __init__(self, db_path, user_data=None):
        self.user_data = user_data or {}
        self.bot_data = {"db_path": db_path}
        self.bot = None


def _db_path(tmp_path) -> str:
    p = tmp_path / "t.db"
    con = botdb.connect(str(p))
    try:
        botdb.init_schema(con)
        con.commit()
    finally:
        con.close()
    return str(p)


def _quiet(monkeypatch):
    monkeypatch.setattr(meal_h.access, "is_admin", lambda uid: True)
    monkeypatch.setattr(meal_h.activity, "log", lambda *a, **k: None)


def test_text_parses_saves_note(monkeypatch, tmp_path):
    _quiet(monkeypatch)
    seen = {}

    def fake_parse(desc, engine="gemini", correction=None):
        seen["desc"], seen["correction"] = desc, correction
        return DRAFT

    monkeypatch.setattr(vision, "parse_meal_text", fake_parse)
    ctx = FakeCtx(_db_path(tmp_path), {"meal_day": "2026-07-11"})
    upd = FakeUpdate(1, text="стандартный овощной суп")
    state = asyncio.run(meal_h.rec_text(upd, ctx))
    assert state == meal_h.R_CONFIRM
    assert seen["desc"] == "стандартный овощной суп"
    assert ctx.user_data["meal_desc"] == "стандартный овощной суп"

    cb = FakeCbUpdate(1, "mr:ok")
    state2 = asyncio.run(meal_h.rec_confirm(cb, ctx))
    assert state2 == ConversationHandler.END
    con = botdb.connect(ctx.bot_data["db_path"])
    try:
        meals = botdb.meals_for_day(con, 1, "2026-07-11")
    finally:
        con.close()
    assert len(meals) == 1
    assert meals[0]["note"] == "стандартный овощной суп"
    assert meals[0]["photo_id"] is None


def test_short_text_reasks_without_quota(monkeypatch, tmp_path):
    _quiet(monkeypatch)
    monkeypatch.setattr(meal_h.access, "is_admin", lambda uid: False)

    def boom(*a, **k):
        raise AssertionError("квота не должна списываться")

    monkeypatch.setattr(meal_h.access, "llm_quota_consume", boom)
    ctx = FakeCtx(_db_path(tmp_path), {"meal_day": "2026-07-11"})
    upd = FakeUpdate(1, text="ок")
    state = asyncio.run(meal_h.rec_text(upd, ctx))
    assert state == meal_h.R_PHOTO
    assert upd.message.replies


def test_text_quota_blocks(monkeypatch, tmp_path):
    _quiet(monkeypatch)
    monkeypatch.setattr(meal_h.access, "is_admin", lambda uid: False)
    monkeypatch.setattr(meal_h.access, "llm_quota_consume", lambda uid: False)
    called = {"parse": False}
    monkeypatch.setattr(vision, "parse_meal_text",
                        lambda *a, **k: called.__setitem__("parse", True))
    ctx = FakeCtx(_db_path(tmp_path), {"meal_day": "2026-07-11"})
    upd = FakeUpdate(1, text="стандартный овощной суп")
    state = asyncio.run(meal_h.rec_text(upd, ctx))
    assert state == ConversationHandler.END
    assert called["parse"] is False


def test_correction_accumulates_for_text(monkeypatch, tmp_path):
    _quiet(monkeypatch)
    seen = {}

    def fake_parse(desc, engine="gemini", correction=None):
        seen["correction"] = correction
        return DRAFT

    monkeypatch.setattr(vision, "parse_meal_text", fake_parse)
    ctx = FakeCtx(_db_path(tmp_path),
                  {"meal_day": "2026-07-11", "meal_desc": "суп",
                   "meal_notes": ["без масла"]})
    upd = FakeUpdate(1, text="с хлебом")
    state = asyncio.run(meal_h.rec_correction(upd, ctx))
    assert state == meal_h.R_CONFIRM
    assert seen["correction"] == "без масла; с хлебом"


def test_edit_fix_text_meal(monkeypatch, tmp_path):
    _quiet(monkeypatch)
    db_path = _db_path(tmp_path)
    con = botdb.connect(db_path)
    try:
        botdb.add_meal(con, 1, "2026-07-11", "2026-07-11T12:00:00",
                       DRAFT["foods"], DRAFT["totals"],
                       note="стандартный овощной суп")
        meal_id = botdb.meals_for_day(con, 1, "2026-07-11")[0]["id"]
    finally:
        con.close()
    ctx = FakeCtx(db_path, {"meal_day": "2026-07-11", "meal_edit_id": meal_id})
    cb = FakeCbUpdate(1, "mea:fix")
    state = asyncio.run(meal_h.edit_pick(cb, ctx))
    assert state == meal_h.E_CORR
    assert ctx.user_data["meal_desc"] == "стандартный овощной суп"
    assert "meal_photo" not in ctx.user_data


def test_edit_fix_nothing_to_reparse(monkeypatch, tmp_path):
    _quiet(monkeypatch)
    db_path = _db_path(tmp_path)
    con = botdb.connect(db_path)
    try:
        botdb.add_meal(con, 1, "2026-07-11", "2026-07-11T12:00:00",
                       DRAFT["foods"], DRAFT["totals"])
        meal_id = botdb.meals_for_day(con, 1, "2026-07-11")[0]["id"]
    finally:
        con.close()
    ctx = FakeCtx(db_path, {"meal_day": "2026-07-11", "meal_edit_id": meal_id})
    cb = FakeCbUpdate(1, "mea:fix")
    state = asyncio.run(meal_h.edit_pick(cb, ctx))
    assert state == ConversationHandler.END
    from tj import i18n
    assert i18n.t("meal.fix_no_photo", "ru") in cb.callback_query.edits


class _FakeFile:
    async def download_as_bytearray(self):
        return bytearray(b"img")


class _FakeBot:
    async def get_file(self, file_id):
        return _FakeFile()


class FakePhoto:
    file_id = "f1"


def test_meal_submenu_buttons_are_menu():
    from tj import i18n
    from tjbot.handlers import menu
    variants = menu.all_menu_variants()
    for key in ("btn.meal_record", "btn.meal_water", "btn.meal_edit",
                "btn.meal_view", "btn.meal_report"):
        assert i18n.t(key, "ru") in variants
        assert i18n.t(key, "en") in variants


def test_text_fail_then_photo_no_note_leak(monkeypatch, tmp_path):
    _quiet(monkeypatch)
    monkeypatch.setattr(vision, "parse_meal_text", lambda *a, **k: None)
    monkeypatch.setattr(vision, "parse_meal", lambda *a, **k: DRAFT)
    ctx = FakeCtx(_db_path(tmp_path), {"meal_day": "2026-07-11"})
    ctx.bot = _FakeBot()
    upd = FakeUpdate(1, text="стандартный овощной суп")
    assert asyncio.run(meal_h.rec_text(upd, ctx)) == meal_h.R_PHOTO
    photo_upd = FakeUpdate(1)
    photo_upd.message.photo = [FakePhoto()]
    assert asyncio.run(meal_h.rec_photo(photo_upd, ctx)) == meal_h.R_CONFIRM
    cb = FakeCbUpdate(1, "mr:ok")
    asyncio.run(meal_h.rec_confirm(cb, ctx))
    con = botdb.connect(ctx.bot_data["db_path"])
    try:
        meals = botdb.meals_for_day(con, 1, "2026-07-11")
    finally:
        con.close()
    assert meals[0]["note"] is None
    assert meals[0]["photo_id"] == "f1"


def test_photo_then_text_note_wins(monkeypatch, tmp_path):
    _quiet(monkeypatch)
    monkeypatch.setattr(vision, "parse_meal_text", lambda *a, **k: DRAFT)
    ctx = FakeCtx(_db_path(tmp_path),
                  {"meal_day": "2026-07-11", "meal_photo": "old"})
    upd = FakeUpdate(1, text="стандартный овощной суп")
    assert asyncio.run(meal_h.rec_text(upd, ctx)) == meal_h.R_CONFIRM
    cb = FakeCbUpdate(1, "mr:ok")
    asyncio.run(meal_h.rec_confirm(cb, ctx))
    con = botdb.connect(ctx.bot_data["db_path"])
    try:
        meals = botdb.meals_for_day(con, 1, "2026-07-11")
    finally:
        con.close()
    assert meals[0]["note"] == "стандартный овощной суп"
    assert meals[0]["photo_id"] is None
