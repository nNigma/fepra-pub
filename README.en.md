# FePra

[Русский](./README.md) · **English**

A personal training service: **a Telegram bot for input + a Mini App for analytics**,
plus a standalone **PWA (beta)** web app with invite-based sign-up and passkeys.
The main sport is CrossFit, plus running / cycling (biometrics from Garmin, Samsung,
Whoop or Apple Watch). The analysis is there to drive decisions: load (ACWR/TRIMP),
readiness, level progression, nutrition, AI workout reviews.

> Architecture and design decisions are in [`SPEC.md`](./SPEC.md) (Russian).

## Features

- **Logging a workout in the bot.** A photo of the WOD board or plain text → recognition
  (Gemini vision + a movement ontology) → an auto-generated results template for the WOD
  format → parsing: strength maxes feed into levels, metcons (time/rounds/score) go to
  the summary.
- **Goals and levels.** A catalog of disciplines (lifts + Girls/Hero benchmarks) with
  standards as bodyweight multiples (Strength Level scale), an overall athlete level and
  progress to the next tier. Recognizes variants (squat/power snatch, clean from the
  floor/hang) and asks in the bot when it's ambiguous.
- **Gym programming.** A shared daily board for the gym (Universe): an admin posts it,
  members see it when logging; exercises are standardized through the ontology.
- **Competitions.** Event card, stages, placings, percentiles, an ability radar, trends,
  "what it's worth in points".
- **Gym leaderboard**, **wellness check-in** (without a watch, readiness comes from
  self-assessment).
- **AI reviews.** A quick Gemini review on tap + an in-depth "🎩 Review by Monsieur
  Claude" (written by an agent skill). Coach-style text: how you approached it, how it
  went, a breakdown of the work, advice. Plus an optional tongue-in-cheek
  "🔮 Astro review".
- **Nutrition.** A food photo or a text description → macros + micronutrients + a
  quality score; a daily summary with an eaten/left/burned ring, targets for your goal
  (cut/bulk/recomp), water adjusted for sweat loss, AI review of the day and week.
- **AI coach.** Ask the coach questions and get answers grounded in your data (profile,
  sport mix, nutrition, recent workouts).
- **Muscle map.** Front/back silhouettes highlighting the groups loaded by a workout's
  tonnage + a weekly map with chips for undertrained groups.
- **Watches.** Garmin (password + MFA via the bot, pull sync), Samsung (Health Connect
  via the Android companion `android/fepra-connect`), Whoop (OAuth + sync),
  Apple Watch (Health Auto Export → webhook). One provider per user; without a watch,
  readiness is based on self-assessment.
- **Programs.** A program catalog and two templates based on the Bulgarian system:
  weights are computed from your maxes, with a starting level and a test session, and an
  "on the platform" screen with a rest timer and set logging.
- **Gyms and roles.** Multiple gyms, each with its own daily program and leaderboard;
  roles admin / gym coach / Pro / athlete are stored in the DB.
- **Multi-user** (coach mode: the admin sees everyone, view-only), **RU/EN locales**.

## PWA (beta)

Telegram is no longer required: `web/` is a Vite + TypeScript + React web app that
installs on a phone as a PWA and talks to the same backend over REST.

- Sign-in: invite link from the admin → nickname → passkey (Face ID / fingerprint),
  server-side sessions.
- Screens: overview, workouts and logging (board photo / text → parsing → form),
  nutrition, goals and 1RMs, competitions, leaderboard, programs, coach, gym, admin,
  Garmin connection.
- Web Push: reminders and notifications (VAPID keys in `.env`).
- Domain logic lives in `tj/services/*` and is shared by the bot and REST
  (`tjapp/routes/*`); long-running tasks (recognition, reviews) go through a `jobs`
  queue with polling.

**Status: beta.** The bot is still the main client and runs on the same DB; moving all
flows to the PWA and retiring the bot is not finished yet. The API contract and
per-phase notes are in [`docs/pwa/`](./docs/pwa/) (Russian).

## Stack and layout

The source of truth is **SQLite `training.db`** (not plaintext). Three packages:

```
src/
├── tj/                     # core: analysis, ontology, standards, LLM client, i18n
│   ├── analysis/           #   TRIMP/ACWR, levels, summary, competitions, WOD notation,
│   │                       #   result parsing, narrative, leaderboard, gym stats
│   ├── data/               #   standards.json (standards), benchmarks.json (Girls/Hero WODs)
│   ├── ontology.py         #   RU/EN movements → canonical (+ variant markers)
│   ├── services/           #   domain services (shared by bot and REST): workouts,
│   │                       #   nutrition, goals, programs, gyms, auth, push, jobs
│   ├── migrations/         #   schema migrations (tracked in schema_migrations)
│   ├── llm.py  i18n.py     #   Gemini client (+ optional Claude); RU/EN strings
│   ├── models.py config.py #   canonical schema; config.toml + .env
│   └── cli.py + adapters/ vault/ store/   # legacy Obsidian/Garmin layer (see below)
├── tjbot/                  # Telegram bot (INPUT layer)
│   ├── db.py               #   training.db: schema, CRUD, standards seeding
│   ├── handlers/           #   onboarding, logging/editing workouts, gym program,
│   │                       #   competitions, goals, nutrition, wellness, profile,
│   │                       #   admin, garmin, watch (Samsung/Apple), whoop
│   ├── vision.py           #   recognition of board/result/food photos
│   └── garmin_sync.py whoop_sync.py garmin_connect.py   # per-user sync + MFA bridge
└── tjapp/                  # FastAPI Mini App (REPORTING layer)
    ├── api.py auth.py      #   Mini App REST + Telegram initData validation
    ├── routes/ deps.py     #   REST for the PWA (auto-discovered routers), sessions/roles
    ├── ingest.py whoop_oauth.py   # Samsung/Apple receivers + Whoop OAuth callback
    └── static/             #   Mini App (index.html, app.js, …); app/ is the PWA build
web/                        # PWA: Vite + TS + React (build → src/tjapp/static/app/)
```

Plus `android/fepra-connect/`, an Android companion for Samsung: it reads Health Connect
and pushes data to the server (build with `android/fepra-connect/build.sh`).

## Quick start (local)

Telegram opens a Mini App only from a public HTTPS URL. Locally you get one for free
with a temporary **cloudflared** tunnel; the launcher sets everything up and fills in
the URL.

```bash
cp .env.example .env    # fill in TG_FEPRA_BOT_TOKEN, OWNER_TG_ID, GEMINI_API_KEY (hints inside)
make setup              # venv (Python 3.12) + dependencies via uv
make run                # Mini App + tunnel + bot, one command
```

`make run` starts uvicorn, launches cloudflared, writes the fresh public URL to
`miniapp_url.txt` (the bot reads it on the fly) and starts the bot. You need
`cloudflared` installed (macOS: `brew install cloudflared`). Tests: `make test`.

The PWA is built from `web/` (Node 20+); the build is an artifact and isn't stored in git:

```bash
make web                # cd web && npm ci && npm run build → src/tjapp/static/app/
PYTHONPATH=src .venv/bin/python -m tj.services.auth_cli invite --admin   # first invite link
```

Frontend development with hot reload: [`docs/pwa/web.md`](./docs/pwa/web.md).

## AI engine: Gemini only (default) or Claude

Out of the box the bot runs **on Gemini only**: a single free `GEMINI_API_KEY` is
enough. All AI features (workout reviews, coach, board/food photo recognition, the
in-depth "Review by Monsieur Claude") go through Gemini.

If you have Claude, turn it on with one flag in `config.toml`:

```toml
[llm]
use_claude = true
```

The pipeline then becomes Claude-first with a Gemini fallback. `use_claude = true`
needs **one of**:
- an installed, logged-in Claude Code CLI (`claude` in `PATH`, on a subscription), **or**
- `ANTHROPIC_API_KEY` in `.env` (text reviews via the API; photo recognition stays
  on Gemini).

If neither is available, a warning goes to the log and everything quietly falls back
to Gemini; nothing breaks.

## Production (permanent hosting)

Any small Linux host works (a VPS or a home server) as long as it can reach the
Gemini API (it doesn't work from some regions, including Russia). Two systemd units:
`fepra-bot` (polling) and `fepra-app` (uvicorn: Mini App + REST + PWA).

You need a permanent public HTTPS address, set in `FEPRA_PUBLIC_URL` (and
`MINIAPP_URL`): invites and watch callbacks are built from it, and it is also the
passkey relying party, so it can't change once keys are registered. Options:
- your own domain + a **Caddy** reverse proxy (Let's Encrypt), template in `deploy/Caddyfile`;
- no public IP: a tunnel (e.g. Tailscale Funnel or a named Cloudflare Tunnel).

Cron jobs: `server_sync.py` (watch sync) → `server_review.py` (auto reviews),
`server_notify.py` (Web Push, hourly). Step-by-step guide and templates:
[`deploy/README.md`](./deploy/README.md) (Russian). Updating: `git pull`, `make web`,
restart the services; data (`training.db`, tokens, `.env`) is left untouched.

## Legacy: Obsidian/CLI layer

The project started as a plaintext journal in Obsidian with a `tj` CLI (`seed`/`sync`/
`build`/`analyze`/`report`): Garmin watch → `raw/` → canonical → md notes → DB cache.
This layer (`tj/cli.py`, `adapters/`, `vault/`, `store/`) is kept and still works, but
**`training.db` is now the source of truth** and the bot is the main input. The CLI is
useful for backfilling Garmin history and offline analysis.

## Security

`.env`, `config.toml`, `*token*`, `users_allow.json`, `admins.json`, `pro_users.json`,
`*.db`/`*.db.bak*`, `raw/`, `data/`, `backups/` are in `.gitignore`. Never commit or
print tokens and credentials.
