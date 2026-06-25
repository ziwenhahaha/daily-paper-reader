-- ============================================================
-- Supabase RPC function definitions (with date filtering parameters)
-- ============================================================
-- Background:
--   match_arxiv_papers_exact uses exact vector distance (no index), which is prone to triggering PostgreSQL statement_timeout (error code 57014) on large tables.
--   After adding filter_published_start / filter_published_end parameters, the database first filters by published date window, then performs vector calculation, significantly reducing the scan range.
--
-- Usage:
--   Execute the following statements in the Supabase SQL Editor.
--   All new parameters are DEFAULT NULL, old clients (without date) are not affected.
-- ============================================================

-- 1. Exact vector retrieval (no index, full table scan → after adding date filtering, only scan within the window)
CREATE OR REPLACE FUNCTION match_arxiv_papers_exact(
  query_embedding vector,
  match_count     int,
  filter_published_start timestamptz DEFAULT NULL,
  filter_published_end   timestamptz DEFAULT NULL
)
RETURNS TABLE (
  id                text,
  title             text,
  abstract          text,
  authors           jsonb,
  primary_category  text,
  categories        jsonb,
  published         timestamptz,
  link              text,
  pdf_url           text,
  source            text,
  similarity        float8
)
LANGUAGE sql STABLE
AS $$
  SELECT
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
    1 - (p.embedding <=> query_embedding) AS similarity
  FROM arxiv_papers p
  WHERE p.embedding IS NOT NULL
    AND (filter_published_start IS NULL OR p.published >= filter_published_start)
    AND (filter_published_end   IS NULL OR p.published <  filter_published_end)
  ORDER BY p.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- 2. ANN vector retrieval (using HNSW / IVFFlat index)
CREATE OR REPLACE FUNCTION match_arxiv_papers(
  query_embedding vector,
  match_count     int,
  filter_published_start timestamptz DEFAULT NULL,
  filter_published_end   timestamptz DEFAULT NULL
)
RETURNS TABLE (
  id                text,
  title             text,
  abstract          text,
  authors           jsonb,
  primary_category  text,
  categories        jsonb,
  published         timestamptz,
  link              text,
  pdf_url           text,
  source            text,
  similarity        float8
)
LANGUAGE sql STABLE
AS $$
  SELECT
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
    1 - (p.embedding <=> query_embedding) AS similarity
  FROM arxiv_papers p
  WHERE p.embedding IS NOT NULL
    AND (filter_published_start IS NULL OR p.published >= filter_published_start)
    AND (filter_published_end   IS NULL OR p.published <  filter_published_end)
  ORDER BY p.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- 3. BM25 full-text retrieval
CREATE OR REPLACE FUNCTION match_arxiv_papers_bm25(
  query_text      text,
  match_count     int,
  filter_published_start timestamptz DEFAULT NULL,
  filter_published_end   timestamptz DEFAULT NULL
)
RETURNS TABLE (
  id                text,
  title             text,
  abstract          text,
  authors           jsonb,
  primary_category  text,
  categories        jsonb,
  published         timestamptz,
  link              text,
  pdf_url           text,
  source            text,
  similarity        float8,
  score             float8
)
LANGUAGE sql STABLE
AS $$
  SELECT
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
    0::float8 AS similarity,
    ts_rank_cd(
      to_tsvector('english', coalesce(p.title, '') || ' ' || coalesce(p.abstract, '')),
      plainto_tsquery('english', query_text)
    ) AS score
  FROM arxiv_papers p
  WHERE to_tsvector('english', coalesce(p.title, '') || ' ' || coalesce(p.abstract, ''))
        @@ plainto_tsquery('english', query_text)
    AND (filter_published_start IS NULL OR p.published >= filter_published_start)
    AND (filter_published_end   IS NULL OR p.published <  filter_published_end)
  ORDER BY score DESC
  LIMIT match_count;
$$;
