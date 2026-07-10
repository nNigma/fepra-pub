"""Профиль: выбор цели питания и города."""
from __future__ import annotations

import asyncio

from telegram.ext import ConversationHandler

from tjbot import db
from tjbot.handlers import nutrition_profile as np


class Msg:
    def __init__(self, text=""):
        self.text = text
        self.texts = []

    async def reply_text(self, t, **kw):
        self.texts.append(t)


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
        self.bot_data = {"db_path": db_path}


def _setup(tmp_path):
    p = str(tmp_path / "t.db")
    con = db.connect(p)
    db.init_schema(con)
    con.execute("INSERT INTO users (tg_id, nick) VALUES (1, 'x')")
    con.commit()
    return p, con


def test_goal_kb_marks_current():
    kb = np.goal_kb("recomp", "ru")
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Рекомп" in t and "✓" in t for t in texts)
    assert sum("✓" in t for t in texts) == 1


def test_goal_kb_callback_data():
    kb = np.goal_kb("maintain", "ru")
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert set(datas) == {"ngoal:cut", "ngoal:maintain", "ngoal:bulk", "ngoal:recomp"}


def test_goal_pick_writes_goal(tmp_path, monkeypatch):
    from tjbot import access
    monkeypatch.setattr(access, "is_allowed", lambda tg_id, path=None: True)
    p, con = _setup(tmp_path)
    q = Q("ngoal:recomp")
    asyncio.run(np.goal_pick(Upd(q=q), Ctx(p)))
    assert db.user_goal(con, 1) == "recomp"
    assert q.edited and "Рекомп" in q.edited[0]


def test_city_save_writes_city(tmp_path):
    p, con = _setup(tmp_path)
    upd = Upd(text="Казань")
    state = asyncio.run(np.city_save(upd, Ctx(p)))
    assert state == ConversationHandler.END
    assert db.user_city(con, 1) == "Казань"
    assert upd.message.texts and "Казань" in upd.message.texts[0]


def test_city_save_empty_stays(tmp_path):
    p, con = _setup(tmp_path)
    state = asyncio.run(np.city_save(Upd(text="   "), Ctx(p)))
    assert state == np.C_CITY
    assert db.user_city(con, 1) == "Москва"
