"""Universe-ingestion: Telethon-userbot слушает тред тренера, ловит фото доски.

Креды: TG_API_ID / TG_API_HASH (.env, с my.telegram.org). Сессия -
файл tg_user.session. Тред: UNIVERSE_CHAT_ID + UNIVERSE_TOPIC_ID.

    PYTHONPATH=src .venv/bin/python -m tjbot.ingest_universe list           # список групп
    PYTHONPATH=src .venv/bin/python -m tjbot.ingest_universe list <chat_id> # темы группы
    PYTHONPATH=src .venv/bin/python -m tjbot.ingest_universe listen         # слушать

Новое фото -> vision.parse_board (или фолбэк) -> pending wod_program ->
уведомление в бот с кнопками Подтвердить/Поправить (их обрабатывает сам бот).
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import timezone
from pathlib import Path

from tj import config as cfgmod
from tj import i18n
from . import db as botdb
from . import vision

_SESSION = str(Path(__file__).resolve().parents[2] / "tg_user")


def _creds():
    env = cfgmod.load_dotenv(cfgmod.default_env_path())
    api_id = os.environ.get("TG_API_ID") or env.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH") or env.get("TG_API_HASH")
    if not api_id or not api_hash:
        raise SystemExit("Нет TG_API_ID / TG_API_HASH в .env (my.telegram.org).")
    return int(api_id), api_hash, env


def _bot_token(env):
    for k in ("TG_KUZ_BOT_TOKEN", "TG_BOT_TOKEN"):
        if t := (os.environ.get(k) or env.get(k)):
            return t
    return None


async def _list():
    from telethon import TelegramClient

    api_id, api_hash, _ = _creds()
    async with TelegramClient(_SESSION, api_id, api_hash) as client:
        print("=== Группы/каналы (id | название) ===")
        async for d in client.iter_dialogs():
            if d.is_group or d.is_channel:
                print(f"  {d.id:>16} | {d.name}")
        if len(sys.argv) > 2:
            cid = int(sys.argv[2])
            try:
                from telethon.tl.functions.channels import GetForumTopicsRequest
                res = await client(GetForumTopicsRequest(
                    channel=cid, offset_date=0, offset_id=0, offset_topic=0, limit=100))
                print(f"\n=== Темы в {cid} (topic_id | заголовок) ===")
                for t in res.topics:
                    print(f"  {t.id:>8} | {t.title}")
            except Exception as e:
                print(f"Темы не получил ({e}) — возможно, в группе нет топиков.")
        else:
            print("\nДальше: list <chat_id> покажет темы. Впиши UNIVERSE_CHAT_ID/_TOPIC_ID в .env.")


async def _notify(env, prog_id, day, raw_text, photo_path, admin_ids, db_path):
    token = _bot_token(env)
    if not token:
        print("Нет токена бота — уведомление пропущено.")
        return
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

    bot = Bot(token)
    con = botdb.connect(db_path)
    try:
        for uid in admin_ids:
            lang = botdb.user_lang(con, uid)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(i18n.t("universe.confirm_btn", lang), callback_data=f"prog:{prog_id}"),
                InlineKeyboardButton(i18n.t("universe.fix_btn", lang), callback_data=f"progedit:{prog_id}"),
            ]])
            cap = i18n.t("universe.board_caption", lang, day=day, text=raw_text[:900])
            try:
                with open(photo_path, "rb") as f:
                    await bot.send_photo(uid, f, caption=cap, reply_markup=kb)
            except Exception as e:
                print(f"notify {uid} fail: {e}")
    finally:
        con.close()


async def _listen():
    from telethon import TelegramClient, events

    api_id, api_hash, env = _creds()
    chat_id = int(os.environ.get("UNIVERSE_CHAT_ID") or env.get("UNIVERSE_CHAT_ID", "0"))
    topic_id = int(os.environ.get("UNIVERSE_TOPIC_ID") or env.get("UNIVERSE_TOPIC_ID", "0"))
    if not chat_id:
        raise SystemExit("Нет UNIVERSE_CHAT_ID — запусти `ingest_universe list` и впиши в .env.")

    from .access import load_allow
    admin_ids = sorted(load_allow())
    db_path = str(botdb.default_db_path())
    data_dir = Path(__file__).resolve().parents[2] / "raw" / "universe"
    data_dir.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(_SESSION, api_id, api_hash)

    @client.on(events.NewMessage(chats=chat_id))
    async def handler(event):
        if not event.photo:
            return
        if topic_id and (rt := getattr(event.message, "reply_to", None)):
            tid = getattr(rt, "reply_to_top_id", None) or getattr(rt, "reply_to_msg_id", None)
            if tid != topic_id:
                return
        day = event.message.date.astimezone(timezone.utc).date().isoformat()
        path = await event.download_media(file=str(data_dir / f"{day}-{event.id}.jpg"))
        draft = vision.parse_board(Path(path).read_bytes()) if vision.has_vision() else None
        raw = draft["raw_text"] if draft else "[фото доски — впиши текст через 'Поправить']"
        fmt = draft.get("format", "other") if draft else "other"
        movements = draft.get("movements", []) if draft else []
        con = botdb.connect(db_path)
        pid = botdb.add_program(con, day, "Universe", raw, fmt=fmt,
                                movements=movements, source="photo", confirmed=0)
        con.close()
        await _notify(env, pid, day, raw, path, admin_ids, db_path)
        print(f"доска {day} -> pending wod_program #{pid}")

    print("Userbot слушает тред тренера. Ctrl+C — выход.")
    async with client:
        await client.run_until_disconnected()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "listen"
    asyncio.run(_list() if mode == "list" else _listen())


if __name__ == "__main__":
    main()
