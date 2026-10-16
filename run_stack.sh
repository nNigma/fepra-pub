#!/bin/bash
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH=src

export TG_FEPRA_BOT_TOKEN="$(.venv/bin/python -c "from tj import config as c; print(c.load_dotenv(c.default_env_path()).get('TG_FEPRA_BOT_TOKEN',''))")"

TJAPP_PORT=8010 .venv/bin/python -m tjapp.server > /tmp/fepra_uvicorn.log 2>&1 &
UV=$!

cloudflared tunnel --url http://localhost:8010 > /tmp/fepra_cf.log 2>&1 &
CF=$!
URL=""
for i in $(seq 1 30); do
  URL="$(grep -aoE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/fepra_cf.log | head -1)"
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] && printf '%s' "$URL" > miniapp_url.txt

.venv/bin/python -m tjbot.main > /tmp/fepra_bot.log 2>&1 &
BOT=$!

while kill -0 "$UV" 2>/dev/null && kill -0 "$CF" 2>/dev/null && kill -0 "$BOT" 2>/dev/null; do
  sleep 10
done
kill "$UV" "$CF" "$BOT" 2>/dev/null
exit 1
