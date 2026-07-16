-- ============================================================
-- 会议论文表 anon/authenticated 只读访问策略
-- ============================================================
--
-- 用途：
-- - 让前端和会议检索链路使用 Supabase anon key 读取公开会议论文表。
-- - 对齐生产库当前已经开放的 9 个会议源。
-- - 修复 RLS 开启后没有 SELECT policy 导致 REST/RPC 查不到行的问题。
--
-- 安全边界：
-- - 仅开放 SELECT，不开放 INSERT / UPDATE / DELETE。
-- - 仅允许 source 符合公开会议论文格式的行可见。
-- - 当前向量 RPC 是 invoker 权限函数，会读取 embedding 列；因此这里对整表授予 SELECT。
--   如果未来不希望 anon 直接读取 embedding 列，需要把 RPC 迁到更受控的设计后再收紧列权限。

begin;

grant usage on schema public to anon, authenticated;

-- OpenReview 会议表
alter table public.icml_openreview_papers enable row level security;
alter table public.neurips_openreview_papers enable row level security;
alter table public.iclr_openreview_papers enable row level security;

grant select on table public.icml_openreview_papers to anon, authenticated;
grant select on table public.neurips_openreview_papers to anon, authenticated;
grant select on table public.iclr_openreview_papers to anon, authenticated;

drop policy if exists "public read icml openreview papers" on public.icml_openreview_papers;
create policy "public read icml openreview papers"
on public.icml_openreview_papers
for select
to anon, authenticated
using (
  source ~ '^ICML-[0-9]{4}-(Accepted|Public|Rejected-Public|Withdrawn-Public)$'
);

drop policy if exists "public read neurips openreview papers" on public.neurips_openreview_papers;
create policy "public read neurips openreview papers"
on public.neurips_openreview_papers
for select
to anon, authenticated
using (
  source ~ '^NeurIPS-[0-9]{4}-(Accepted|Public|Rejected-Public|Withdrawn-Public)$'
);

drop policy if exists "public read iclr openreview papers" on public.iclr_openreview_papers;
create policy "public read iclr openreview papers"
on public.iclr_openreview_papers
for select
to anon, authenticated
using (
  source ~ '^ICLR-[0-9]{4}-(Accepted|Public|Rejected-Public|Withdrawn-Public)$'
);

-- Proceedings / anthology 会议表
alter table public.aaai_papers enable row level security;
alter table public.acl_papers enable row level security;
alter table public.emnlp_papers enable row level security;
alter table public.cvpr_papers enable row level security;
alter table public.eccv_papers enable row level security;
alter table public.ijcai_papers enable row level security;
alter table public.osdi_papers enable row level security;
alter table public.sosp_papers enable row level security;
alter table public.ieee_sp_papers enable row level security;
alter table public.ndss_papers enable row level security;

grant select on table public.aaai_papers to anon, authenticated;
grant select on table public.acl_papers to anon, authenticated;
grant select on table public.emnlp_papers to anon, authenticated;
grant select on table public.cvpr_papers to anon, authenticated;
grant select on table public.eccv_papers to anon, authenticated;
grant select on table public.ijcai_papers to anon, authenticated;
grant select on table public.osdi_papers to anon, authenticated;
grant select on table public.sosp_papers to anon, authenticated;
grant select on table public.ieee_sp_papers to anon, authenticated;
grant select on table public.ndss_papers to anon, authenticated;

drop policy if exists "public read aaai papers" on public.aaai_papers;
create policy "public read aaai papers"
on public.aaai_papers
for select
to anon, authenticated
using (
  source ~ '^AAAI-[0-9]{4}-[A-Za-z0-9-]+$'
);

drop policy if exists "public read acl papers" on public.acl_papers;
create policy "public read acl papers"
on public.acl_papers
for select
to anon, authenticated
using (
  source ~ '^ACL-[0-9]{4}-[A-Za-z0-9-]+$'
);

drop policy if exists "public read emnlp papers" on public.emnlp_papers;
create policy "public read emnlp papers"
on public.emnlp_papers
for select
to anon, authenticated
using (
  source ~ '^EMNLP-[0-9]{4}-[A-Za-z0-9-]+$'
);

drop policy if exists "public read cvpr papers" on public.cvpr_papers;
create policy "public read cvpr papers"
on public.cvpr_papers
for select
to anon, authenticated
using (
  source ~ '^CVPR-[0-9]{4}-[A-Za-z0-9-]+$'
);

drop policy if exists "public read eccv papers" on public.eccv_papers;
create policy "public read eccv papers"
on public.eccv_papers
for select
to anon, authenticated
using (
  source ~ '^ECCV-[0-9]{4}-[A-Za-z0-9-]+$'
);

drop policy if exists "public read ijcai papers" on public.ijcai_papers;
create policy "public read ijcai papers"
on public.ijcai_papers
for select
to anon, authenticated
using (
  source ~ '^IJCAI-[0-9]{4}-[A-Za-z0-9-]+$'
);

drop policy if exists "public read osdi papers" on public.osdi_papers;
create policy "public read osdi papers"
on public.osdi_papers
for select
to anon, authenticated
using (
  source ~ '^OSDI-[0-9]{4}-[A-Za-z0-9-]+$'
);

drop policy if exists "public read sosp papers" on public.sosp_papers;
create policy "public read sosp papers"
on public.sosp_papers
for select
to anon, authenticated
using (
  source ~ '^SOSP-[0-9]{4}-[A-Za-z0-9-]+$'
);

drop policy if exists "public read ieee sp papers" on public.ieee_sp_papers;
create policy "public read ieee sp papers"
on public.ieee_sp_papers
for select
to anon, authenticated
using (
  source ~ '^IEEE-SP-[0-9]{4}-[A-Za-z0-9-]+$'
);

drop policy if exists "public read ndss papers" on public.ndss_papers;
create policy "public read ndss papers"
on public.ndss_papers
for select
to anon, authenticated
using (
  source ~ '^NDSS-[0-9]{4}-[A-Za-z0-9-]+$'
);

-- RPC execute grants
grant execute on function public.match_icml_openreview_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_icml_openreview_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_neurips_openreview_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_neurips_openreview_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_iclr_openreview_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_iclr_openreview_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_aaai_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_aaai_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_acl_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_acl_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_emnlp_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_emnlp_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_cvpr_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_cvpr_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_eccv_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_eccv_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_ijcai_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_ijcai_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_osdi_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_osdi_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_sosp_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_sosp_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_ieee_sp_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_ieee_sp_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_ndss_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_ndss_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant select on public.conference_papers_unified
to anon, authenticated;

grant execute on function public.match_conference_papers_exact(vector, int, text[])
to anon, authenticated;
grant execute on function public.match_conference_papers_bm25(text, int, text[])
to anon, authenticated;

commit;
