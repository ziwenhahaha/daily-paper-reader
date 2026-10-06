-- ============================================================
-- NeurIPS OpenReview 投稿表的检索 RPC
-- ============================================================

create or replace function match_neurips_openreview_papers_exact(
  query_embedding vector,
  match_count int,
  filter_published_start timestamptz default null,
  filter_published_end timestamptz default null
)
returns table (
  id text,
  title text,
  abstract text,
  authors jsonb,
  primary_category text,
  categories jsonb,
  published timestamptz,
  link text,
  pdf_url text,
  source text,
  similarity float8
)
language sql stable security invoker
set search_path = public, extensions
as $$
  select
    p.id,
    p.title,
    p.abstract,
    p.authors,
    p.primary_category,
    p.categories,
    p.published,
    p.link,
    p.pdf_url,
    p.source,
    1 - (p.embedding <=> query_embedding) as similarity
  from public.neurips_openreview_papers p
  where p.embedding is not null
    and (filter_published_start is null or p.published >= filter_published_start)
    and (filter_published_end is null or p.published < filter_published_end)
  order by p.embedding <=> query_embedding
  limit match_count;
$$;

create or replace function match_neurips_openreview_papers_bm25(
  query_text text,
  match_count int,
  filter_published_start timestamptz default null,
  filter_published_end timestamptz default null
)
returns table (
  id text,
  title text,
  abstract text,
  authors jsonb,
  primary_category text,
  categories jsonb,
  published timestamptz,
  link text,
  pdf_url text,
  source text,
  similarity float8,
  score float8
)
language plpgsql stable security invoker
set search_path = public, extensions
set plan_cache_mode = force_custom_plan
set jit = off
as $$
declare
  search_query tsquery := plainto_tsquery('english', query_text);
begin
  return query
  with ranked as materialized (
    select p.id, ts_rank_cd(p.search_tsv, search_query) as rank_score
    from public.neurips_openreview_papers p
    where p.search_tsv @@ search_query
      and (filter_published_start is null or p.published >= filter_published_start)
      and (filter_published_end is null or p.published < filter_published_end)
    order by rank_score desc, p.id
    limit match_count
  )
  select p.id, p.title, p.abstract, p.authors, p.primary_category,
         p.categories, p.published, p.link, p.pdf_url, p.source,
         0::float8 as similarity, r.rank_score::float8 as score
  from ranked r
  join public.neurips_openreview_papers p on p.id = r.id
  order by r.rank_score desc, r.id;
end;
$$;

notify pgrst, 'reload schema';
