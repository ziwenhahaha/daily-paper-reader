-- ============================================================
-- Conference paper table anon/authenticated read-only access policies
-- ============================================================
--
-- Purpose:
-- - Allow frontend to read ICML / NeurIPS conference papers using Supabase anon key from config.yaml.
-- - Fix REST query returning 200 [] issue: with RLS enabled, rows are not visible to anon without SELECT policy.
--
-- Security boundaries:
-- - Only allow SELECT, not INSERT / UPDATE / DELETE.
-- - Only allow rows with source matching public conference paper format to be visible.
-- - The current vector RPC is invoker-permission function, which reads the embedding column; therefore, we grant SELECT to the entire table.
-- - If in the future we do not want anon to directly read the embedding column, we need to move the RPC to a more controlled design and tighten column permissions.

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
-- Verify SQL
-- ============================================================
--
-- After executing the above transaction in the Supabase SQL Editor, you can verify the REST visibility using the anon key:
--
-- curl "$SUPABASE_URL/rest/v1/icml_openreview_papers?select=id,title,source&source=like.ICML-2025*&limit=1" \
--   -H "apikey: $SUPABASE_ANON_KEY" \
--   -H "Authorization: Bearer $SUPABASE_ANON_KEY"
--
-- curl "$SUPABASE_URL/rest/v1/neurips_openreview_papers?select=id,title,source&source=like.NeurIPS-2025*&limit=1" \
--   -H "apikey: $SUPABASE_ANON_KEY" \
--   -H "Authorization: Bearer $SUPABASE_ANON_KEY"
