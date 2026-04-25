-- ============================================================
-- 多表联合检索：arXiv + bioRxiv
-- ============================================================
-- 设计目标：
-- 1) 先通过 UNION ALL 将多个论文表合并为统一候选池；
-- 2) 再在统一候选池上执行 exact 向量召回 / BM25 全文召回；
-- 3) 支持通过 filter_sources 精确控制本次检索涉及哪些源。
--
-- 说明：
-- - 当前版本显式联合 public.arxiv_papers + public.biorxiv_papers。
-- - 后续若增加 medRxiv / ChemRxiv，可继续在视图里追加 UNION ALL。
-- - 由于当前项目已经收口为 exact-only，这种“多表先选池再精排”是合适的。
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
