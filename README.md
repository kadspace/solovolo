# solovolo

Get Discord notifications when new Volo Sports pickups and drop-ins are posted in San Diego.

## What it does

Checks Volo Sports every 5 minutes for new pickups/drop-ins across all sports except softball. When something new pops up, you get a Discord ping with the details.

Drop-ins only notify when the Volo API reports male-eligible spots. If a drop-in is first seen with no male-eligible spots, it stays pending and can notify later if spots open up.

## Setup

1. Clone this repo.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and add your Discord webhook URL.
4. Run it:
   ```bash
   python watcher.py
   ```

By default, first run sends notifications for current notifiable activities. Set `NOTIFY_ON_STARTUP=false` if you only want pings after the first poll.

## Discord webhook

Create a webhook in Discord: Server Settings -> Integrations -> Webhooks -> New Webhook.

Copy the URL and put it in your `.env` file.

## Hosting

The recommended free-tier deployment is Cloudflare Workers Cron + D1. This repo
includes a Worker port in `src/worker.js`, D1 migrations in `migrations/`, and
Wrangler config in `wrangler.toml`.

Cloudflare quick start:

1. Install Worker dependencies:
   ```bash
   npm install
   ```
2. Log in and create the D1 database:
   ```bash
   npx wrangler login
   npx wrangler d1 create solovolo
   ```
3. Copy the generated D1 `database_id` into `wrangler.toml`.
4. Apply the remote migration:
   ```bash
   npx wrangler d1 migrations apply solovolo --remote
   ```
5. Store your Discord webhook as a Worker secret:
   ```bash
   npx wrangler secret put DISCORD_WEBHOOK_URL
   ```
6. Deploy:
   ```bash
   npm run deploy
   ```

For local Cloudflare testing, create `.dev.vars` with `DISCORD_WEBHOOK_URL=...`,
run `npm run dev`, then call:

```bash
curl "http://localhost:8787/__scheduled?cron=*/5+*+*+*+*"
```

The original Python worker still works on any server that can run Python. Set
`DISCORD_WEBHOOK_URL` as an environment variable.

Optional environment variables:

- `POLL_INTERVAL`: seconds between checks, default `300`.
- `EXCLUDED_SPORTS`: comma-separated sports to suppress, default `Softball`.
- `WATCHED_SPORTS`: comma-separated sports to check. Leave unset to check all sports.
- `NOTIFY_ON_STARTUP`: set to `false` to skip startup notifications.
- `SEND_STARTUP_STATUS`: set to `false` to skip the "online" ping on worker boot.
- `DB_PATH`: override the SQLite path, useful if Railway has a mounted volume.

Cloudflare ignores `POLL_INTERVAL`, `SEND_STARTUP_STATUS`, and `DB_PATH`.
Schedule frequency comes from `wrangler.toml`, state is stored in D1, and there
is no long-running process startup ping.

For Railway, connect the repo and add the env vars. `railway.json` sets the start command to `python watcher.py`.

## Why

Volo pickups fill up fast. This lets you know immediately instead of checking manually.
