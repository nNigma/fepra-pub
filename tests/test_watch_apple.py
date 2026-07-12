from __future__ import annotations

import asyncio

from tjbot import db as botdb
from tjbot.handlers import watch


class _FakeMsg:
    def __init__(self):
        self.texts = []

    async def reply_text(self, text, **kw):
        self.texts.append(text)


class _FakeQuery:
    def __init__(self, uid):
        self.from_user = type("U", (), {"id": uid})()
        self.answers = []

    async def answer(self, *a, **k):
        self.answers.append(a[0] if a else None)


class _FakeUpdate:
    def __init__(self, msg, q):
        self.callback_query = q
        self.effective_message = msg


class _FakeCtx:
    def __init__(self, db_path):
        self.bot_data = {"db_path": db_path}


def _fresh_db(tmp_path):
    p = tmp_path / "t.db"
    con = botdb.connect(p)
    botdb.init_schema(con)
    con.close()
    return str(p)


def test_apple_connect_issues_token_and_sends_msg(tmp_path, monkeypatch):
    from tjbot import access
    monkeypatch.setattr(access, "is_allowed", lambda tg_id, path=None: True)
    p = _fresh_db(tmp_path)
    msg = _FakeMsg()
    q = _FakeQuery(1)
    asyncio.run(watch.apple_connect_cb.__wrapped__(_FakeUpdate(msg, q), _FakeCtx(p)))

    con = botdb.connect(p)
    acc = botdb.watch_account_get(con, 1, "apple")
    assert acc["status"] == "pending"
    assert msg.texts
    text = msg.texts[0]
    assert watch.apple_ingest_url() in text
    assert "Bearer" in text


def test_apple_disconnect_sets_revoked(tmp_path, monkeypatch):
    from tjbot import access
    monkeypatch.setattr(access, "is_allowed", lambda tg_id, path=None: True)
    p = _fresh_db(tmp_path)
    con = botdb.connect(p)
    botdb.issue_watch_token(con, 1, "apple")
    con.close()
    msg = _FakeMsg()
    q = _FakeQuery(1)
    asyncio.run(watch.apple_disconnect_cb.__wrapped__(_FakeUpdate(msg, q), _FakeCtx(p)))

    con = botdb.connect(p)
    acc = botdb.watch_account_get(con, 1, "apple")
    assert acc["status"] == "revoked"


def test_profile_kb_apple_gating():
    from tjbot.handlers.menu import _profile_kb

    def flat(kb):
        return [b.callback_data for row in kb.inline_keyboard for b in row]

    kb = _profile_kb("ru", has_acc=False, astro=False)
    b = flat(kb)
    assert "wconnect:apple" in b
    assert "wconnect:samsung" in b
    assert "wconnect:whoop" in b
    assert "gconnect" in b

    kb = _profile_kb("ru", has_acc=False, astro=False, apple_connected=True)
    b = flat(kb)
    assert "wdisc:apple" in b
    assert "wconnect:samsung" not in b and "wconnect:whoop" not in b and "gconnect" not in b

    kb = _profile_kb("ru", has_acc=False, astro=False, sam_connected=True)
    assert "wconnect:apple" not in flat(kb)

    kb = _profile_kb("ru", has_acc=True, astro=False)
    assert "wconnect:apple" not in flat(kb)
