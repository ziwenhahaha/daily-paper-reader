-- Daily Paper Reader real-time workflow run status & step progress table.
-- Stores non-sensitive execution metadata only (no API keys, tokens, or private prompts).
-- Shared across forks via public Supabase, partitioned by repo_full_name (owner/repo).

create table if not exists public.workflow_run_status (
  repo_full_name text not null,
  run_key text not null,
  workflow_key text not null default '',
  workflow_file text not null default '',
  display_label text not null default '',
  run_id bigint,
  run_number integer,
  run_url text not null default '',
  status text not null default 'queued',
  conclusion text not null default '',
  step_code text not null default '',
  step_label text not null default '',
  progress_current integer not null default 0,
  progress_total integer not null default 0,
  detail text not null default '',
  started_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  primary key (repo_full_name, run_key),
  constraint workflow_run_status_repo_format
    check (repo_full_name ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'),
  constraint workflow_run_status_key_format
    check (run_key ~ '^(?:gh:[0-9]{1,20}|pending:[A-Za-z0-9_.-]{1,64}:[0-9]{1,20})$'),
  constraint workflow_run_status_status_valid
    check (status in ('queued', 'in_progress', 'completed')),
  constraint workflow_run_status_conclusion_valid
    check (conclusion in ('', 'success', 'failure', 'cancelled', 'skipped')),
  constraint workflow_run_status_progress_nonneg
    check (progress_current >= 0 and progress_total >= 0),
  constraint workflow_run_status_url_safe
    check (
      run_url = ''
      or run_url ~ '^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/[0-9]+$'
    ),
  constraint workflow_run_status_lengths
    check (
      char_length(workflow_key) <= 64
      and char_length(workflow_file) <= 100
      and char_length(display_label) <= 160
      and char_length(step_code) <= 64
      and char_length(step_label) <= 120
      and char_length(detail) <= 240
    )
);

create index if not exists workflow_run_status_repo_updated_idx
  on public.workflow_run_status (repo_full_name, updated_at desc);

alter table public.workflow_run_status enable row level security;

revoke all on table public.workflow_run_status from anon, authenticated;

grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on public.workflow_run_status to anon, authenticated;
grant select, insert, update, delete on public.workflow_run_status to service_role;

drop policy if exists workflow_run_status_select_recent
  on public.workflow_run_status;
create policy workflow_run_status_select_recent
  on public.workflow_run_status
  for select
  to anon, authenticated
  using (updated_at >= now() - interval '7 days');

drop policy if exists workflow_run_status_insert_valid
  on public.workflow_run_status;
create policy workflow_run_status_insert_valid
  on public.workflow_run_status
  for insert
  to anon, authenticated
  with check (
    repo_full_name ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'
    and run_key ~ '^(?:gh:[0-9]{1,20}|pending:[A-Za-z0-9_.-]{1,64}:[0-9]{1,20})$'
  );

drop policy if exists workflow_run_status_update_recent
  on public.workflow_run_status;
create policy workflow_run_status_update_recent
  on public.workflow_run_status
  for update
  to anon, authenticated
  using (updated_at >= now() - interval '7 days')
  with check (
    repo_full_name ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'
    and run_key ~ '^(?:gh:[0-9]{1,20}|pending:[A-Za-z0-9_.-]{1,64}:[0-9]{1,20})$'
  );

drop policy if exists workflow_run_status_delete_pending
  on public.workflow_run_status;
create policy workflow_run_status_delete_pending
  on public.workflow_run_status
  for delete
  to anon, authenticated
  using (run_key like 'pending:%');
