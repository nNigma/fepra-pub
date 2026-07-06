"""Поведенческие тесты гардов лимита ИИ в хендлерах бота (async напрямую)."""
from __future__ import annotations

import asyncio

import tjbot.vision as vision
from tjbot import db as botdb
from tjbot.handlers import competition
from tjbot.handlers import record_workout as rw


class FakePhoto:
    file_id = "f1"


class FakeMsg:
    def __init__(self, photo=False, text=None):
        self.photo = [FakePhoto()] if photo else None
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeUpdate:
    def __init__(self, uid, photo=False, text=None):
        self.effective_user = FakeUser(uid)
        self.message = FakeMsg(photo=photo, text=text)


def _db_path(tmp_path) -> str:
    p = tmp_path / "t.db"
    con = botdb.connect(str(p))
    try:
        botdb.init_schema(con)
        con.commit()
    finally:
        con.close()
    return str(p)


class FakeCtx:
    def __init__(self, user_data=None, db_path=":memory:"):
        self.user_data = user_data or {}
        self.bot_data = {"db_path": db_path}
        self.bot = None



def test_board_photo_blocked_when_quota_exhausted(monkeypatch, tmp_path):
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    called = {"parse": False}
    monkeypatch.setattr(vision, "parse_board",
                        lambda *a, **k: called.__setitem__("parse", True))
    monkeypatch.setattr(rw.access, "llm_quota_consume", lambda *a, **k: False)
    upd = FakeUpdate(1, photo=True)
    ctx = FakeCtx(db_path=_db_path(tmp_path))
    state = asyncio.run(rw.board(upd, ctx))
    assert state == rw.BOARD
    assert called["parse"] is False
    from tj import i18n
    assert any(i18n.t("record.llm_limit", "ru", limit=rw.access.LLM_DAILY_LIMIT) in r
               for r in upd.message.replies)
    assert ctx.user_data["board_text"] == "[фото доски — не распознано]"



def _run_board_text(monkeypatch, consume_result, tmp_path):
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    seen = {}
    monkeypatch.setattr(vision, "parse_text",
                        lambda text, use_llm=True: seen.update(use_llm=use_llm)
                        or {"raw_text": text, "format": "amrap"})
    monkeypatch.setattr(rw.access, "llm_quota_consume", lambda *a, **k: consume_result)
    upd = FakeUpdate(1, text="Fran 21-15-9")
    ctx = FakeCtx(db_path=_db_path(tmp_path))
    state = asyncio.run(rw.board(upd, ctx))
    assert state == rw.BOARD_CONFIRM
    return seen


def test_board_text_uses_llm_when_allowed(monkeypatch, tmp_path):
    assert _run_board_text(monkeypatch, consume_result=True, tmp_path=tmp_path)["use_llm"] is True


def test_board_text_falls_back_when_exhausted(monkeypatch, tmp_path):
    assert _run_board_text(monkeypatch, consume_result=False, tmp_path=tmp_path)["use_llm"] is False



def test_fill_stage_photo_blocked_when_exhausted(monkeypatch, tmp_path):
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    called = {"parse": False}
    monkeypatch.setattr(vision, "parse_stages",
                        lambda *a, **k: called.__setitem__("parse", True))
    monkeypatch.setattr(competition.access, "llm_quota_consume", lambda *a, **k: False)
    upd = FakeUpdate(1, photo=True)
    ctx = FakeCtx({"fill": {"div_id": 1, "eid": 1, "athlete": "X"}}, db_path=_db_path(tmp_path))
    state = asyncio.run(competition.fill_stage_photo(upd, ctx))
    assert state == competition.FILL_STAGE_TEXT
    assert called["parse"] is False
    from tj import i18n
    assert any(i18n.t("comp.llm_limit_stage", "ru", limit=competition.access.LLM_DAILY_LIMIT) in r
               for r in upd.message.replies)


def test_fill_result_photo_blocked_when_exhausted(monkeypatch, tmp_path):
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    called = {"parse": False}
    monkeypatch.setattr(vision, "parse_results",
                        lambda *a, **k: called.__setitem__("parse", True))
    monkeypatch.setattr(competition.access, "llm_quota_consume", lambda *a, **k: False)
    upd = FakeUpdate(1, photo=True)
    ctx = FakeCtx({"fill": {"div_id": 1, "eid": 1, "athlete": "X"}}, db_path=_db_path(tmp_path))
    state = asyncio.run(competition.fill_result_photo(upd, ctx))
    assert state == competition.FILL_RESULT_TEXT
    assert called["parse"] is False
    from tj import i18n
    assert any(i18n.t("comp.llm_limit_result", "ru", limit=competition.access.LLM_DAILY_LIMIT) in r
               for r in upd.message.replies)
