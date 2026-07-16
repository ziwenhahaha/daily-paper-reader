-- ============================================================
-- 会议年份统计快照表
-- ============================================================

create table if not exists public.conference_year_stats (
  id text primary key,
  conference_key text not null,
  conference_label text not null,
  year int not null,
  source_table text not null,
  official_accepted_count int not null default 0,
  stored_total_count int not null default 0,
  stored_accepted_count int not null default 0,
  stored_rejected_count int not null default 0,
  stored_other_count int not null default 0,
  generated_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (conference_key, year)
);

create index if not exists conference_year_stats_conference_year_idx
  on public.conference_year_stats (conference_key, year desc);

alter table public.conference_year_stats enable row level security;

drop policy if exists conference_year_stats_anon_select on public.conference_year_stats;
create policy conference_year_stats_anon_select
  on public.conference_year_stats
  for select
  to anon, authenticated
  using (true);

grant select on public.conference_year_stats to anon, authenticated;
grant select, insert, update, delete on public.conference_year_stats to service_role;
