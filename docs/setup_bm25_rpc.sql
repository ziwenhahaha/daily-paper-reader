-- Daily Paper Reader - Supabase BM25 检索（全文检索）安装脚本
-- 目标：在数据库侧提供 match_arxiv_papers_bm25 RPC，供 src/2.1.retrieval_papers_bm25.py 调用
-- 适用前提：表 public.arxiv_papers 已存在（见 docs/supabase_schema.sql）

-- ===== 1) 为 arxiv_papers 增加/补齐全文检索字段 =====
alter table if exists public.arxiv_papers
add column if not exists search_tsv tsvector;

-- ===== 2) 回填已有数据 =====
update public.arxiv_papers
set search_tsv =
  setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
where search_tsv is null;

-- ===== 3) 为全文检索创建 GIN 索引（首次创建会很耗时，建议离线执行） =====
create index if not exists idx_arxiv_papers_search_tsv
on public.arxiv_papers using gin (search_tsv);

-- ===== 4) 自动维护 search_tsv（INSERT/UPDATE） =====
create or replace function public.arxiv_papers_search_tsv_update()
returns trigger
language plpgsql
as $$
begin
  NEW.search_tsv :=
    setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.abstract, '')), 'B');
  return NEW;
end;
$$;

drop trigger if exists trg_arxiv_papers_search_tsv on public.arxiv_papers;
create trigger trg_arxiv_papers_search_tsv
before insert or update on public.arxiv_papers
for each row
execute function public.arxiv_papers_search_tsv_update();

-- ===== 5) BM25 风格 RPC（ts_rank_cd） =====
-- 参数：
--   query_text: 关键词文本
--   match_count: 返回条数（默认 50）
create or replace function public.match_arxiv_papers_bm25(
  query_text text,
  match_count int default 50
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
  score real
)
language plpgsql
stable
as $$
declare
  safe_match_count int;
  q_raw text;
  q tsquery;
begin
  safe_match_count := greatest(coalesce(match_count, 0), 1);
  -- REST 参数在某些环境里可能会带入单引号，先做一次轻量清洗，避免 tsquery 语法错误。
  q_raw := coalesce(query_text, '');
  q_raw := regexp_replace(q_raw, E'\\s+', ' ', 'g');
  q_raw := trim(q_raw);
  q_raw := btrim(q_raw, E'''\"');
  q_raw := trim(regexp_replace(q_raw, E'[\'\"]', ' ', 'g'));
  q := websearch_to_tsquery('english', q_raw);

  if q_raw = '' or q = ''''::tsquery then
    return;
  end if;

  return query
  select
    p.id,
    p.title,
    p.abstract,
    p.authors,
    p.primary_category,
    p.categories,
    p.published,
    p.link,
    ts_rank_cd(p.search_tsv, q, 32)::real as score
  from public.arxiv_papers p
  where p.search_tsv @@ q
  order by ts_rank_cd(p.search_tsv, q, 32) desc
  limit safe_match_count;
end;
$$;

-- 如果你不想改动 trigger/列，也可临时回退到在线构建检索向量：
--   把 where/order 内的 p.search_tsv 替换为：
--   (
--     setweight(to_tsvector('english', coalesce(p.title, '')), 'A') ||
--     setweight(to_tsvector('english', coalesce(p.abstract, '')), 'B')
--   ) @@ q
