from __future__ import annotations

import asyncio


def test_bot_username_default():
    from tj import config
    assert config.bot_username({}) == "example_bot"


def test_bot_username_from_env(monkeypatch):
    from tj import config
    monkeypatch.setenv("BOT_USERNAME", "my_bot")
    assert config.bot_username({}) == "my_bot"


def test_api_goals_includes_bot_username(tmp_path, monkeypatch):
    from tjbot import db as botdb
    from tjapp import api
    p = str(tmp_path / "t.db")
    con = botdb.connect(p)
    botdb.init_schema(con)
    con.close()
    monkeypatch.setattr(api, "_db", lambda: p)
    data = asyncio.run(api.api_goals(user={"id": 1, "lang": "ru"}, as_user=None))
    assert data.get("bot_username") == "example_bot"
