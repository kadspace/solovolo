# solovolo

Get Discord notifications when new Volo Sports pickups and drop-ins are posted in San Diego.

## What it does

Checks Volo Sports every 5 minutes for new volleyball and soccer pickups/drop-ins. When something new pops up, you get a Discord ping with the details.

## Setup

1. Clone this repo
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and add your Discord webhook URL
4. Run it:
   ```bash
   python watcher.py
   ```

First run will populate the database with current activities (no notifications). After that, you'll get pinged for new stuff.

## Discord webhook

Create a webhook in Discord: Server Settings → Integrations → Webhooks → New Webhook

Copy the URL and put it in your `.env` file.

## Hosting

Works on Railway, Fly.io, or any server that can run Python. Set `DISCORD_WEBHOOK_URL` as an environment variable.

For Railway: just connect the repo and add the env var. The `Procfile` handles the rest.

## Why

Volo pickups fill up fast. This lets you know immediately instead of checking manually.
