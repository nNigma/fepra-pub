from __future__ import annotations
import asyncio

from tj import i18n
from tjbot import db as botdb
from tjbot.handlers import add_result as ar
from tjbot.handlers import onboarding as ob
from tjbot.handlers import record_workout as rw


def _db_path(tmp_path) -> str:
    p = tmp_path / "t.db"
    con = botdb.connect(str(p))
    try:
        botdb.init_schema(con)
        con.commit()
    finally:
        con.close()
    return str(p)


class _Msg:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kw):
        self.replies.append((text, kw.get("reply_markup")))
        return type("M", (), {"message_id": len(self.replies)})()


class _CQ:
    def __init__(self, data, uid=1):
        self.data = data
        self.message = _Msg()
        self.from_user = type("U", (), {"id": uid})()
        self.edited = []

    async def answer(self):
        pass

    async def edit_message_text(self, text, **kw):
        self.edited.append((text, kw.get("reply_markup")))


class _Upd:
    def __init__(self, data, uid=1):
        self.callback_query = _CQ(data, uid)
        self.effective_user = self.callback_query.from_user

    @property
    def effective_message(self):
        return self.callback_query.message


class _Ctx:
    def __init__(self, user_data=None, db_path=":memory:"):
        self.user_data = user_data or {}
        self.bot_data = {"db_path": db_path}


def _flat(kb):
    return [b for row in kb.inline_keyboard for b in row]


def test_guide_i18n_keys():
    for lang in ("ru", "en"):
        guide = i18n.t("onboarding.results_guide", lang)
        assert "45" in guide and "60" in guide
        assert i18n.t("onboarding.btn_guide_ok", lang)
        assert i18n.t("record.btn_results_help", lang)


def test_get_gym_saves_and_shows_guide(tmp_path):
    db = _db_path(tmp_path)
    u = _Upd("gym:Universe")
    c = _Ctx({"nick": "n", "height_cm": 180, "weight_kg": 80.0, "sex": "m", "age": 30},
             db_path=db)
    assert asyncio.run(ob.get_gym(u, c)) == ob.GUIDE
    con = botdb.connect(db)
    try:
        assert botdb.get_user(con, 1)["gym"] == "Universe"
    finally:
        con.close()
    text, kb = u.callback_query.message.replies[0]
    assert text == i18n.t("onboarding.results_guide", "ru")
    assert _flat(kb)[0].callback_data == "guideok"
    assert set(c.user_data) == {"guide_msg_id"}


def test_guide_ok_ends_with_menu(tmp_path):
    from telegram.ext import ConversationHandler
    u = _Upd("guideok")
    c = _Ctx(db_path=_db_path(tmp_path))
    assert asyncio.run(ob.guide_ok(u, c)) == ConversationHandler.END
    assert u.callback_query.edited[0][0] == i18n.t("onboarding.results_guide", "ru")
    assert u.callback_query.edited[0][1] is None
    assert u.callback_query.message.replies


def test_guide_any_text_falls_through_to_menu(tmp_path):
    from telegram.ext import ConversationHandler

    class _TextUpd:
        def __init__(self):
            self.effective_user = type("U", (), {"id": 1})()
            self.effective_message = _Msg()

    u = _TextUpd()
    c = _Ctx(db_path=_db_path(tmp_path))
    assert asyncio.run(ob.guide_text(u, c)) == ConversationHandler.END
    assert u.effective_message.replies


def test_guide_text_removes_memo_keyboard(tmp_path):
    from telegram.ext import ConversationHandler

    calls = []

    class _Bot:
        async def edit_message_reply_markup(self, chat_id, message_id, reply_markup):
            calls.append((chat_id, message_id, reply_markup))

    class _TextUpd:
        def __init__(self):
            self.effective_user = type("U", (), {"id": 1})()
            self.effective_chat = type("C", (), {"id": 99})()
            self.effective_message = _Msg()

    u = _TextUpd()
    c = _Ctx({"guide_msg_id": 555}, db_path=_db_path(tmp_path))
    c.bot = _Bot()
    assert asyncio.run(ob.guide_text(u, c)) == ConversationHandler.END
    assert calls == [(99, 555, None)]
    assert "guide_msg_id" not in c.user_data


def test_board_confirm_template_has_help_button(tmp_path):
    board = "2 ТА.\n- Е2МОМх5х5х80%\nприседание со штангой на спине\n"
    u = _Upd("bconf:ok")
    c = _Ctx({"board_text": board}, db_path=_db_path(tmp_path))
    assert asyncio.run(rw.board_confirm(u, c)) == rw.RESULT
    marked = [kb for _, kb in u.callback_query.message.replies if kb]
    assert marked and _flat(marked[0])[0].callback_data == "reshelp"


def test_add_result_template_has_help_button(tmp_path):
    u = _Upd("arc:y")
    board = "2 ТА.\n- Е2МОМх5х5х80%\nприседание со штангой на спине\n"
    c = _Ctx({"ar_prog": board, "ar_blocks_stored": None}, db_path=_db_path(tmp_path))
    assert asyncio.run(ar.confirm(u, c)) == ar.AR_RESULT
    marked = [kb for _, kb in u.callback_query.message.replies if kb]
    assert marked and _flat(marked[0])[0].callback_data == "reshelp"


def test_results_help_replies_guide_keeps_state(tmp_path):
    u = _Upd("reshelp")
    c = _Ctx(db_path=_db_path(tmp_path))
    assert asyncio.run(rw.results_help(u, c)) is None
    text, _ = u.callback_query.message.replies[0]
    assert text == i18n.t("onboarding.results_guide", "ru")


def test_onboarding_handler_has_guide_state():
    h = ob.handler()
    assert ob.GUIDE in h.states
