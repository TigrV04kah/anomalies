create table if not exists public.monitor_runs (
  run_id text primary key,
  started_at timestamptz not null,
  mode text not null,
  changed_games integer not null,
  snapshot_games integer not null,
  summary_json jsonb not null
);

create table if not exists public.run_statistics (
  run_id text primary key references public.monitor_runs(run_id),
  started_at timestamptz not null,
  finished_at timestamptz not null,
  duration_seconds numeric not null,
  mode text not null,
  changed_games integer not null,
  snapshot_games integer not null,
  total_anomalies integer not null,
  checks_with_anomalies integer not null,
  synced_results integer not null,
  updated_since timestamptz,
  max_dd timestamptz,
  check_counts_json jsonb not null,
  status_counts_json jsonb not null,
  synced_counts_json jsonb not null
);

create table if not exists public.run_check_statistics (
  run_id text not null references public.monitor_runs(run_id),
  check_name text not null,
  check_title text not null,
  rows_count integer not null,
  status_counts_json jsonb not null,
  synced_rows integer not null,
  primary key (run_id, check_name)
);

create table if not exists public.check_results (
  result_key text primary key,
  check_name text not null,
  check_title text not null,
  status text not null,
  first_seen_at timestamptz not null,
  last_seen_at timestamptz not null,
  last_run_id text not null references public.monitor_runs(run_id),
  occurrence_count integer not null default 1,
  payload_json jsonb not null,
  verdict text,
  review_comment text,
  reviewed_by text,
  reviewed_at timestamptz
);

create index if not exists idx_check_results_check_status
  on public.check_results(check_name, status);

create index if not exists idx_check_results_title_status
  on public.check_results(check_title, status);

create index if not exists idx_check_results_verdict
  on public.check_results(verdict);

create index if not exists idx_check_results_last_seen
  on public.check_results(last_seen_at);

create index if not exists idx_run_statistics_started_at
  on public.run_statistics(started_at desc);

create index if not exists idx_run_check_statistics_check_name
  on public.run_check_statistics(check_name, run_id);
