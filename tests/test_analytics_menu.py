from __future__ import annotations

import asyncio


class Msg:
    def __init__(self):
        self.texts = []
        self.markups = []

    async def reply_text(self, t, **kw):
        self.texts.append(t)
        self.markups.append(kw.get("reply_markup"))


class Upd:
    def __init__(self, uid=1):
        self.effective_user = type("U", (), {"id": uid})()
        self.effective_message = Msg()


class Ctx:
    def __init__(self, db_path):
        self.user_data = {}
        self.bot_data = {"db_path": db_path}


def _setup(tmp_path, monkeypatch):
    from tjbot import access
    from tjbot import db as botdb
    monkeypatch.setattr(access, "is_allowed", lambda uid: True)
    p = str(tmp_path / "t.db")
    con = botdb.connect(p)
    botdb.init_schema(con)
    botdb.save_user(con, 1, nick="a", height_cm=180, weight_kg=80, sex="m", age=30, gym="solo")
    con.close()
    return Upd(uid=1), Ctx(p)


def test_analytics_opens_miniapp_directly(tmp_path, monkeypatch):
    from tj import i18n
    from tjbot.handlers import menu
    monkeypatch.setattr(menu, "miniapp_url", lambda: "https://fepra.example")
    upd, ctx = _setup(tmp_path, monkeypatch)
    asyncio.run(menu.open_analytics(upd, ctx))
    m = upd.effective_message
    assert m.texts == [i18n.t("menu.analytics_intro", "ru")]
    btn = m.markups[0].inline_keyboard[0][0]
    assert btn.text == i18n.t("app.open_analytics_btn", "ru")
    assert btn.web_app.url.startswith("https://fepra.example/?view=summary")


def test_analytics_without_url_says_not_running(tmp_path, monkeypatch):
    from tj import i18n
    from tjbot.handlers import menu
    monkeypatch.setattr(menu, "miniapp_url", lambda: None)
    upd, ctx = _setup(tmp_path, monkeypatch)
    asyncio.run(menu.open_analytics(upd, ctx))
    assert upd.effective_message.texts == [i18n.t("app.not_running", "ru")]


def test_analytics_submenu_gone():
    from tjbot.handlers import menu
    assert not hasattr(menu, "analytics_kb")


def test_goal_and_feel_in_main_menu():
    from tj import i18n
    from tjbot.handlers.menu import main_kb
    texts = [b.text for row in main_kb(12345678, "ru").keyboard for b in row]
    for t in (i18n.t("btn.goal_single", "ru"), i18n.t("btn.feel", "ru")):
        assert t in texts, t
