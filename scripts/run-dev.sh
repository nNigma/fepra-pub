#!/usr/bin/env bash
# Local dev stack: Mini App (uvicorn) + a temporary public HTTPS tunnel + the bot.
# Telegram serves a Mini App only over public HTTPS; cloudflared gives a free temp URL.
# For a permanent setup use your own domain + Caddy — see deploy/README.md.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${TJAPP_PORT:-8010}"
PY=.venv/bin/python

[ -x "$PY" ] || { echo "No venv. Run: make setup"; exit 1; }
[ -f .env ] || { echo "No .env. Copy .env.example to .env and fill it in."; exit 1; }
command -v cloudflared >/dev/null 2>&1 || {
  echo "cloudflared not found (macOS: brew install cloudflared)."
  echo "For a permanent domain instead of a temp tunnel, see deploy/README.md."
  exit 1
}

CFLOG="$(mktemp)"
cleanup() { kill "${APP_PID:-}" "${CF_PID:-}" 2>/dev/null || true; rm -f "$CFLOG"; }
trap cleanup EXIT

echo "Starting Mini App on :$PORT ..."
PYTHONPATH=src TJAPP_PORT="$PORT" "$PY" -m tjapp.server & APP_PID=$!

echo "Opening public tunnel ..."
cloudflared tunnel --url "http://localhost:$PORT" >"$CFLOG" 2>&1 & CF_PID=$!

URL=""
for _ in $(seq 1 30); do
  URL="$(grep -aoE 'https://[a-z0-9-]+\.trycloudflare\.com' "$CFLOG" | head -1 || true)"
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] || { echo "Could not read tunnel URL. cloudflared log:"; cat "$CFLOG"; exit 1; }

echo "$URL" > miniapp_url.txt
echo "Mini App public URL: $URL  (written to miniapp_url.txt, bot reads it live)"

echo "Starting bot — press Ctrl-C to stop everything ..."
PYTHONPATH=src "$PY" -m tjbot.main
