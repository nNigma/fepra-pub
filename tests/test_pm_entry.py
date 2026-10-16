from __future__ import annotations

import asyncio


class Msg:
    def __init__(self):
        self.texts = []
        self.markups = []

    async def reply_text(self, t, **kw):
        self.texts.append(t)
        self.markups.append(kw.get("reply_markup"))


def test_send_kind_prompt_shows_two_kinds():
    from tjbot.handlers.record_result import send_kind_prompt
    m = Msg()
    asyncio.run(send_kind_prompt(m, "ru"))
    assert m.texts, "должен быть текст вопроса вида"
    kb = m.markups[0]
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert datas == ["k:lift", "k:benchmark"]


class Upd:
    def __init__(self, uid=1):
        self.effective_user = type("U", (), {"id": uid})()
        self.effective_message = Msg()


class Ctx:
    def __init__(self, db_path, args=None):
        self.user_data = {}
        self.bot_data = {"db_path": db_path}
        self.args = args or []


def test_start_pm_onboarded_sends_kind_prompt(tmp_path, monkeypatch):
    from tjbot import db as botdb
    from tjbot.handlers import onboarding
    from tj import i18n
    monkeypatch.setattr(onboarding, "is_allowed", lambda uid: True)
    p = str(tmp_path / "t.db")
    con = botdb.connect(p)
    botdb.init_schema(con)
    botdb.save_user(con, 1, nick="a", height_cm=180, weight_kg=80, sex="m", age=30, gym="solo")
    con.close()
    upd, ctx = Upd(uid=1), Ctx(p, args=["pm"])
    asyncio.run(onboarding.start(upd, ctx))
    assert i18n.t("recresult.ask_kind", "ru") in upd.effective_message.texts


def test_start_plain_onboarded_shows_menu(tmp_path, monkeypatch):
    from tjbot import db as botdb
    from tjbot.handlers import onboarding
    from tj import i18n
    monkeypatch.setattr(onboarding, "is_allowed", lambda uid: True)
    p = str(tmp_path / "t.db")
    con = botdb.connect(p)
    botdb.init_schema(con)
    botdb.save_user(con, 1, nick="a", height_cm=180, weight_kg=80, sex="m", age=30, gym="solo")
    con.close()
    upd, ctx = Upd(uid=1), Ctx(p, args=[])
    asyncio.run(onboarding.start(upd, ctx))
    assert i18n.t("recresult.ask_kind", "ru") not in upd.effective_message.texts


def test_record_result_handler_registered_in_main():
    import inspect
    from tjbot import main
    src = inspect.getsource(main.build_application)
    assert "record_result.handler()" in src


def test_record_result_handler_builds():
    from tjbot.handlers import record_result
    h = record_result.handler()
    assert h is not None
