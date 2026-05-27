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

Use `Start Line Monitor.cmd` to run the monitor and start the local preview.
