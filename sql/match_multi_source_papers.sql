-- ============================================================
-- Multi-source paper retrieval RPC
-- ============================================================
-- Design goals:
-- 1) First, UNION ALL multiple paper tables into a unified candidate pool;
-- 2) Then, perform exact vector retrieval / BM25 full-text retrieval on the unified candidate pool;
-- 3) Support filtering the sources involved in this retrieval via filter_sources.
--
-- Notes:
-- - Currently, public.arxiv_papers + public.biorxiv_papers are explicitly UNION ALLed.
-- - Future extensions (e.g., medRxiv / ChemRxiv) can simply add UNION ALL to the view.
-- - Given the current project is exact-only, this "multi-table selection pool then re-ranking" approach is appropriate.
-- ============================================================

create or replace view public.multi_source_papers as
select
  p.id,
  p.source,
  p.source_paper_id,
  p.doi,
  p.version,
  p.title,
  p.abstract,
  p.authors,
  p.primary_category,
  p.categories,
  p.published,
  p.link,
  p.pdf_url,
  p.embedding,
  p.embedding_model,
  p.embedding_dim,
  p.embedding_updated_at,
  p.updated_at
from public.arxiv_papers p

union all

select
  p.id,
  p.source,
  p.source_paper_id,
  p.doi,
  p.version,
  p.title,
  p.abstract,
  p.authors,
  p.primary_category,
  p.categories,
  p.published,
  p.link,
  p.pdf_url,
  p.embedding,
  p.embedding_model,
  p.embedding_dim,
  p.embedding_updated_at,
  p.updated_at
from public.biorxiv_papers p;


create or replace function match_multi_source_papers_exact(
  query_embedding vector,
  match_count int,
  filter_sources text[] default null,
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
language sql stable
as $$
  with selected as (
    select *
    from public.multi_source_papers p
    where (filter_sources is null or p.source = any(filter_sources))
      and (filter_published_start is null or p.published >= filter_published_start)
      and (filter_published_end is null or p.published < filter_published_end)
  )
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
  from selected p
  where p.embedding is not null
  order by p.embedding <=> query_embedding
  limit match_count;
$$;


create or replace function match_multi_source_papers_bm25(
  query_text text,
  match_count int,
  filter_sources text[] default null,
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
language sql stable
as $$
  with selected as (
    select *
    from public.multi_source_papers p
    where (filter_sources is null or p.source = any(filter_sources))
      and (filter_published_start is null or p.published >= filter_published_start)
      and (filter_published_end is null or p.published < filter_published_end)
  )
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
    0::float8 as similarity,
    ts_rank_cd(
      to_tsvector('english', coalesce(p.title, '') || ' ' || coalesce(p.abstract, '')),
      plainto_tsquery('english', query_text)
    ) as score
  from selected p
  where to_tsvector('english', coalesce(p.title, '') || ' ' || coalesce(p.abstract, ''))
        @@ plainto_tsquery('english', query_text)
  order by score desc
  limit match_count;
$$;
