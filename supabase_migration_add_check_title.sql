alter table public.check_results
  add column if not exists check_title text;

update public.check_results
set check_title = case
  when check_name = 'favorite_by_period' then 'discrepancy between favorites by period'
  else check_name
end
where check_title is null or check_title = '';

alter table public.check_results
  alter column check_title set not null;

create index if not exists idx_check_results_title_status
  on public.check_results(check_title, status);
