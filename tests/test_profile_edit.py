from __future__ import annotations

import asyncio

from telegram.ext import ConversationHandler

from tjbot import db
from tjbot.handlers import profile_edit as pe


class Msg:
    def __init__(self, text=""):
        self.text = text
        self.texts = []
        self.markups = []

    async def reply_text(self, t, **kw):
        self.texts.append(t)
        self.markups.append(kw.get("reply_markup"))


class Q:
    def __init__(self, data, uid=1):
        self.data = data
        self.from_user = type("U", (), {"id": uid})()
        self.message = Msg()
        self.edited = []

    async def answer(self, *a, **k):
        pass

    async def edit_message_text(self, t, **kw):
        self.edited.append(t)


class Upd:
    def __init__(self, q=None, uid=1, text=""):
        self.callback_query = q
        self.effective_user = type("U", (), {"id": uid})()
        self.message = Msg(text)
        self.effective_message = self.message


class Ctx:
    def __init__(self, db_path):
        self.user_data = {}
        self.bot_data = {"db_path": db_path, "tz": "UTC"}


def _setup(tmp_path):
    p = str(tmp_path / "t.db")
    con = db.connect(p)
    db.init_schema(con)
    db.save_user(con, 1, nick="old", height_cm=180, weight_kg=80.0,
                 sex="m", age=30, gym="Universe", level=2)
    con.commit()
    return p, con


def _datas(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row]


def test_setters_touch_single_field(tmp_path):
    p, con = _setup(tmp_path)
    db.set_nick(con, 1, "Алексей")
    db.set_height(con, 1, 176)
    db.set_weight(con, 1, 74.5)
    db.set_sex(con, 1, "f")
    db.set_age(con, 1, 41)
    db.set_gym(con, 1, "Берлога")
    u = db.get_user(con, 1)
    assert u["nick"] == "Алексей"
    assert u["height_cm"] == 176
    assert u["weight_kg"] == 74.5
    assert u["sex"] == "f"
    assert u["age"] == 41
    assert u["gym"] == "Берлога"


def test_set_nick_preserves_level_and_created_at(tmp_path):
    p, con = _setup(tmp_path)
    before = db.get_user(con, 1)
    db.set_nick(con, 1, "новый")
    after = db.get_user(con, 1)
    assert after["level"] == before["level"]
    assert after["created_at"] == before["created_at"]


def test_edit_menu_kb_has_all_fields(tmp_path):
    p, con = _setup(tmp_path)
    datas = _datas(pe.edit_menu_kb(con, "ru", 1))
    assert datas == ["pedit:nick", "pedit:height", "pedit:weight",
                     "pedit:sex", "pedit:age", "pedit:gym", "pedit:done"]


def test_edit_menu_kb_shows_current_values(tmp_path):
    p, con = _setup(tmp_path)
    texts = [b.text for row in pe.edit_menu_kb(con, "ru", 1).inline_keyboard for b in row]
    assert any("old" in t for t in texts)
    assert any("180" in t for t in texts)
    assert any("Universe" in t for t in texts)


def test_open_edit_shows_menu(tmp_path, monkeypatch):
    from tjbot import access
    monkeypatch.setattr(access, "is_allowed", lambda tg_id, path=None: True)
    p, con = _setup(tmp_path)
    q = Q("pedit:open")
    state = asyncio.run(pe.open_edit(Upd(q=q), Ctx(p)))
    assert state == pe.MENU
    assert q.message.markups and _datas(q.message.markups[-1])[0] == "pedit:nick"


def test_pick_text_field_asks_and_sets_state(tmp_path):
    p, con = _setup(tmp_path)
    q = Q("pedit:height")
    ctx = Ctx(p)
    state = asyncio.run(pe.field_router(Upd(q=q), ctx))
    assert state == pe.VALUE
    assert ctx.user_data["pedit_field"] == "height"


def test_save_nick(tmp_path):
    p, con = _setup(tmp_path)
    ctx = Ctx(p)
    ctx.user_data["pedit_field"] = "nick"
    state = asyncio.run(pe.save_value(Upd(text="Алексей"), ctx))
    assert state == pe.MENU
    assert db.get_user(con, 1)["nick"] == "Алексей"


def test_save_height_valid(tmp_path):
    p, con = _setup(tmp_path)
    ctx = Ctx(p)
    ctx.user_data["pedit_field"] = "height"
    state = asyncio.run(pe.save_value(Upd(text="176"), ctx))
    assert state == pe.MENU
    assert db.get_user(con, 1)["height_cm"] == 176


def test_save_height_invalid_stays(tmp_path):
    p, con = _setup(tmp_path)
    ctx = Ctx(p)
    ctx.user_data["pedit_field"] = "height"
    upd = Upd(text="триста")
    state = asyncio.run(pe.save_value(upd, ctx))
    assert state == pe.VALUE
    assert db.get_user(con, 1)["height_cm"] == 180
    assert upd.message.texts


def test_save_weight_comma(tmp_path):
    p, con = _setup(tmp_path)
    ctx = Ctx(p)
    ctx.user_data["pedit_field"] = "weight"
    asyncio.run(pe.save_value(Upd(text="74,5"), ctx))
    assert db.get_user(con, 1)["weight_kg"] == 74.5


def test_save_age_invalid_stays(tmp_path):
    p, con = _setup(tmp_path)
    ctx = Ctx(p)
    ctx.user_data["pedit_field"] = "age"
    state = asyncio.run(pe.save_value(Upd(text="5"), ctx))
    assert state == pe.VALUE
    assert db.get_user(con, 1)["age"] == 30


def test_pick_sex_shows_choices(tmp_path):
    p, con = _setup(tmp_path)
    q = Q("pedit:sex")
    state = asyncio.run(pe.field_router(Upd(q=q), Ctx(p)))
    assert state == pe.MENU
    assert set(_datas(q.message.markups[-1])) == {"sedit:m", "sedit:f"}


def test_set_sex_writes(tmp_path):
    p, con = _setup(tmp_path)
    q = Q("sedit:f")
    state = asyncio.run(pe.set_sex_cb(Upd(q=q), Ctx(p)))
    assert state == pe.MENU
    assert db.get_user(con, 1)["sex"] == "f"


def test_pick_gym_kb_from_list_gyms(tmp_path):
    p, con = _setup(tmp_path)
    db.add_gym(con, "Берлога")
    q = Q("pedit:gym")
    asyncio.run(pe.field_router(Upd(q=q), Ctx(p)))
    datas = _datas(q.message.markups[-1])
    assert datas[0] == "pgym:Universe"
    assert "pgym:Берлога" in datas
    assert datas[-2] == "pgym:other"
    assert datas[-1] == "pgym:solo"


def test_set_gym_writes(tmp_path):
    p, con = _setup(tmp_path)
    db.add_gym(con, "Берлога")
    q = Q("pgym:Берлога")
    state = asyncio.run(pe.set_gym_cb(Upd(q=q), Ctx(p)))
    assert state == pe.MENU
    assert db.get_user(con, 1)["gym"] == "Берлога"


def test_set_gym_solo(tmp_path):
    p, con = _setup(tmp_path)
    q = Q("pgym:solo")
    asyncio.run(pe.set_gym_cb(Upd(q=q), Ctx(p)))
    assert db.get_user(con, 1)["gym"] == "solo"


def test_done_ends(tmp_path):
    p, con = _setup(tmp_path)
    q = Q("pedit:done")
    state = asyncio.run(pe.field_router(Upd(q=q), Ctx(p)))
    assert state == ConversationHandler.END


def test_handler_shape():
    h = pe.handler()
    assert isinstance(h, ConversationHandler)
    assert pe.MENU in h.states and pe.VALUE in h.states
