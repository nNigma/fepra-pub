"""Крон-обёртка авторазборов Месье Клода (сервер). Запускать ПОСЛЕ server_sync.py.
У крона/SSH нет ~/.local/bin в PATH (у бота это drop-in claude.conf) —
поэтому CLAUDE_BIN обязателен:

    0 9,20 * * *  cd /opt/fepra && PYTHONPATH=src .venv/bin/python server_sync.py \
                  >> /var/log/fepra_sync.log 2>&1 && CLAUDE_BIN=$HOME/.local/bin/claude \
                  PYTHONPATH=src .venv/bin/python server_review.py \
                  >> /var/log/fepra_review.log 2>&1

Вся логика — в tjbot.claude_review (по всем Pro: поденные разборы + сводка + совет).
"""
import datetime
import json

from tjbot import claude_review

out = claude_review.run_all()
print(datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
      json.dumps(out, ensure_ascii=False), flush=True)
claude_review.notify_admins(out)
