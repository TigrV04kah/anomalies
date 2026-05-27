# Line Monitor

UI for reviewing line-monitor anomalies stored in Supabase.

## Deployment

Vercel deploys only the web UI and JavaScript API routes:

- `index.html`
- `app.js`
- `styles.css`
- `check_definitions.json`
- `api/*.js`

Local Python scripts, Mongo access, snapshots, reports, notebooks, CSV and ZIP files are excluded from Vercel by `.vercelignore`.

## Vercel Environment Variables

Set these variables in Vercel Project Settings:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## Local Monitor

The line export/check pipeline runs locally on the workstation.

Required local environment variables:

- `LINE_MONGO_URI`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Use `Start Line Monitor.cmd` to start the local monitor loop and local preview. It runs the full monitor immediately, then repeats every 5 minutes while the command window stays open. Stop it with `Ctrl+C`.

Full line snapshots are stored in `snapshots/current_line_snapshot.zip` by default.

By default, every monitor run fetches the full current line from Mongo. Incremental mode is kept only for debugging and must be requested explicitly with `--incremental`.
