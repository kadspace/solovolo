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

Works on Railway, Fly.io, or any server that can run Python. Set `DISCORD_WEBHOOK_URL` as an environment variable.

Optional environment variables:

- `POLL_INTERVAL`: seconds between checks, default `300`.
- `EXCLUDED_SPORTS`: comma-separated sports to suppress, default `Softball`.
- `WATCHED_SPORTS`: comma-separated sports to check. Leave unset to check all sports.
- `NOTIFY_ON_STARTUP`: set to `false` to skip startup notifications.
- `DB_PATH`: override the SQLite path, useful if Railway has a mounted volume.

For Railway, connect the repo and add the env vars. The `Procfile` starts the worker.

## Why

Volo pickups fill up fast. This lets you know immediately instead of checking manually.
