create table if not exists public.defect_review_cycles (
  id bigserial primary key,
  cycle_key text not null unique,
  result_key text not null references public.check_results(result_key) on delete cascade,
  check_name text not null,
  check_title text not null,
  cycle_type text not null check (cycle_type in ('appeared', 'reopened')),
  open_reason text,
  opened_at timestamptz not null,
  opened_run_id text,
  comparison_key text,
  old_parameter_spread numeric,
  new_parameter_spread numeric,
  previous_verdict text,
  previous_review_comment text,
  previous_reviewed_by text,
  previous_reviewed_at timestamptz,
  opened_payload_json jsonb not null default '{}'::jsonb,
  verdict text check (verdict is null or verdict in ('defect', 'normal')),
  review_comment text,
  reviewed_by text,
  reviewed_at timestamptz,
  response_seconds numeric,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_defect_review_cycles_result_key
  on public.defect_review_cycles(result_key);

create index if not exists idx_defect_review_cycles_open
  on public.defect_review_cycles(result_key, opened_at desc)
  where reviewed_at is null;

create index if not exists idx_defect_review_cycles_reviewed_by
  on public.defect_review_cycles(reviewed_by, reviewed_at desc);

create index if not exists idx_defect_review_cycles_type
  on public.defect_review_cycles(check_name, cycle_type, opened_at desc);

alter table public.defect_review_cycles enable row level security;
