create table if not exists public.snapshot_sport_statistics (
  run_id text not null references public.monitor_runs(run_id),
  sport text not null,
  unique_main_games integer not null,
  unique_main_game_types integer not null,
  unique_event_types integer not null,
  games_count integer not null,
  events_count integer not null,
  primary key (run_id, sport)
);

create table if not exists public.snapshot_subsport_statistics (
  run_id text not null references public.monitor_runs(run_id),
  subsport text not null,
  unique_main_games integer not null,
  games_count integer not null,
  events_count integer not null,
  primary key (run_id, subsport)
);

create table if not exists public.snapshot_hourly_statistics (
  run_id text not null references public.monitor_runs(run_id),
  sport text not null,
  hour_local integer not null check (hour_local >= 0 and hour_local <= 23),
  unique_main_games integer not null,
  unique_main_game_types integer not null,
  unique_event_types integer not null,
  games_count integer not null,
  events_count integer not null,
  primary key (run_id, sport, hour_local)
);

create index if not exists idx_snapshot_sport_statistics_sport
  on public.snapshot_sport_statistics(sport, run_id);

create index if not exists idx_snapshot_subsport_statistics_subsport
  on public.snapshot_subsport_statistics(subsport, run_id);

create index if not exists idx_snapshot_hourly_statistics_sport_hour
  on public.snapshot_hourly_statistics(sport, hour_local, run_id);
