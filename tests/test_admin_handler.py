from __future__ import annotations

import asyncio

from tj import i18n, llm
from tjbot import db as botdb
from tjbot.handlers import admin


class _FakeUser:
    def __init__(self, uid):
        self.id = uid


class _FakeMsg:
    def __init__(self):
        self.replies: list[str] = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)


class _FakeUpdate:
    def __init__(self, uid):
        self.effective_user = _FakeUser(uid)
        self.effective_message = _FakeMsg()


class _FakeCtx:
    def __init__(self, db_path, review_running=False):
        self.bot_data = {"db_path": db_path, "review_running": review_running}


def _db_path(tmp_path) -> str:
    p = tmp_path / "t.db"
    con = botdb.connect(str(p))
    try:
        botdb.init_schema(con)
        con.commit()
    finally:
        con.close()
    return str(p)


def test_review_run_blocks_without_any_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(admin, "is_admin", lambda uid: True)
    monkeypatch.setattr(llm, "has_llm", lambda: False)
    upd = _FakeUpdate(1)
    ctx = _FakeCtx(_db_path(tmp_path))
    asyncio.run(admin.review_run(upd, ctx))
    assert upd.effective_message.replies == [i18n.t("admin.review_no_claude", "ru")]


def test_review_run_allows_gemini_only_admin(monkeypatch, tmp_path):
    # ключ Gemini есть, Claude выключен — раньше это блокировалось has_claude_vision()
    monkeypatch.setattr(admin, "is_admin", lambda uid: True)
    monkeypatch.setattr(llm, "has_llm", lambda: True)
    monkeypatch.setattr(llm, "has_claude_vision", lambda: False)
    upd = _FakeUpdate(1)
    ctx = _FakeCtx(_db_path(tmp_path), review_running=True)
    asyncio.run(admin.review_run(upd, ctx))
    assert upd.effective_message.replies == [i18n.t("admin.review_busy", "ru")]


def test_removable_excludes_admins():
    out = admin._removable({1, 2, 3}, {1}, {2: "Боб"})
    assert out == [("Боб (2)", 2), ("3", 3)]


def test_removable_empty():
    assert admin._removable({1}, {1}, {}) == []


def test_admin_kb_and_register():
    assert admin.admin_kb() is not None
    assert admin.BTN_ADD_USER == "➕ Добавить в бота"
    assert admin.BTN_DEL_USER == "➖ Удалить из бота"
    assert callable(admin.register)
