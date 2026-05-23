-- ============================================================
-- 会议论文表 anon/authenticated 只读访问策略
-- ============================================================
--
-- 用途：
-- - 让前端使用 config.yaml 中的 Supabase anon key 读取 ICML / NeurIPS 会议论文。
-- - 修复 REST 查询返回 200 [] 的问题：RLS 开启后，没有 SELECT policy 时 anon 看不到行。
--
-- 安全边界：
-- - 仅开放 SELECT，不开放 INSERT / UPDATE / DELETE。
-- - 仅允许 source 符合公开会议论文格式的行可见。
-- - 当前向量 RPC 是 invoker 权限函数，会读取 embedding 列；因此这里对整表授予 SELECT。
--   如果未来不希望 anon 直接读取 embedding 列，需要把 RPC 迁到更受控的设计后再收紧列权限。

begin;

alter table public.icml_openreview_papers enable row level security;
alter table public.neurips_openreview_papers enable row level security;

grant usage on schema public to anon, authenticated;

grant select on table public.icml_openreview_papers to anon, authenticated;
grant select on table public.neurips_openreview_papers to anon, authenticated;

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

grant execute on function public.match_icml_openreview_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_icml_openreview_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_neurips_openreview_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_neurips_openreview_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

commit;

-- ============================================================
-- 验证 SQL
-- ============================================================
--
-- 在 Supabase SQL Editor 执行上面的事务后，可以用 anon key 验证 REST 可见性：
--
-- curl "$SUPABASE_URL/rest/v1/icml_openreview_papers?select=id,title,source&source=like.ICML-2025*&limit=1" \
--   -H "apikey: $SUPABASE_ANON_KEY" \
--   -H "Authorization: Bearer $SUPABASE_ANON_KEY"
--
-- curl "$SUPABASE_URL/rest/v1/neurips_openreview_papers?select=id,title,source&source=like.NeurIPS-2025*&limit=1" \
--   -H "apikey: $SUPABASE_ANON_KEY" \
--   -H "Authorization: Bearer $SUPABASE_ANON_KEY"
