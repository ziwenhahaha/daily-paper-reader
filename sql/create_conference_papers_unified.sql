-- ============================================================
-- 统一会议论文检索入口
-- ============================================================

create extension if not exists vector;

create or replace view public.conference_papers_unified
with (security_invoker = true)
as
select
  'neurips'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'neurips:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'neurips_openreview_papers'::text as source_table,
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
  p.embedding
from public.neurips_openreview_papers p
union all
select
  'icml'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'icml:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'icml_openreview_papers'::text as source_table,
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
  p.embedding
from public.icml_openreview_papers p
union all
select
  'iclr'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'iclr:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'iclr_openreview_papers'::text as source_table,
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
  p.embedding
from public.iclr_openreview_papers p
union all
select
  'aaai'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'aaai:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'aaai_papers'::text as source_table,
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
  p.embedding
from public.aaai_papers p
union all
select
  'acl'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'acl:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'acl_papers'::text as source_table,
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
  p.embedding
from public.acl_papers p
union all
select
  'emnlp'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'emnlp:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'emnlp_papers'::text as source_table,
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
  p.embedding
from public.emnlp_papers p
union all
select
  'cvpr'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'cvpr:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'cvpr_papers'::text as source_table,
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
  p.embedding
from public.cvpr_papers p
union all
select
  'eccv'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'eccv:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'eccv_papers'::text as source_table,
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
  p.embedding
from public.eccv_papers p
union all
select
  'ijcai'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'ijcai:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'ijcai_papers'::text as source_table,
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
  p.embedding
from public.ijcai_papers p
union all
select
  'osdi'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'osdi:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'osdi_papers'::text as source_table,
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
  p.embedding
from public.osdi_papers p
union all
select
  'sosp'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'sosp:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'sosp_papers'::text as source_table,
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
  p.embedding
from public.sosp_papers p
union all
select
  'ieee_sp'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'ieee_sp:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'ieee_sp_papers'::text as source_table,
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
  p.embedding
from public.ieee_sp_papers p
union all
select
  'ndss'::text as conference_key,
  coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int) as conference_year,
  'ndss:' || coalesce(nullif(substring(p.source from '((?:19|20)[0-9]{2})'), '')::int, extract(year from p.published)::int)::text as conference_pair,
  'ndss_papers'::text as source_table,
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
  p.embedding
from public.ndss_papers p;

create or replace function public.match_conference_papers_exact(
  query_embedding vector,
  match_count int,
  filter_pairs text[] default null
)
returns table (
  conference_key text,
  conference_year int,
  conference_pair text,
  source_table text,
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
language plpgsql stable
set statement_timeout = '60s'
as $$
declare
  spec record;
  pair text;
  active_pairs text[] := array[]::text[];
  has_pair_filter boolean := false;
  selects text[] := array[]::text[];
  sql text;
  year_expr text := 'coalesce(nullif(substring(p.source from ''((?:19|20)[0-9]{2})''), '''')::int, extract(year from p.published)::int)';
begin
  if filter_pairs is not null then
    select array_agg(distinct lower(trim(item)))
    into active_pairs
    from unnest(filter_pairs) as item
    where trim(item) <> '';
    active_pairs := coalesce(active_pairs, array[]::text[]);
  end if;
  has_pair_filter := cardinality(active_pairs) > 0;

  for spec in
    select *
    from (values
      ('neurips', 'neurips_openreview_papers'),
      ('icml', 'icml_openreview_papers'),
      ('iclr', 'iclr_openreview_papers'),
      ('aaai', 'aaai_papers'),
      ('acl', 'acl_papers'),
      ('emnlp', 'emnlp_papers'),
      ('cvpr', 'cvpr_papers'),
      ('eccv', 'eccv_papers'),
      ('ijcai', 'ijcai_papers'),
      ('osdi', 'osdi_papers'),
      ('sosp', 'sosp_papers'),
      ('ieee_sp', 'ieee_sp_papers'),
      ('ndss', 'ndss_papers')
    ) as s(conference_key, source_table)
  loop
    if has_pair_filter then
      foreach pair in array active_pairs loop
        if pair !~ '^[a-z0-9_]+:[0-9]{4}$' or split_part(pair, ':', 1) <> spec.conference_key then
          continue;
        end if;
        selects := array_append(selects, format($fmt$
          select * from (
            select
              %L::text as conference_key,
              split_part(%L, ':', 2)::int as conference_year,
              %L::text as conference_pair,
              %L::text as source_table,
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
              1 - (p.embedding <=> $1) as similarity
            from public.%I p
            where p.embedding is not null
              and %L = (%L || ':' || (%s)::text)
            order by p.embedding <=> $1
            limit greatest($2, 1)
          ) q
        $fmt$, spec.conference_key, pair, pair, spec.source_table, spec.source_table, pair, spec.conference_key, year_expr));
      end loop;
    else
      selects := array_append(selects, format($fmt$
        select * from (
          select
            %L::text as conference_key,
            (%s) as conference_year,
            %L || ':' || (%s)::text as conference_pair,
            %L::text as source_table,
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
            1 - (p.embedding <=> $1) as similarity
          from public.%I p
          where p.embedding is not null
          order by p.embedding <=> $1
          limit greatest($2, 1)
        ) q
      $fmt$, spec.conference_key, year_expr, spec.conference_key, year_expr, spec.source_table, spec.source_table));
    end if;
  end loop;

  if cardinality(selects) = 0 then
    return;
  end if;

  -- 等价于统一 view 语义：p.conference_pair = any(filter_pairs)
  sql := 'select * from (' || array_to_string(selects, ' union all ') || ') u order by similarity desc limit greatest($2, 1)';
  return query execute sql using query_embedding, match_count;
end;
$$;

create or replace function public.match_conference_papers_bm25(
  query_text text,
  match_count int,
  filter_pairs text[] default null
)
returns table (
  conference_key text,
  conference_year int,
  conference_pair text,
  source_table text,
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
language plpgsql stable
set statement_timeout = '60s'
as $$
declare
  spec record;
  pair text;
  active_pairs text[] := array[]::text[];
  has_pair_filter boolean := false;
  selects text[] := array[]::text[];
  sql text;
  year_expr text := 'coalesce(nullif(substring(p.source from ''((?:19|20)[0-9]{2})''), '''')::int, extract(year from p.published)::int)';
begin
  if filter_pairs is not null then
    select array_agg(distinct lower(trim(item)))
    into active_pairs
    from unnest(filter_pairs) as item
    where trim(item) <> '';
    active_pairs := coalesce(active_pairs, array[]::text[]);
  end if;
  has_pair_filter := cardinality(active_pairs) > 0;

  for spec in
    select *
    from (values
      ('neurips', 'neurips_openreview_papers'),
      ('icml', 'icml_openreview_papers'),
      ('iclr', 'iclr_openreview_papers'),
      ('aaai', 'aaai_papers'),
      ('acl', 'acl_papers'),
      ('emnlp', 'emnlp_papers'),
      ('cvpr', 'cvpr_papers'),
      ('eccv', 'eccv_papers'),
      ('ijcai', 'ijcai_papers'),
      ('osdi', 'osdi_papers'),
      ('sosp', 'sosp_papers'),
      ('ieee_sp', 'ieee_sp_papers'),
      ('ndss', 'ndss_papers')
    ) as s(conference_key, source_table)
  loop
    if has_pair_filter then
      foreach pair in array active_pairs loop
        if pair !~ '^[a-z0-9_]+:[0-9]{4}$' or split_part(pair, ':', 1) <> spec.conference_key then
          continue;
        end if;
        selects := array_append(selects, format($fmt$
          select * from (
            select
              %L::text as conference_key,
              split_part(%L, ':', 2)::int as conference_year,
              %L::text as conference_pair,
              %L::text as source_table,
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
                plainto_tsquery('english', $1)
              )::float8 as score
            from public.%I p
            where to_tsvector('english', coalesce(p.title, '') || ' ' || coalesce(p.abstract, ''))
                  @@ plainto_tsquery('english', $1)
              and %L = (%L || ':' || (%s)::text)
            order by score desc
            limit greatest($2, 1)
          ) q
        $fmt$, spec.conference_key, pair, pair, spec.source_table, spec.source_table, pair, spec.conference_key, year_expr));
      end loop;
    else
      selects := array_append(selects, format($fmt$
        select * from (
          select
            %L::text as conference_key,
            (%s) as conference_year,
            %L || ':' || (%s)::text as conference_pair,
            %L::text as source_table,
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
              plainto_tsquery('english', $1)
            )::float8 as score
          from public.%I p
          where to_tsvector('english', coalesce(p.title, '') || ' ' || coalesce(p.abstract, ''))
                @@ plainto_tsquery('english', $1)
          order by score desc
          limit greatest($2, 1)
        ) q
      $fmt$, spec.conference_key, year_expr, spec.conference_key, year_expr, spec.source_table, spec.source_table));
    end if;
  end loop;

  if cardinality(selects) = 0 then
    return;
  end if;

  -- 等价于统一 view 语义：p.conference_pair = any(filter_pairs)
  sql := 'select * from (' || array_to_string(selects, ' union all ') || ') u order by score desc limit greatest($2, 1)';
  return query execute sql using query_text, match_count;
end;
$$;

grant select on public.conference_papers_unified to anon, authenticated;
grant execute on function public.match_conference_papers_exact(vector, int, text[]) to anon, authenticated;
grant execute on function public.match_conference_papers_bm25(text, int, text[]) to anon, authenticated;
