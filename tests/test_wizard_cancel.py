"""Единый выход из мастеров: /cancel + любая кнопка меню отменяют диалог."""
from __future__ import annotations

import asyncio

from telegram.ext import CommandHandler, ConversationHandler, MessageHandler

from tjbot import db as botdb
from tjbot.handlers import (admin, club, competition, edit_workout, garmin,
                            goal, menu, pro, program, record_result)
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


class FakeMsg:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, uid=1):
        self.effective_user = type("U", (), {"id": uid})()
        self.effective_message = FakeMsg()


class FakeCtx:
    def __init__(self, db_path=":memory:"):
        self.user_data = {"stale": 1}
        self.bot_data = {"db_path": db_path}


def test_menu_buttons_cover_main():
    for b in (menu.BTN_RECORD, menu.BTN_EDIT, menu.BTN_COMP, menu.BTN_ADMIN, menu.BTN_BACK,
              "Программа зала", "Тренировки", "Сводка", "Соревнования", "Цели", "Профиль"):
        assert b in menu.MENU_BUTTONS


def test_cancel_wizard_clears_state_and_ends(tmp_path):
    upd, ctx = FakeUpdate(), FakeCtx(db_path=_db_path(tmp_path))
    state = asyncio.run(menu.cancel_wizard(upd, ctx))
    assert state == ConversationHandler.END
    assert ctx.user_data == {}                      # состояние вычищено
    assert upd.effective_message.replies             # показал меню


def test_wizard_fallbacks_shape():
    fb = menu.wizard_fallbacks()
    assert sum(isinstance(h, CommandHandler) for h in fb) == 2      # /cancel + /start
    assert sum(isinstance(h, MessageHandler) for h in fb) == 1      # кнопки меню


def test_all_wizards_have_menu_cancel_fallback():
    convs = [rw.handler(), edit_workout.handler(), competition.handler(),
             club._view_conv(), club._add_conv(), admin._add_conv(),
             pro.handler(), goal.handler(), record_result.handler(), garmin.handler()]
    convs += [h for h in program.handlers() if isinstance(h, ConversationHandler)]
    for c in convs:
        assert any(isinstance(h, CommandHandler) for h in c.fallbacks)   # /cancel
        assert any(isinstance(h, MessageHandler) for h in c.fallbacks)   # выход по кнопке
