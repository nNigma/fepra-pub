"""Крон-обёртка Garmin-синка (сервер). Запускать ПЕРЕД server_review.py:

    0 9,20 * * *  cd /opt/fepra && PYTHONPATH=src .venv/bin/python server_sync.py \
                  >> /var/log/fepra_sync.log 2>&1 && …

Между пользователями пауза 20–60 с (FEPRA_SYNC_PAUSE_MIN/MAX), backoff при 429.
Падение по одному аккаунту не роняет прогон — ошибка уезжает в лог. Разбор
последствий (статус аккаунта, алерт админам после двух неудач подряд) живёт
в tjbot.garmin_alerts, чтобы падение не оставалось только строкой в логе.
"""
import json
from datetime import datetime, timezone

from tjbot import db, garmin_alerts, garmin_sync
from tjbot.db import OWNER_ID

con = db.connect(db.default_db_path())
db.init_schema(con)
rows = con.execute('SELECT "tg_id","email","status" FROM garmin_accounts ORDER BY "tg_id"').fetchall()
con.close()

accounts = [(r["tg_id"], r["email"], r["status"]) for r in rows]
ids = {a[0] for a in accounts}
if OWNER_ID and OWNER_ID not in ids:
    accounts.append((OWNER_ID, "(owner-legacy)", "ok"))

out = garmin_sync.sync_all(db.default_db_path(), accounts, log=lambda m: print(m, flush=True))

try:
    alerts = garmin_alerts.apply(db.default_db_path(), out)
except Exception as e:                       # алерт — не повод ронять синк
    alerts = {"error": type(e).__name__}

stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
print(stamp, json.dumps(out, ensure_ascii=False), json.dumps(alerts, ensure_ascii=False))
