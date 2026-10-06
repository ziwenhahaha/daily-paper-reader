-- ============================================================
-- NeurIPS OpenReview 会议投稿表
-- ============================================================

create extension if not exists vector;

create table if not exists public.neurips_openreview_papers (
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
  pdf_url text,
  embedding vector(384),
  embedding_model text,
  embedding_dim int,
  embedding_updated_at timestamptz,
  updated_at timestamptz not null default now()
);

alter table public.neurips_openreview_papers
  add column if not exists search_tsv tsvector
  generated always as (
    to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, ''))
  ) stored;

create index if not exists neurips_openreview_papers_search_tsv_idx
  on public.neurips_openreview_papers using gin (search_tsv);

create index if not exists neurips_openreview_papers_source_published_idx
  on public.neurips_openreview_papers (source, published desc);

create index if not exists neurips_openreview_papers_published_idx
  on public.neurips_openreview_papers (published desc);

create index if not exists neurips_openreview_papers_title_abstract_fts_idx
  on public.neurips_openreview_papers
  using gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, '')));
