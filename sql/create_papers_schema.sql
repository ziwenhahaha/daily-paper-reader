-- ============================================================
-- 通用论文表结构（适用于 arXiv / bioRxiv 等单源仓库）
-- ============================================================

create extension if not exists vector;

create table if not exists public.papers (
  id text primary key,
  source text not null,
  source_paper_id text,
  doi text,
  version text,
  title text not null,
  abstract text,
  authors jsonb not null default '[]'::jsonb,
  primary_category text,
  categories jsonb not null default '[]'::jsonb,
  published timestamptz,
  link text,
  embedding vector(384),
  embedding_model text,
  embedding_dim int,
  embedding_updated_at timestamptz,
  updated_at timestamptz not null default now()
);

create index if not exists papers_source_published_idx
  on public.papers (source, published desc);

create index if not exists papers_published_idx
  on public.papers (published desc);

create index if not exists papers_title_abstract_fts_idx
  on public.papers
  using gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, '')));

create index if not exists papers_embedding_hnsw_idx
  on public.papers
  using hnsw (embedding vector_cosine_ops);
