-- ============================================================
-- ICML OpenReview 投稿表的检索 RPC
-- ============================================================

create or replace function match_icml_openreview_papers_exact(
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
  source text,
  similarity float8
)
language sql stable
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
    p.source,
    1 - (p.embedding <=> query_embedding) as similarity
  from public.icml_openreview_papers p
  where p.embedding is not null
    and (filter_published_start is null or p.published >= filter_published_start)
    and (filter_published_end is null or p.published < filter_published_end)
  order by p.embedding <=> query_embedding
  limit match_count;
$$;

create or replace function match_icml_openreview_papers_bm25(
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
  source text,
  similarity float8,
  score float8
)
language sql stable
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
    p.source,
    0::float8 as similarity,
    ts_rank_cd(
      to_tsvector('english', coalesce(p.title, '') || ' ' || coalesce(p.abstract, '')),
      plainto_tsquery('english', query_text)
    ) as score
  from public.icml_openreview_papers p
  where to_tsvector('english', coalesce(p.title, '') || ' ' || coalesce(abstract, ''))
        @@ plainto_tsquery('english', query_text)
    and (filter_published_start is null or p.published >= filter_published_start)
    and (filter_published_end is null or p.published < filter_published_end)
  order by score desc
  limit match_count;
$$;
