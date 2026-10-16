"""Крон-обёртка плановых push-уведомлений (сервер). Раз в час:

    5 * * * *  cd /opt/fepra && PYTHONPATH=src .venv/bin/python server_notify.py \
               >> /var/log/fepra_notify.log 2>&1

Сейчас: «программа на сегодня» (раз в день на пользователя, только с активной
push-подпиской и запланированной сессией; до FEPRA_NOTIFY_FROM_HOUR, по умолчанию 7,
по локальному времени не шлём). Нет VAPID-ключей — уведомление остаётся баннером.
"""
import json
from datetime import datetime, timezone

from tj import config as cfgmod
from tj.services import push
from tjbot import db

try:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(cfgmod.timezone(cfgmod.load_config()))
except Exception:
    tz = timezone.utc

now = datetime.now(tz)
con = db.connect(db.default_db_path())
db.init_schema(con)
try:
    import os
    res = push.run_daily(con, now.date().isoformat(), now.hour,
                         from_hour=int(os.environ.get("FEPRA_NOTIFY_FROM_HOUR", "7")))
finally:
    con.close()
print(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"), json.dumps(res, ensure_ascii=False))
