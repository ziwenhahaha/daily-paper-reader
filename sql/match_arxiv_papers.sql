-- ============================================================
-- Supabase RPC 函数定义（含日期过滤参数）
-- ============================================================
-- 背景：
--   match_arxiv_papers_exact 使用精确向量距离（无索引），在大表上易触发
--   PostgreSQL statement_timeout（错误码 57014）。
--   添加 filter_published_start / filter_published_end 参数后，数据库先
--   按 published 时间窗口过滤，再做向量计算，大幅缩小扫描范围。
--
-- 使用方式：
--   在 Supabase SQL Editor 中执行以下语句。
--   新增参数均带 DEFAULT NULL，旧客户端调用（不传日期）不受影响。
-- ============================================================

-- 1. 精确向量检索（无索引，全表扫描 → 加日期过滤后仅扫窗口内行）
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
    p.source,
    1 - (p.embedding <=> query_embedding) AS similarity
  FROM arxiv_papers p
  WHERE p.embedding IS NOT NULL
    AND (filter_published_start IS NULL OR p.published >= filter_published_start)
    AND (filter_published_end   IS NULL OR p.published <  filter_published_end)
  ORDER BY p.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- 2. ANN 向量检索（使用 HNSW / IVFFlat 索引）
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
    p.source,
    1 - (p.embedding <=> query_embedding) AS similarity
  FROM arxiv_papers p
  WHERE p.embedding IS NOT NULL
    AND (filter_published_start IS NULL OR p.published >= filter_published_start)
    AND (filter_published_end   IS NULL OR p.published <  filter_published_end)
  ORDER BY p.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- 3. BM25 全文检索
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
