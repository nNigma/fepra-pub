"""Точка входа бота (M1, слой ввода). Запуск:

    PYTHONPATH=src .venv/bin/python -m tjbot.main

Токен — TG_KUZ_BOT_TOKEN (в .env или окружении), берётся у @BotFather.
Доступ приватный: незнакомцу бот отдаёт его ID, владелец вписывает в users_allow.json.
"""
from __future__ import annotations

import os

from telegram.ext import Application

from tj import config as cfgmod
from . import db as botdb
from .handlers import (add_result, admin, bodyweight, club, coach, competition,
                       edit_workout, garmin as garmin_h, goal, meal, menu,
                       nutrition_profile, onboarding, pro, program, record_workout)
from .handlers import self_feel as self_feel_h


_TOKEN_KEYS = ("TG_KUZ_BOT_TOKEN", "TG_BOT_TOKEN")


def _token(env: dict) -> str:
    for k in _TOKEN_KEYS:
        tok = os.environ.get(k) or env.get(k)
        if tok:
            return tok
    raise SystemExit(
        "Нет токена (TG_KUZ_BOT_TOKEN в .env или окружении). Возьми у @BotFather."
    )


def build_application() -> Application:
    env = cfgmod.load_dotenv(cfgmod.default_env_path())
    try:
        tz = cfgmod.timezone(cfgmod.load_config())
    except FileNotFoundError:
        tz = "UTC"

    db_path = str(botdb.default_db_path())
    con = botdb.connect(db_path)
    botdb.init_schema(con)
    con.close()

    app = Application.builder().token(_token(env)).build()
    app.bot_data["db_path"] = db_path
    app.bot_data["tz"] = tz

    app.add_handler(onboarding.handler())
    app.add_handler(record_workout.handler())
    app.add_handler(add_result.handler())
    app.add_handler(bodyweight.handler())
    app.add_handler(edit_workout.handler())
    app.add_handler(goal.handler())
    app.add_handler(garmin_h.handler())
    competition.register(app)
    club.register(app)
    app.add_handler(pro.handler())
    admin.register(app)
    for h in program.handlers():
        app.add_handler(h)
    meal.register(app)      # до register_stubs: подменю Питания перекрывает заглушку
    coach.register(app)
    nutrition_profile.register(app)
    menu.register_stubs(app)
    self_feel_h.register(app)
    from .handlers import lift_disambig
    app.add_handler(lift_disambig.handler())
    return app


def main() -> None:
    app = build_application()
    print("Бот запущен (polling). Ctrl+C — выход.")
    app.run_polling()


if __name__ == "__main__":
    main()
