#!/bin/bash
# DEV-стек отдельного dev-бота на ОТДЕЛЬНОМ токене (TG_FEPRA_DEV_BOT_TOKEN).
# Прод-бот живёт на сервере на своём токене - здесь его НЕ трогаем.
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH=src

export FEPRA_DB_PATH="$HOME/fepra-dev/training.dev.db"
mkdir -p "$(dirname "$FEPRA_DB_PATH")"
[ -f "$FEPRA_DB_PATH" ] || cp training.db "$FEPRA_DB_PATH"

export TG_FEPRA_BOT_TOKEN="$(.venv/bin/python -c "from tj import config as c; print(c.load_dotenv(c.default_env_path()).get('TG_FEPRA_DEV_BOT_TOKEN',''))")"
if [ -z "$TG_FEPRA_BOT_TOKEN" ]; then echo "НЕТ TG_FEPRA_DEV_BOT_TOKEN"; exit 1; fi

TJAPP_PORT=8010 .venv/bin/python -m tjapp.server > /tmp/fepra_dev_uvicorn.log 2>&1 &
UV=$!

cloudflared tunnel --url http://localhost:8010 > /tmp/fepra_dev_cf.log 2>&1 &
CF=$!
URL=""
for i in $(seq 1 30); do
  URL="$(grep -aoE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/fepra_dev_cf.log | head -1)"
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] && printf '%s' "$URL" > miniapp_url.txt

.venv/bin/python -m tjbot.main > /tmp/fepra_dev_bot.log 2>&1 &
BOT=$!

echo "dev stack up: app(uvicorn)=$UV cloudflared=$CF bot=$BOT url=$URL"
while kill -0 "$UV" 2>/dev/null && kill -0 "$CF" 2>/dev/null && kill -0 "$BOT" 2>/dev/null; do
  sleep 10
done
kill "$UV" "$CF" "$BOT" 2>/dev/null
exit 1
