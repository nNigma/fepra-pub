# Deploy

Kuznitsa runs as two long-lived processes — the Telegram bot (polling) and the
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

git clone <your-fork-url> /opt/kuznitsa
cd /opt/kuznitsa
uv venv --python 3.12
uv pip install -e '.[bot]'          # Gemini-only (default)
# uv pip install -e '.[bot,claude]' # only if you set use_claude = true with an API key
```

## 3. Configure

```bash
cp .env.example .env
# fill in TG_KUZ_BOT_TOKEN, OWNER_TG_ID, GEMINI_API_KEY, MINIAPP_URL, ... (see .env.example)
```

`config.toml [llm].use_claude` defaults to `false` (Gemini-only) — leave it as is
unless you want Claude-first with an API key or a logged-in CLI (see main README).

Garmin token: the first sync logs in with `GARMIN_EMAIL`/`GARMIN_PASSWORD`
(MFA handled once) and caches an OAuth token under `GARMIN_TOKENSTORE`
(`~/.garminconnect` by default), so later runs don't re-login.

## 4. Reverse proxy + HTTPS (Caddy)

Point a domain at the server (a free DuckDNS subdomain works), then:

```bash
cp deploy/Caddyfile /etc/caddy/Caddyfile   # edit the domain first
systemctl reload caddy
```

Caddy fetches a Let's Encrypt certificate automatically and proxies to
`localhost:8010`.

## 5. Services

```bash
cp deploy/kuznitsa-bot.service /etc/systemd/system/
cp deploy/kuznitsa-app.service /etc/systemd/system/
# edit WorkingDirectory / paths / MINIAPP_URL in both, then:
systemctl daemon-reload
systemctl enable --now kuznitsa-bot kuznitsa-app
```

Logs: `journalctl -u kuznitsa-bot -f` (or `kuznitsa-app`).

## 6. Updating

Pull new code and restart — runtime data (`training.db`, `.env`, tokens) is
never touched by a code update:

```bash
cd /opt/kuznitsa && git pull
systemctl restart kuznitsa-bot kuznitsa-app
```

After changing `tjapp/static/*`, bump the `?v=` query on `app.js` in
`index.html` (Telegram caches the web view aggressively).
