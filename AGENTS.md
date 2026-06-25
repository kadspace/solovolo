# Notes For Future Codex Sessions

This repo has two deployment paths:

- Original Python worker: `watcher.py` runs continuously with SQLite state in `volo.db`.
- Cloudflare port: `src/worker.js` runs from Workers Cron every 5 minutes and stores state in D1.

The Cloudflare port intentionally keeps the Python/Railway files intact. Do not remove
`watcher.py`, `scraper.py`, `discord.py`, `requirements.txt`, `Procfile`, or
`railway.json` unless the user explicitly asks to retire the Python deployment.

Cloudflare setup notes:

- `wrangler.toml` has `database_id = "REPLACE_WITH_D1_DATABASE_ID"` until a D1
  database is created with `npx wrangler d1 create solovolo`.
- `DISCORD_WEBHOOK_URL` must be stored as a Wrangler secret, not committed.
- `MANUAL_RUN_TOKEN` is optional, but required for the `/run` endpoint.
- D1 schema lives in `migrations/0001_init.sql`.
- The cron schedule is configured in `wrangler.toml`, not through `POLL_INTERVAL`.

Useful checks:

```bash
npm run check
python -m compileall watcher.py scraper.py discord.py
```

Local Cloudflare testing requires Wrangler and a `.dev.vars` file with local secrets.
Do not commit `.dev.vars`, `.env`, generated SQLite databases, `.wrangler/`, or
`node_modules/`.
