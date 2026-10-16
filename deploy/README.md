# Deploy

FePra runs as two long-lived processes — the Telegram bot (polling) and the
FastAPI Mini App (uvicorn) — behind a reverse proxy that terminates HTTPS.

> Important: the Gemini API is blocked from some regions (RU among them).
> Host the server where Gemini is reachable, or the AI features will fail.

## 1. Server

A small VPS is enough (1 vCPU / ~1 GB RAM + swap). Tested on Ubuntu.
Open ports 22, 80, 443.

## 2. Install

```bash
# uv (Python package/venv manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone <your-fork-url> /opt/fepra
cd /opt/fepra
uv venv --python 3.12
uv pip install -e '.[bot]'          # Gemini-only (default)
# uv pip install -e '.[bot,claude]' # only if you set use_claude = true with an API key
```

## 3. Configure

```bash
cp .env.example .env
# fill in TG_FEPRA_BOT_TOKEN, OWNER_TG_ID, GEMINI_API_KEY, FEPRA_PUBLIC_URL, MINIAPP_URL, ... (see .env.example)
# Web Push keys for the PWA:
PYTHONPATH=src .venv/bin/python -m tj.services.push_cli gen-keys >> .env
```

`FEPRA_PUBLIC_URL` is the permanent public HTTPS origin: invite links and watch
callbacks are built from it, and it is the passkey relying party — changing it
later invalidates registered passkeys.

`config.toml [llm].use_claude` defaults to `false` (Gemini-only) — leave it as is
unless you want Claude-first with an API key or a logged-in CLI (see main README).

Garmin token: the first sync logs in with `GARMIN_EMAIL`/`GARMIN_PASSWORD`
(MFA handled once) and caches an OAuth token under `GARMIN_TOKENSTORE`
(`~/.garminconnect` by default), so later runs don't re-login.

## 4. Reverse proxy + HTTPS (Caddy)

Point a domain at the server, then:

```bash
cp deploy/Caddyfile /etc/caddy/Caddyfile   # edit the domain first
systemctl reload caddy
```

Caddy fetches a Let's Encrypt certificate automatically and proxies to
`localhost:8010`. No public IP (home server behind NAT)? Use a tunnel instead,
e.g. Tailscale Funnel or a named Cloudflare Tunnel pointing at `localhost:8010`.

## 4b. PWA build (beta)

```bash
cd web && npm ci && npm run build   # → src/tjapp/static/app/, served under /app/
cd .. && PYTHONPATH=src .venv/bin/python -m tj.services.auth_cli invite --admin
```

Open the printed invite link, pick a nick and register a passkey.

## 5. Services

```bash
cp deploy/fepra-bot.service /etc/systemd/system/
cp deploy/fepra-app.service /etc/systemd/system/
# edit WorkingDirectory / paths / MINIAPP_URL in both, then:
systemctl daemon-reload
systemctl enable --now fepra-bot fepra-app
```

Logs: `journalctl -u fepra-bot -f` (or `fepra-app`).

Cron (watch sync → AI reviews, hourly Web Push):

```cron
0 9,20 * * *  cd /opt/fepra && PYTHONPATH=src .venv/bin/python server_sync.py >> /var/log/fepra_sync.log 2>&1 && PYTHONPATH=src .venv/bin/python server_review.py >> /var/log/fepra_review.log 2>&1
5 * * * *     cd /opt/fepra && PYTHONPATH=src .venv/bin/python server_notify.py >> /var/log/fepra_notify.log 2>&1
```

## 6. Updating

Pull new code and restart — runtime data (`training.db`, `.env`, tokens) is
never touched by a code update:

```bash
cd /opt/fepra && git pull
(cd web && npm ci && npm run build)
systemctl restart fepra-bot fepra-app
```

After changing `tjapp/static/*`, bump the `?v=` query on `app.js` in
`index.html` (Telegram caches the web view aggressively).
