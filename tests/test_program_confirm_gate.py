from __future__ import annotations

import asyncio

from tjbot import db as botdb
from tjbot.handlers import program


class _Q:
    def __init__(self, uid, data):
        self.from_user = type("U", (), {"id": uid})()
        self.data = data
        self.captions = []

    async def answer(self, *a, **kw):
        pass

    async def edit_message_caption(self, caption, **kw):
        self.captions.append(caption)


class _Upd:
    def __init__(self, uid, data):
        self.callback_query = _Q(uid, data)


class _Ctx:
    def __init__(self, db_path):
        self.user_data = {"lang": "ru"}
        self.bot_data = {"db_path": db_path}


def _db(tmp_path):
    p = str(tmp_path / "t.db")
    con = botdb.connect(p)
    botdb.init_schema(con)
    pid = botdb.add_program(con, "2026-09-28", "Universe", "рывок 5x1", "other", [], "universe", 0)
    con.close()
    return p, pid


def _confirmed(p, pid):
    con = botdb.connect(p)
    try:
        return botdb.get_program_by_id(con, pid)["confirmed"]
    finally:
        con.close()


def test_confirm_program_rejected_for_plain_user(tmp_path, monkeypatch):
    p, pid = _db(tmp_path)
    monkeypatch.setattr(program, "is_admin", lambda uid: False)
    monkeypatch.setattr(program, "is_coach", lambda uid: False)
    upd = _Upd(5, f"prog:{pid}")
    asyncio.run(program.confirm(upd, _Ctx(p)))
    assert not _confirmed(p, pid)
    assert upd.callback_query.captions == []


def test_confirm_program_allowed_for_admin(tmp_path, monkeypatch):
    p, pid = _db(tmp_path)
    monkeypatch.setattr(program, "is_admin", lambda uid: True)
    monkeypatch.setattr(program, "is_coach", lambda uid: False)
    upd = _Upd(1, f"prog:{pid}")
    asyncio.run(program.confirm(upd, _Ctx(p)))
    assert _confirmed(p, pid)
