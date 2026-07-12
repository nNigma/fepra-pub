"""Поведенческие тесты гардов лимита ИИ в хендлерах бота (async напрямую)."""
from __future__ import annotations

import asyncio

import tjbot.vision as vision
from tjbot import db as botdb
from tjbot.handlers import club as club_h
from tjbot.handlers import competition
from tjbot.handlers import record_workout as rw


class FakePhoto:
    file_id = "f1"


class FakeMsg:
    def __init__(self, photo=False, text=None):
        self.photo = [FakePhoto()] if photo else None
        self.text = text
        self.replies: list[str] = []
        self.markups: list = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)
        self.markups.append(kw.get("reply_markup"))


def _kb_has(markup, data: str) -> bool:
    if markup is None:
        return False
    return any(b.callback_data == data
               for row in markup.inline_keyboard for b in row)


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


class FakeCbQuery:
    def __init__(self, data):
        self.data = data
        self.message = FakeMsg()
        self.edits: list[str] = []
        self.edit_markups: list = []

    async def answer(self, *a, **k):
        pass

    async def edit_message_text(self, text, **kw):
        self.edits.append(text)
        self.edit_markups.append(kw.get("reply_markup"))


class FakeCbUpdate:
    def __init__(self, uid, data):
        self.effective_user = FakeUser(uid)
        self.callback_query = FakeCbQuery(data)


# ---- record_workout: фото доски -> спрашиваем движок, лимит гардит в board_engine ----

def test_board_photo_asks_engine_then_quota_blocks(monkeypatch, tmp_path):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    monkeypatch.setattr(vision, "has_claude", lambda: True)
    called = {"parse": False}
    monkeypatch.setattr(vision, "parse_board",
                        lambda *a, **k: called.__setitem__("parse", True))
    ctx = FakeCtx(db_path=_db_path(tmp_path))
    # 1) фото -> бот спрашивает движок, без парса и без списания
    upd = FakeUpdate(1, photo=True)
    state = asyncio.run(rw.board(upd, ctx))
    assert state == rw.BOARD_ENGINE
    assert called["parse"] is False
    assert ctx.user_data["board_photo"] == "f1"
    # 2) выбор движка при исчерпанном лимите -> не распознано, ждём текст
    monkeypatch.setattr(rw.access, "llm_quota_consume", lambda *a, **k: False)
    cb = FakeCbUpdate(1, "beng:fast")
    state2 = asyncio.run(rw.board_engine(cb, ctx))
    assert state2 == rw.BOARD
    assert called["parse"] is False
    from tj import i18n
    limit_msg = i18n.t("record.llm_limit", "ru", limit=rw.access.LLM_DAILY_LIMIT)
    assert any(limit_msg in r for r in cb.callback_query.message.replies)
    assert ctx.user_data["board_text"] == "[фото доски — не распознано]"


class _FakeFile:
    async def download_as_bytearray(self):
        return bytearray(b"img")


class _FakeBot:
    async def get_file(self, file_id):
        return _FakeFile()


def _run_engine_choice(monkeypatch, tmp_path, cb_data):
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    monkeypatch.setattr(rw.access, "llm_quota_consume", lambda *a, **k: True)
    seen = {}
    monkeypatch.setattr(
        vision, "parse_board",
        lambda img, engine="gemini", **k: seen.update(engine=engine)
        or {"raw_text": "доска", "format": "amrap", "engine_used": engine})
    ctx = FakeCtx(db_path=_db_path(tmp_path))
    ctx.user_data["board_photo"] = "f1"
    ctx.bot = _FakeBot()
    cb = FakeCbUpdate(1, cb_data)
    state = asyncio.run(rw.board_engine(cb, ctx))
    return seen, state, ctx


def test_board_engine_fast_uses_gemini(monkeypatch, tmp_path):
    seen, state, ctx = _run_engine_choice(monkeypatch, tmp_path, "beng:fast")
    assert seen["engine"] == "gemini"
    assert state == rw.BOARD_CONFIRM
    assert ctx.user_data["board_text"] == "доска"


def test_board_engine_slow_uses_claude(monkeypatch, tmp_path):
    seen, state, ctx = _run_engine_choice(monkeypatch, tmp_path, "beng:slow")
    assert seen["engine"] == "claude"
    assert state == rw.BOARD_CONFIRM


def test_board_engine_failure_offers_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    monkeypatch.setattr(rw.access, "llm_quota_consume", lambda *a, **k: True)
    monkeypatch.setattr(vision, "parse_board", lambda *a, **k: None)  # не распознал
    ctx = FakeCtx(db_path=_db_path(tmp_path))
    ctx.user_data["board_photo"] = "f1"
    ctx.bot = _FakeBot()
    cb = FakeCbUpdate(1, "beng:fast")
    state = asyncio.run(rw.board_engine(cb, ctx))
    assert state == rw.BOARD
    assert any(_kb_has(m, "bretry") for m in cb.callback_query.message.markups)


def test_board_retry_reasks_engine(monkeypatch, tmp_path):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    monkeypatch.setattr(vision, "has_claude", lambda: True)
    ctx = FakeCtx(db_path=_db_path(tmp_path))
    ctx.user_data["board_photo"] = "f1"
    cb = FakeCbUpdate(1, "bretry")
    state = asyncio.run(rw.board_retry(cb, ctx))
    assert state == rw.BOARD_ENGINE
    assert any(_kb_has(m, "beng:fast") for m in cb.callback_query.edit_markups)


# ---- record_workout: текст доски, use_llm прокидывается из лимита ----

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
    assert state == rw.BOARD_CONFIRM                       # текст доски → подтверждение
    return seen


def test_board_text_uses_llm_when_allowed(monkeypatch, tmp_path):
    assert _run_board_text(monkeypatch, consume_result=True, tmp_path=tmp_path)["use_llm"] is True


def test_board_text_falls_back_when_exhausted(monkeypatch, tmp_path):
    assert _run_board_text(monkeypatch, consume_result=False, tmp_path=tmp_path)["use_llm"] is False


# ---- competition: фото этапов/протокола, лимит исчерпан -> текстовый фолбэк ----

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


# ---- club (Программа зала): выбор движка распознавания программы ----

def test_club_photo_asks_engine(monkeypatch, tmp_path):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    monkeypatch.setattr(vision, "has_claude", lambda: True)
    ctx = FakeCtx(db_path=_db_path(tmp_path))
    upd = FakeUpdate(1, photo=True)
    state = asyncio.run(club_h.add_input(upd, ctx))
    assert state == club_h.ADD_ENGINE
    assert ctx.user_data["club_photo"] == "f1"
    assert any(_kb_has(m, "ceng:fast") for m in upd.message.markups)


def test_club_add_engine_slow_uses_claude(monkeypatch, tmp_path):
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    seen = {}
    monkeypatch.setattr(
        vision, "parse_board",
        lambda img, engine="gemini", **k: seen.update(engine=engine)
        or {"raw_text": "2 сета: 10 приседаний с резиной", "engine_used": engine})
    ctx = FakeCtx(db_path=_db_path(tmp_path))
    ctx.user_data["club_photo"] = "f1"
    ctx.bot = _FakeBot()
    cb = FakeCbUpdate(1, "ceng:slow")
    state = asyncio.run(club_h.add_engine(cb, ctx))
    assert seen["engine"] == "claude"
    assert state == club_h.ADD_CONFIRM


def test_club_add_engine_failure_offers_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    monkeypatch.setattr(vision, "parse_board", lambda *a, **k: None)
    ctx = FakeCtx(db_path=_db_path(tmp_path))
    ctx.user_data["club_photo"] = "f1"
    ctx.bot = _FakeBot()
    cb = FakeCbUpdate(1, "ceng:fast")
    state = asyncio.run(club_h.add_engine(cb, ctx))
    assert state == club_h.ADD_INPUT
    assert any(_kb_has(m, "cretry") for m in cb.callback_query.message.markups)


def test_club_add_retry_reasks_engine(monkeypatch, tmp_path):
    monkeypatch.setenv("FEPRA_USE_CLAUDE", "1")
    monkeypatch.setattr(vision, "has_claude", lambda: True)
    ctx = FakeCtx(db_path=_db_path(tmp_path))
    ctx.user_data["club_photo"] = "f1"
    cb = FakeCbUpdate(1, "cretry")
    state = asyncio.run(club_h.add_retry(cb, ctx))
    assert state == club_h.ADD_ENGINE
    assert any(_kb_has(m, "ceng:fast") for m in cb.callback_query.edit_markups)
