#!/usr/bin/env python
# 基于 BM25 对 ArXiv 元数据池做二次筛选：
# 1. 读取 arxiv_fetch_raw.py 生成的 JSON（所有论文）；
# 2. 对标题 + 摘要做 BM25 索引；
# 3. 使用 config.yaml 中的 intent_profiles -> keywords / intent_queries 作为查询，计算相似度；
# 4. 每个查询保留前 top_k 篇论文，并为这些论文打上 tag（tag），一篇论文可拥有多个 tag；
# 5. 将带 tag 的论文列表和每个查询的 top_k 结果写回到一个新的 JSON 文件中。

import argparse
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Iterable

from query_boolean import (
  parse_boolean_expr,
  split_or_branches,
  evaluate_expr,
  collect_unique_positive_terms,
  clean_expr_for_embedding,
  match_term,
)
try:
  from source_backend_router import group_queries_by_source, merge_pipeline_results
  from source_config import ARXIV_SOURCE_KEY, get_source_backend, load_config_with_source_migration, normalize_source_list
except Exception:  # pragma: no cover - 兼容 package 导入路径
  from src.source_backend_router import group_queries_by_source, merge_pipeline_results
  from src.source_config import ARXIV_SOURCE_KEY, get_source_backend, load_config_with_source_migration, normalize_source_list
from subscription_plan import build_pipeline_inputs
from supabase_source import (
  count_papers_by_date_range,
  get_supabase_read_config,
  match_papers_by_bm25,
)


# 当前脚本位于 src/ 下，config.yaml 在上一级目录
SCRIPT_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "config.yaml"))
ROOT_DIR = os.path.dirname(CONFIG_FILE)
TODAY_STR = str(os.getenv("DPR_RUN_DATE") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
ARCHIVE_DIR = os.path.join(ROOT_DIR, "archive", TODAY_STR)
RAW_DIR = os.path.join(ARCHIVE_DIR, "raw")
FILTERED_DIR = os.path.join(ARCHIVE_DIR, "filtered")
DATE_RE_DAY = re.compile(r"^\d{8}$")
DATE_RE_RANGE = re.compile(r"^\d{8}-\d{8}$")
SUPABASE_TIME_FIELDS = ("published",)
SUPABASE_BM25_SHARD_DAYS = 7


TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
MAIN_TERM_WEIGHT = 1.0
RELATED_TERM_WEIGHT = 0.5
QUERY_TEXT_WEIGHT = 0
DEFAULT_OR_SOFT_WEIGHT = 0.3


def log(message: str) -> None:
  ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
  print(f"[{ts}] {message}", flush=True)


def resolve_supabase_recall_window(config: Dict[str, Any], end_dt: datetime | None = None) -> tuple[datetime, datetime]:
  paper_setting = (config or {}).get("arxiv_paper_setting") or {}
  try:
    days = int(paper_setting.get("days_window") or 9)
  except Exception:
    days = 9
  safe_days = max(days, 1)

  anchor = end_dt or datetime.now(timezone.utc)
  if anchor.tzinfo is None:
    anchor = anchor.replace(tzinfo=timezone.utc)
  anchor = anchor.astimezone(timezone.utc)
  token = str(os.getenv("DPR_RUN_DATE") or "").strip()

  if DATE_RE_RANGE.fullmatch(token):
    start_text, end_text = token.split("-", 1)
    try:
      start_dt = datetime.strptime(start_text, "%Y%m%d").replace(tzinfo=timezone.utc)
      end_day = datetime.strptime(end_text, "%Y%m%d").replace(tzinfo=timezone.utc)
      if end_day >= start_dt:
        return start_dt, end_day + timedelta(days=1)
    except Exception:
      pass

  if DATE_RE_DAY.fullmatch(token):
    day_start = datetime.strptime(token, "%Y%m%d").replace(tzinfo=timezone.utc)
    if safe_days > 1:
      return anchor - timedelta(days=safe_days), anchor
    return day_start, day_start + timedelta(days=1)

  return anchor - timedelta(days=safe_days), anchor


def group_start(title: str) -> None:
  print(f"::group::{title}", flush=True)


def group_end() -> None:
  print("::endgroup::", flush=True)


def tokenize(text: str) -> List[str]:
  """简单分词：英文按词，中文按单字。"""
  if not text:
    return []
  return TOKEN_RE.findall(text.lower())


@dataclass
class Paper:
  """用于 BM25 检索阶段的论文结构（只关心元数据和 tag）"""

  id: str
  title: str
  abstract: str
  authors: List[str]
  primary_category: str | None = None
  categories: List[str] = field(default_factory=list)
  published: str | None = None
  link: str | None = None
  source: str = "arxiv"
  tags: Set[str] = field(default_factory=set)

  @property
  def text_for_bm25(self) -> str:
    """用于 BM25 的文本：标题 + 摘要（带标签，便于结构化）"""
    title = (self.title or "").strip()
    abstract = (self.abstract or "").strip()
    if title and abstract:
      return f"Title: {title}\n\nAbstract: {abstract}"
    if title:
      return f"Title: {title}"
    if abstract:
      return f"Abstract: {abstract}"
    return ""

  def to_dict(self) -> Dict[str, Any]:
    """转换为可 JSON 序列化的字典"""
    return {
      "id": self.id,
      "source": self.source,
      "title": self.title,
      "abstract": self.abstract,
      "authors": self.authors,
      "primary_category": self.primary_category,
      "categories": self.categories,
      "published": self.published,
      "link": self.link,
      "tags": sorted(self.tags),
    }


class BM25Index:
  """轻量 BM25 实现，避免额外依赖。"""

  def __init__(self, tokenized_docs: List[List[str]], k1: float = 1.5, b: float = 0.75):
    self.k1 = k1
    self.b = b

    self.doc_len = [len(tokens) for tokens in tokenized_docs]
    self.avgdl = sum(self.doc_len) / max(len(self.doc_len), 1)
    self.doc_freqs: List[Dict[str, int]] = []
    self.idf: Dict[str, float] = {}
    self.inverted: Dict[str, List[tuple[int, int]]] = {}

    df: Dict[str, int] = {}
    for idx, tokens in enumerate(tokenized_docs):
      freqs: Dict[str, int] = {}
      for t in tokens:
        freqs[t] = freqs.get(t, 0) + 1
      self.doc_freqs.append(freqs)
      for t in freqs.keys():
        df[t] = df.get(t, 0) + 1
        self.inverted.setdefault(t, []).append((idx, freqs[t]))

    total_docs = len(tokenized_docs)
    for t, dfn in df.items():
      # 标准 BM25 IDF
      self.idf[t] = math.log(1 + (total_docs - dfn + 0.5) / (dfn + 0.5))

  def score(self, query_tokens: Iterable[str]) -> List[float]:
    scores = [0.0] * len(self.doc_len)
    if not self.doc_len:
      return scores

    q_tf: Dict[str, int] = {}
    for t in query_tokens:
      q_tf[t] = q_tf.get(t, 0) + 1

    for term, q_count in q_tf.items():
      idf = self.idf.get(term)
      if idf is None:
        continue
      postings = self.inverted.get(term, [])
      for doc_idx, tf in postings:
        dl = self.doc_len[doc_idx]
        denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
        score = idf * (tf * (self.k1 + 1) / denom) * q_count
        scores[doc_idx] += score

    return scores


def load_config() -> dict:
  """
  从仓库根目录读取 config.yaml。
  仅基于 intent_profiles 构建检索输入，不兼容 legacy 字段。
  """
  if not os.path.exists(CONFIG_FILE):
    log(f"[WARN] config.yaml 不存在：{CONFIG_FILE}")
    return {}

  try:
    data = load_config_with_source_migration(CONFIG_FILE, write_back=False)
    if isinstance(data, dict):
      return data
    log("[WARN] config.yaml 顶层结构不是字典，将忽略该配置文件。")
    return {}
  except Exception as e:
    log(f"[WARN] 读取 config.yaml 失败：{e}")
    return {}


def _query_text_for_supabase_bm25(q: dict) -> str:
  q_text = str(q.get("query_text") or "").strip()
  return q_text


def _format_supabase_window_for_log(
  start_dt: datetime | None,
  end_dt: datetime | None,
  time_fields: tuple[str, ...],
) -> tuple[str, str, str]:
  safe_fields = {str(f).strip() for f in (time_fields or ()) if str(f).strip()}
  if start_dt is None or end_dt is None:
    published = "N/A"
    updated = "N/A"
  else:
    window = f"{start_dt.isoformat()} ~ {end_dt.isoformat()}"
    published = window if "published" in safe_fields else "N/A"
    updated = window if "updated_at" in safe_fields else "N/A"
  return published, updated, ",".join(sorted(safe_fields))


def _normalize_utc_datetime(value: datetime | None) -> datetime | None:
  if not isinstance(value, datetime):
    return None
  if value.tzinfo is None:
    return value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc)


def split_supabase_time_window(
  start_dt: datetime | None,
  end_dt: datetime | None,
  *,
  shard_days: int = SUPABASE_BM25_SHARD_DAYS,
) -> list[tuple[datetime, datetime]]:
  """
  将较长时间窗口切成多个固定天数分片，避免单次 BM25 RPC 触发 statement timeout。
  """
  safe_start = _normalize_utc_datetime(start_dt)
  safe_end = _normalize_utc_datetime(end_dt)
  if safe_start is None or safe_end is None or safe_end <= safe_start:
    return []

  safe_shard_days = max(int(shard_days or 1), 1)
  step = timedelta(days=safe_shard_days)
  if safe_end - safe_start <= step:
    return [(safe_start, safe_end)]

  shards: list[tuple[datetime, datetime]] = []
  cursor = safe_start
  while cursor < safe_end:
    next_dt = min(cursor + step, safe_end)
    shards.append((cursor, next_dt))
    cursor = next_dt
  return shards


def _resolve_supabase_row_score(row: Dict[str, Any]) -> float:
  score_raw = row.get("score")
  if score_raw is None:
    score_raw = row.get("similarity")
  try:
    return float(score_raw)
  except Exception:
    return 0.0


def merge_supabase_bm25_rows(
  rows_per_shard: list[list[Dict[str, Any]]],
  *,
  top_k: int,
) -> list[Dict[str, Any]]:
  """
  合并多个分片的 BM25 结果：
  - 按 id 去重；
  - 同一论文跨分片重复出现时保留更高分；
  - 最终按 score 降序截断到 top_k。
  """
  merged_by_id: Dict[str, Dict[str, Any]] = {}

  for shard_idx, rows in enumerate(rows_per_shard):
    for local_rank, row in enumerate(rows, start=1):
      if not isinstance(row, dict):
        continue
      pid = str(row.get("id") or "").strip()
      if not pid:
        continue
      score = _resolve_supabase_row_score(row)
      existing = merged_by_id.get(pid)
      should_replace = False
      if existing is None:
        should_replace = True
      else:
        old_score = float(existing.get("_merged_score") or 0.0)
        old_shard_idx = int(existing.get("_merged_shard_idx") or 0)
        old_local_rank = int(existing.get("_merged_local_rank") or 0)
        if score > old_score:
          should_replace = True
        elif score == old_score and (
          shard_idx < old_shard_idx
          or (shard_idx == old_shard_idx and local_rank < old_local_rank)
        ):
          should_replace = True

      if not should_replace:
        continue

      normalized = dict(row)
      normalized["_merged_score"] = score
      normalized["_merged_shard_idx"] = shard_idx
      normalized["_merged_local_rank"] = local_rank
      merged_by_id[pid] = normalized

  merged = sorted(
    merged_by_id.values(),
    key=lambda item: (
      -float(item.get("_merged_score") or 0.0),
      int(item.get("_merged_shard_idx") or 0),
      int(item.get("_merged_local_rank") or 0),
      str(item.get("id") or ""),
    ),
  )
  if top_k > 0:
    merged = merged[:top_k]

  for item in merged:
    item.pop("_merged_score", None)
    item.pop("_merged_shard_idx", None)
    item.pop("_merged_local_rank", None)
  return merged


def _query_supabase_bm25_window(
  *,
  url: str,
  api_key: str,
  rpc_name: str,
  query_text: str,
  match_count: int,
  schema: str,
  start_dt: datetime,
  end_dt: datetime,
  time_fields: tuple[str, ...],
  shard_days: int,
  min_shard_days: int = 1,
  depth: int = 0,
  filter_sources: List[str] | None = None,
) -> tuple[list[list[Dict[str, Any]]], int, list[str]]:
  rows, msg = match_papers_by_bm25(
    url=url,
    api_key=api_key,
    rpc_name=rpc_name,
    query_text=query_text,
    match_count=match_count,
    schema=schema,
    start_dt=start_dt,
    end_dt=end_dt,
    time_fields=time_fields,
    filter_sources=filter_sources,
  )
  window = f"{start_dt.isoformat()} ~ {end_dt.isoformat()}"
  log(
    "[Supabase BM25] "
    f"depth={depth} "
    f"window={window} "
    f"{msg}"
  )
  if msg.startswith("rpc 查询成功"):
    return ([rows], 1, [])

  failure_message = f"depth={depth} window={window} {msg}"
  safe_start = _normalize_utc_datetime(start_dt)
  safe_end = _normalize_utc_datetime(end_dt)
  if safe_start is None or safe_end is None or safe_end <= safe_start:
    return ([], 0, [failure_message])
  if "57014" not in msg:
    return ([], 0, [failure_message])

  span_seconds = max((safe_end - safe_start).total_seconds(), 0.0)
  span_days = max(int(math.ceil(span_seconds / 86400.0)), 1)
  safe_min_shard_days = max(int(min_shard_days or 1), 1)
  if span_days <= safe_min_shard_days:
    return ([], 0, [failure_message])

  next_shard_days = max(span_days // 2, safe_min_shard_days)
  if shard_days > 1:
    next_shard_days = min(next_shard_days, shard_days - 1)
  if next_shard_days >= span_days:
    next_shard_days = span_days - 1
  if next_shard_days < safe_min_shard_days:
    next_shard_days = safe_min_shard_days
  if next_shard_days >= span_days:
    return ([], 0, [failure_message])

  sub_shards = split_supabase_time_window(
    safe_start,
    safe_end,
    shard_days=next_shard_days,
  )
  if len(sub_shards) <= 1:
    return ([], 0, [failure_message])

  log(
    "[Supabase BM25] "
    f"timeout fallback window={window} "
    f"split_to={len(sub_shards)} "
    f"sub_shard_days={next_shard_days}"
  )

  rows_per_shard: list[list[Dict[str, Any]]] = []
  success_count = 0
  failure_messages: list[str] = []
  for sub_start, sub_end in sub_shards:
    sub_rows, sub_success, sub_failures = _query_supabase_bm25_window(
      url=url,
      api_key=api_key,
      rpc_name=rpc_name,
      query_text=query_text,
      match_count=match_count,
      schema=schema,
      start_dt=sub_start,
      end_dt=sub_end,
      time_fields=time_fields,
      shard_days=next_shard_days,
      min_shard_days=safe_min_shard_days,
      depth=depth + 1,
      filter_sources=filter_sources,
    )
    rows_per_shard.extend(sub_rows)
    success_count += sub_success
    failure_messages.extend(sub_failures)
  if success_count > 0:
    return (rows_per_shard, success_count, failure_messages)
  return ([], 0, [failure_message, *failure_messages])


def query_supabase_bm25_with_shards(
  *,
  url: str,
  api_key: str,
  rpc_name: str,
  query_text: str,
  match_count: int,
  schema: str,
  start_dt: datetime | None,
  end_dt: datetime | None,
  time_fields: tuple[str, ...],
  shard_days: int = SUPABASE_BM25_SHARD_DAYS,
  filter_sources: List[str] | None = None,
) -> tuple[list[Dict[str, Any]], str]:
  safe_start = _normalize_utc_datetime(start_dt)
  safe_end = _normalize_utc_datetime(end_dt)
  if safe_start is None or safe_end is None or safe_end <= safe_start:
    return match_papers_by_bm25(
      url=url,
      api_key=api_key,
      rpc_name=rpc_name,
      query_text=query_text,
      match_count=match_count,
      schema=schema,
      start_dt=start_dt,
      end_dt=end_dt,
      time_fields=time_fields,
      filter_sources=filter_sources,
    )

  shards = split_supabase_time_window(
    safe_start,
    safe_end,
    shard_days=shard_days,
  )
  if not shards:
    return ([], "rpc 分片查询失败：未生成有效时间分片")

  rows_per_shard: list[list[Dict[str, Any]]] = []
  success_count = 0
  failure_messages: list[str] = []

  for shard_start, shard_end in shards:
    sub_rows, sub_success, sub_failures = _query_supabase_bm25_window(
      url=url,
      api_key=api_key,
      rpc_name=rpc_name,
      query_text=query_text,
      match_count=match_count,
      schema=schema,
      start_dt=shard_start,
      end_dt=shard_end,
      time_fields=time_fields,
      shard_days=max(int(shard_days or 1), 1),
      filter_sources=filter_sources,
    )
    rows_per_shard.extend(sub_rows)
    success_count += sub_success
    failure_messages.extend(sub_failures)

  merged_rows = merge_supabase_bm25_rows(
    rows_per_shard,
    top_k=max(int(match_count or 1), 1),
  )
  if success_count <= 0:
    detail = " | ".join(failure_messages[:2]) if failure_messages else "所有分片均失败"
    return ([], f"rpc 分片查询失败：success=0/{len(shards)} | {detail}")

  summary = (
    f"rpc 分片查询成功：{len(merged_rows)} 条"
    f"（initial_shards={len(shards)} success_windows={success_count} failed_windows={len(failure_messages)}）"
  )
  if failure_messages:
    summary += f" | partial_failures={len(failure_messages)}"
  return (merged_rows, summary)


def load_paper_pool(path: str) -> List[Paper]:
  """
  读取 arxiv_fetch_raw.py 生成的 JSON：
  期望结构为 [ { id, title, abstract, authors, primary_category, categories, published, link }, ... ]
  """
  if not os.path.exists(path):
    raise FileNotFoundError(f"找不到论文池文件：{path}")

  with open(path, "r", encoding="utf-8") as f:
    raw = json.load(f)

  papers: List[Paper] = []
  for item in raw:
    try:
      p = Paper(
        id=str(item.get("id") or "").strip(),
        source=str(item.get("source") or "arxiv").strip() or "arxiv",
        title=str(item.get("title") or "").strip(),
        abstract=str(item.get("abstract") or "").strip(),
        authors=[str(a) for a in (item.get("authors") or [])],
        primary_category=str(item.get("primary_category") or "") or None,
        categories=[str(c) for c in (item.get("categories") or [])],
        published=str(item.get("published") or "") or None,
        link=str(item.get("link") or "") or None,
      )
      if p.id:
        papers.append(p)
    except Exception as e:
      log(f"[WARN] 解析论文条目失败，将跳过：{e}")

  log(f"[INFO] 从 {path} 读取到 {len(papers)} 篇论文。")
  return papers


def build_bm25_index(papers: List[Paper], k1: float = 1.5, b: float = 0.75) -> BM25Index:
  docs = [p.text_for_bm25 for p in papers]
  tokenized = [tokenize(d) for d in docs]
  return BM25Index(tokenized_docs=tokenized, k1=k1, b=b)


def estimate_dynamic_top_k(total_papers: int | None) -> int:
  try:
    total = int(total_papers or 0)
  except Exception:
    total = 0
  if total <= 0:
    return 50
  blocks = (total - 1) // 1000
  return 50 * (blocks + 1)


def multi_source_rpc_enabled() -> bool:
  return str(os.getenv("DPR_ENABLE_MULTI_SOURCE_RPC") or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_multi_source_bm25_backend(config: Dict[str, Any], queries: List[dict]) -> Dict[str, Any] | None:
  all_sources: List[str] = []
  for query in queries or []:
    all_sources.extend(normalize_source_list(query.get("paper_sources")))
  all_sources = normalize_source_list(all_sources)
  if len(all_sources) <= 1:
    return None

  backends = []
  for source_key in all_sources:
    backend = get_source_backend(config, source_key)
    if not backend:
      return None
    backends.append(backend)
  if not backends:
    return None

  first = backends[0]
  first_key = (
    str(first.get("url") or "").strip(),
    str(first.get("anon_key") or "").strip(),
    str(first.get("schema") or "public").strip(),
  )
  if not all(
    (
      str(item.get("url") or "").strip(),
      str(item.get("anon_key") or "").strip(),
      str(item.get("schema") or "public").strip(),
    ) == first_key
    for item in backends[1:]
  ):
    return None
  if not all(bool(item.get("use_bm25_rpc")) for item in backends):
    return None

  return {
    "enabled": True,
    "use_bm25_rpc": True,
    "url": first_key[0],
    "anon_key": first_key[1],
    "schema": first_key[2],
    "bm25_rpc": str(os.getenv("DPR_MULTI_SOURCE_BM25_RPC") or "match_multi_source_papers_bm25").strip(),
  }


def rank_papers_for_queries_via_supabase(
  queries: List[dict],
  top_k: int,
  supabase_conf: Dict[str, Any],
  *,
  start_dt: datetime | None = None,
  end_dt: datetime | None = None,
  time_fields: tuple[str, ...] = SUPABASE_TIME_FIELDS,
  query_filter_sources: bool = False,
) -> dict:
  if not queries:
    return {"queries": [], "papers": {}, "total_hits": 0}

  url = str(supabase_conf.get("url") or "").strip()
  api_key = str(supabase_conf.get("anon_key") or "").strip()
  rpc_name = str(supabase_conf.get("bm25_rpc") or "match_arxiv_papers_bm25").strip()
  schema = str(supabase_conf.get("schema") or "public").strip()
  if not url or not api_key:
    return {"queries": [], "papers": {}, "total_hits": 0}

  id_to_paper: Dict[str, Paper] = {}
  results_per_query: List[dict] = []
  total_hits = 0

  for q_idx, q in enumerate(queries, start=1):
    q_text = _query_text_for_supabase_bm25(q)
    paper_tag = str(q.get("paper_tag") or "").strip()
    if not q_text:
      continue

    published_window, updated_window, window_fields = _format_supabase_window_for_log(
      start_dt=start_dt,
      end_dt=end_dt,
      time_fields=time_fields,
    )
    log(
      "[Supabase BM25] "
      f"batch={q_idx} tag={q.get('tag') or ''} "
      f"type={q.get('type') or ''} "
      f"published_window={published_window} "
      f"updated_window={updated_window} "
      f"time_fields={window_fields}"
    )

    rows, msg = query_supabase_bm25_with_shards(
      url=url,
      api_key=api_key,
      rpc_name=rpc_name,
      query_text=q_text,
      match_count=max(int(top_k or 1), 1),
      schema=schema,
      start_dt=start_dt,
      end_dt=end_dt,
      time_fields=time_fields,
      filter_sources=normalize_source_list(q.get("paper_sources")) if query_filter_sources else None,
    )
    log(f"[Supabase BM25] {msg} | tag={q.get('tag') or ''}")

    sim_scores: Dict[str, Dict[str, float | int]] = {}
    for rank_idx, row in enumerate(rows, start=1):
      pid = str(row.get("id") or "").strip()
      if not pid:
        continue
      score = _resolve_supabase_row_score(row)
      sim_scores[pid] = {"score": score, "rank": rank_idx}
      total_hits += 1

      if pid not in id_to_paper:
        id_to_paper[pid] = Paper(
          id=pid,
          source=str(row.get("source") or q.get("active_source") or "supabase").strip() or "supabase",
          title=str(row.get("title") or "").strip(),
          abstract=str(row.get("abstract") or "").strip(),
          authors=[str(a) for a in (row.get("authors") or [])],
          primary_category=str(row.get("primary_category") or "") or None,
          categories=[str(c) for c in (row.get("categories") or [])],
          published=str(row.get("published") or "") or None,
          link=str(row.get("link") or "") or None,
        )
      if paper_tag:
        id_to_paper[pid].tags.add(paper_tag)

    results_per_query.append(
      {
        "type": q.get("type"),
        "tag": q.get("tag"),
        "paper_tag": q.get("paper_tag"),
        "paper_sources": q.get("paper_sources") or [q.get("active_source") or ARXIV_SOURCE_KEY],
        "query_text": q_text,
        "logic_cn": q.get("logic_cn") or "",
        "boolean_expr": q.get("boolean_expr") or "",
        "bm25_mode": "supabase",
        "sim_scores": sim_scores,
      }
    )

  return {
    "queries": results_per_query,
    "papers": id_to_paper,
    "total_hits": total_hits,
  }


def score_boolean_mixed_for_query(
  bm25: BM25Index,
  papers: List[Paper],
  expr: str,
  or_soft_weight: float = DEFAULT_OR_SOFT_WEIGHT,
  must_have: List[str] | None = None,
  optional: List[str] | None = None,
  exclude: List[str] | None = None,
) -> List[float]:
  """
  BM25 布尔混合模式：
  - AND/NOT：硬约束（不过滤则直接淘汰）；
  - OR：同一论文命中多个分支时做软增强。
  """
  parsed = parse_boolean_expr(expr)
  if parsed is None:
    fallback_text = clean_expr_for_embedding(expr) or expr
    return bm25.score(tokenize(fallback_text))

  branches = split_or_branches(parsed)
  if not branches:
    fallback_text = clean_expr_for_embedding(expr) or expr
    return bm25.score(tokenize(fallback_text))

  branch_terms: List[List[str]] = [collect_unique_positive_terms(b) for b in branches]
  term_score_cache: Dict[str, List[float]] = {}
  for terms in branch_terms:
    for term in terms:
      key = term.lower()
      if key in term_score_cache:
        continue
      term_score_cache[key] = bm25.score(tokenize(term))

  must_list = [str(x).strip() for x in (must_have or []) if str(x).strip()]
  optional_list = [str(x).strip() for x in (optional or []) if str(x).strip()]
  exclude_list = [str(x).strip() for x in (exclude or []) if str(x).strip()]

  scores = [-1.0] * len(papers)
  for idx, paper in enumerate(papers):
    title = paper.title or ""
    abstract = paper.abstract or ""
    authors = paper.authors or []

    if must_list:
      if not all(match_term(t, title, abstract, authors) for t in must_list):
        continue
    if exclude_list:
      if any(match_term(t, title, abstract, authors) for t in exclude_list):
        continue

    passed_branch_scores: List[float] = []
    for b_idx, branch in enumerate(branches):
      if not evaluate_expr(branch, title, abstract, authors):
        continue
      terms = branch_terms[b_idx]
      if terms:
        branch_score = sum(term_score_cache[t.lower()][idx] for t in terms) / max(len(terms), 1)
      else:
        branch_score = 1.0
      passed_branch_scores.append(float(branch_score))

    if not passed_branch_scores:
      continue

    base = max(passed_branch_scores)
    extra = max(sum(passed_branch_scores) - base, 0.0)
    score = base + float(or_soft_weight) * extra

    if optional_list:
      hits = sum(1 for t in optional_list if match_term(t, title, abstract, authors))
      if hits > 0:
        score += 0.1 * hits / len(optional_list)

    scores[idx] = float(score)

  return scores


def rank_papers_for_queries(
  bm25: BM25Index,
  papers: List[Paper],
  queries: List[dict],
  top_k: int = 50,
) -> dict:
  """
  对每个查询分别进行 BM25 排序：
  - 使用 query_text 分词，与所有论文做 BM25 打分；
  - 取分数最高的前 top_k 篇论文，记录 arxiv_id；
  - 为这些论文打上 tag（tag），一篇论文可拥有多个 tag；
  - 返回结构包含：
    {
      "queries": [ { type, tag, query_text, paper_tag, sim_scores: {paper_id: {score, rank}} }, ... ],
      "papers": { paper_id: Paper(...) }
    }
  """
  if not queries:
    log("[WARN] 未从 config.yaml 中解析到任何查询（intent_profiles），将直接返回空结果。")
    return {"queries": [], "papers": {}}

  paper_ids = [p.id for p in papers]
  id_to_paper: Dict[str, Paper] = {p.id: p for p in papers}

  results_per_query: List[dict] = []

  for q in queries:
    q_text = _query_text_for_supabase_bm25(q)
    paper_tag = q.get("paper_tag") or ""
    if not q_text:
      continue

    log(f"[INFO] BM25 处理查询（{q.get('type')}）：tag={q.get('tag') or ''}")

    scores: List[float] | None = None
    total_weight = 0.0
    query_terms = q.get("query_terms") or []
    query_mode = "normal"

    if isinstance(query_terms, list) and query_terms:
      for term in query_terms:
        if not isinstance(term, dict):
          continue
        term_text = (term.get("text") or "").strip()
        weight = float(term.get("weight", 1.0))
        if not term_text or weight <= 0:
          continue
        term_scores = bm25.score(tokenize(term_text))
        if scores is None:
          scores = [0.0] * len(term_scores)
        for i, s in enumerate(term_scores):
          scores[i] += weight * s
        total_weight += weight

    if scores is None:
      scores = bm25.score(tokenize(q_text))
      total_weight = 1.0

    if total_weight > 0:
      scores = [s / total_weight for s in scores]
    candidate_indices = list(range(len(scores)))

    if top_k <= 0 or top_k > len(candidate_indices):
      k = len(candidate_indices)
    else:
      k = top_k

    indices = sorted(candidate_indices, key=lambda i: scores[i], reverse=True)[:k]
    sim_scores: Dict[str, Dict[str, float | int]] = {}
    for rank_idx, idx in enumerate(indices, start=1):
      pid = paper_ids[idx]
      score = float(scores[idx])
      sim_scores[pid] = {"score": score, "rank": rank_idx}
      if paper_tag:
        id_to_paper[pid].tags.add(paper_tag)

    results_per_query.append(
      {
        "type": q.get("type"),
        "tag": q.get("tag"),
        "paper_tag": q.get("paper_tag"),
        "paper_sources": q.get("paper_sources") or [ARXIV_SOURCE_KEY],
        "query_text": q_text,
        "logic_cn": q.get("logic_cn") or "",
        "boolean_expr": "",
        "bm25_mode": query_mode,
        "sim_scores": sim_scores,
      }
    )

  return {
    "queries": results_per_query,
    "papers": id_to_paper,
  }


def save_tagged_results(
  result: dict,
  output_path: str,
) -> None:
  """
  将结果写入 JSON：
  {
    "top_k": ...,
    "generated_at": "...",
    "queries": [ { type, tag, paper_tag, query_text, sim_scores: {...} }, ... ],
    "papers": [ { id, title, abstract, ..., tags: [...] }, ... ]  // 仅保留至少有一个 tag 的论文
  }
  """
  from datetime import datetime, timezone

  os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

  id_to_paper: Dict[str, Paper] = result.get("papers") or {}
  tagged_papers = [p.to_dict() for p in id_to_paper.values() if p.tags]

  q_list = result.get("queries") or []
  if q_list:
    q0 = q_list[0]
    sim_scores = q0.get("sim_scores") or {}
    inferred_top_k = len(sim_scores) if isinstance(sim_scores, dict) else 0
  else:
    inferred_top_k = 0

  payload = {
    "top_k": inferred_top_k,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "papers": tagged_papers,
    "queries": result.get("queries") or [],
  }

  with open(output_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

  log(f"[INFO] 已将带 tag 的论文和每个查询的 top_k 结果写入：{output_path}")
  log(f"[INFO] 其中带 tag 的论文数：{len(tagged_papers)}")


def main() -> None:
  parser = argparse.ArgumentParser(
    description="步骤 2.1：使用 BM25 对 ArXiv 论文池做关键词 / LLM 查询检索并打 tag。",
  )
  parser.add_argument(
    "--input",
    type=str,
    default=None,
    help="可选：只处理指定的原始 JSON 文件；省略时将批量处理 archive/YYYYMMDD/raw 目录下所有 .json 文件。",
  )
  parser.add_argument(
    "--output",
    type=str,
    default=None,
    help="可选：当使用 --input 处理单个文件时，自定义输出 JSON 路径；批处理模式下将自动写入 archive/YYYYMMDD/filtered 目录，默认后缀 .bm25.json。",
  )
  parser.add_argument(
    "--top-k",
    type=int,
    default=None,
    help="每个查询保留的 Top K 论文数；未指定时根据原始论文总数自适应：<=1000 篇取 50，每增加 1000 篇增加 50。",
  )
  parser.add_argument(
    "--k1",
    type=float,
    default=1.5,
    help="BM25 k1 参数（默认 1.5）。",
  )
  parser.add_argument(
    "--b",
    type=float,
    default=0.75,
    help="BM25 b 参数（默认 0.75）。",
  )
  parser.add_argument(
    "--disable-supabase-bm25",
    action="store_true",
    help="关闭 Supabase BM25 召回，强制使用本地 BM25 索引。",
  )

  args = parser.parse_args()

  config = load_config()
  supabase_conf = get_supabase_read_config(config)
  sb_start_dt, sb_end_dt = resolve_supabase_recall_window(config)
  log(
    "[INFO] Supabase BM25 召回窗口："
    f"{sb_start_dt.isoformat()} ~ {sb_end_dt.isoformat()} "
    f"(time_fields={','.join(SUPABASE_TIME_FIELDS)})"
  )
  pipeline_inputs = build_pipeline_inputs(config)
  queries = pipeline_inputs.get("bm25_queries") or []
  comparison = pipeline_inputs.get("comparison") or {}
  if comparison:
    log(
      "[INFO] 迁移阶段A输入对比："
      f"bm25_only_new={comparison.get('bm25_only_new_count', 0)} "
      f"bm25_only_legacy={comparison.get('bm25_only_legacy_count', 0)} "
      f"embedding_only_new={comparison.get('embedding_only_new_count', 0)} "
      f"embedding_only_legacy={comparison.get('embedding_only_legacy_count', 0)}"
    )
  if not queries:
    log("[ERROR] 未能从订阅配置中解析到 BM25 查询，退出。")
    return

  query_groups = group_queries_by_source(queries)
  for source_key in query_groups:
    if source_key == ARXIV_SOURCE_KEY:
      continue
    if not get_source_backend(config, source_key):
      log(f"[ERROR] 词条引用了论文源「{source_key}」，但未配置 source_backends.{source_key}。")
      return
  multi_source_backend = resolve_multi_source_bm25_backend(config, queries) if multi_source_rpc_enabled() else None

  def run_supabase_rank_for_source(output_path: str, source_key: str, source_queries: List[dict]) -> dict | None:
    backend_conf = supabase_conf if source_key == ARXIV_SOURCE_KEY else get_source_backend(config, source_key)
    backend_enabled = (
      bool(backend_conf.get("enabled"))
      and bool(backend_conf.get("use_bm25_rpc"))
      and not bool(args.disable_supabase_bm25)
    )
    if not source_queries:
      return None
    if not backend_enabled:
      if source_key == ARXIV_SOURCE_KEY:
        return None
      raise RuntimeError(f"论文源「{source_key}」未配置可用的 BM25 RPC。")

    label = os.path.basename(output_path)
    if args.top_k is None or args.top_k <= 0:
      count_value, count_msg = count_papers_by_date_range(
        url=str(backend_conf.get("url") or "").strip(),
        api_key=str(backend_conf.get("anon_key") or "").strip(),
        papers_table=str(backend_conf.get("papers_table") or "papers").strip(),
        start_dt=sb_start_dt,
        end_dt=sb_end_dt,
        schema=str(backend_conf.get("schema") or "public").strip(),
      )
      log(f"[INFO] Supabase BM25 窗口计数（source={source_key}）：{count_msg}")
      dynamic_top_k = estimate_dynamic_top_k(count_value)
      log(
        f"[INFO] Supabase BM25 自适应 Top K = {dynamic_top_k} "
        f"(source={source_key}, window_count={count_value if count_value is not None else 'unknown'})，"
        f"输出文件：{label}"
      )
    else:
      dynamic_top_k = args.top_k
      log(f"[INFO] Supabase BM25 使用命令行指定的 Top K = {dynamic_top_k}，source={source_key}，输出文件：{label}")

    group_start(f"Step 2.1 - supabase bm25 recall ({source_key}:{label})")
    try:
      result_sb = rank_papers_for_queries_via_supabase(
        queries=source_queries,
        top_k=dynamic_top_k,
        supabase_conf=backend_conf,
        start_dt=sb_start_dt,
        end_dt=sb_end_dt,
        time_fields=SUPABASE_TIME_FIELDS,
      )
      total_hits = int(result_sb.get("total_hits") or 0)
      if total_hits > 0:
        log(f"[INFO] Supabase BM25 命中 {total_hits} 条（source={source_key}）。")
      else:
        log(f"[WARN] Supabase BM25 未命中（source={source_key}）。")
      return result_sb
    except Exception as e:
      if source_key == ARXIV_SOURCE_KEY:
        log(f"[WARN] Supabase BM25 异常，将回退本地 BM25：{e}")
        return None
      raise
    finally:
      group_end()

  def run_multi_source_supabase_rank(output_path: str, source_queries: List[dict]) -> dict | None:
    if not multi_source_backend:
      return None
    label = os.path.basename(output_path)
    count_value, count_msg = count_papers_by_date_range(
      url=str(multi_source_backend.get("url") or "").strip(),
      api_key=str(multi_source_backend.get("anon_key") or "").strip(),
      papers_table="multi_source_papers",
      start_dt=sb_start_dt,
      end_dt=sb_end_dt,
      schema=str(multi_source_backend.get("schema") or "public").strip(),
    )
    log(f"[INFO] Multi-source BM25 窗口计数：{count_msg}")
    dynamic_top_k = args.top_k if isinstance(args.top_k, int) and args.top_k > 0 else estimate_dynamic_top_k(count_value)
    group_start(f"Step 2.1 - multi-source bm25 recall ({label})")
    try:
      result_sb = rank_papers_for_queries_via_supabase(
        queries=source_queries,
        top_k=dynamic_top_k,
        supabase_conf=multi_source_backend,
        start_dt=sb_start_dt,
        end_dt=sb_end_dt,
        time_fields=SUPABASE_TIME_FIELDS,
        query_filter_sources=True,
      )
      total_hits = int(result_sb.get("total_hits") or 0)
      if total_hits > 0:
        log(f"[INFO] Multi-source BM25 命中 {total_hits} 条。")
        return result_sb
      log("[WARN] Multi-source BM25 未命中。")
      return None
    finally:
      group_end()

  def process_single_file(input_path: str, output_path: str) -> None:
    merged_results: List[dict] = []
    if multi_source_backend:
      multi_source_result = run_multi_source_supabase_rank(output_path, queries)
      if multi_source_result:
        save_tagged_results(multi_source_result, output_path)
        return

    arxiv_queries = query_groups.get(ARXIV_SOURCE_KEY) or []
    arxiv_supabase_result = run_supabase_rank_for_source(output_path, ARXIV_SOURCE_KEY, arxiv_queries)
    arxiv_hits = int((arxiv_supabase_result or {}).get("total_hits") or 0)
    if arxiv_supabase_result and arxiv_hits > 0:
      merged_results.append(arxiv_supabase_result)

    for source_key, source_queries in query_groups.items():
      if source_key == ARXIV_SOURCE_KEY:
        continue
      result_sb = run_supabase_rank_for_source(output_path, source_key, source_queries)
      if result_sb:
        merged_results.append(result_sb)

    need_local_arxiv = bool(arxiv_queries) and arxiv_hits <= 0
    if need_local_arxiv:
      papers = load_paper_pool(input_path)
      if not papers:
        log(f"[ERROR] 论文池为空，且 arxiv 查询无法从 Supabase 命中：{input_path}")
      else:
        total_papers = len(papers)
        if args.top_k is None or args.top_k <= 0:
          dynamic_top_k = estimate_dynamic_top_k(total_papers)
          log(
            f"[INFO] 文件 {os.path.basename(input_path)} 原始论文数为 {total_papers} 篇，"
            f"自适应设置每个查询 Top K = {dynamic_top_k}。"
          )
        else:
          dynamic_top_k = args.top_k
          log(
            f"[INFO] 文件 {os.path.basename(input_path)} 使用命令行指定的 Top K = {dynamic_top_k}，"
            f"原始论文数为 {total_papers} 篇。"
          )

        group_start(f"Step 2.1 - build BM25 index ({os.path.basename(input_path)})")
        log(f"[INFO] 正在为 {total_papers} 篇论文构建 BM25 索引...")
        bm25 = build_bm25_index(papers, k1=float(args.k1), b=float(args.b))
        group_end()

        group_start(f"Step 2.1 - rank queries ({os.path.basename(input_path)})")
        result_local = rank_papers_for_queries(
          bm25=bm25,
          papers=papers,
          queries=arxiv_queries,
          top_k=dynamic_top_k,
        )
        group_end()
        merged_results.append(result_local)

    merged = merge_pipeline_results(merged_results)
    if not merged.get("queries"):
      log(f"[WARN] 当前文件没有产出任何 BM25 结果：{input_path}")
      return
    save_tagged_results(merged, output_path)

  if args.input:
    input_path = args.input
    if not os.path.isabs(input_path):
      input_path = os.path.abspath(os.path.join(ROOT_DIR, input_path))
    if not os.path.exists(input_path):
      log(f"[ERROR] 指定的输入文件不存在：{input_path}")
      return

    if args.output:
      output_path = args.output
      if not os.path.isabs(output_path):
        output_path = os.path.abspath(os.path.join(ROOT_DIR, output_path))
    else:
      base = os.path.basename(input_path)
      if base.lower().endswith(".json"):
        base = base[:-5]
      output_path = os.path.join(FILTERED_DIR, f"{base}.bm25.json")

    process_single_file(input_path, output_path)
  else:
    if os.path.isdir(RAW_DIR):
      raw_files = sorted(f for f in os.listdir(RAW_DIR) if f.lower().endswith(".json"))
    else:
      raw_files = []

    if not raw_files:
      output_path = os.path.join(FILTERED_DIR, f"arxiv_papers_{TODAY_STR}.bm25.json")
      if multi_source_backend:
        multi_source_result = run_multi_source_supabase_rank(output_path, queries)
        if multi_source_result:
          save_tagged_results(multi_source_result, output_path)
          return
      merged_results: List[dict] = []
      for source_key, source_queries in query_groups.items():
        result_sb = run_supabase_rank_for_source(output_path, source_key, source_queries)
        if result_sb:
          merged_results.append(result_sb)
      if merged_results:
        save_tagged_results(merge_pipeline_results(merged_results), output_path)
      else:
        log("[WARN] 无本地原始文件，且没有任何 source backend 返回结果。")
      return

    log(f"[INFO] 批量模式：将在 {RAW_DIR} 下处理 {len(raw_files)} 个 JSON 文件。")
    for name in raw_files:
      input_path = os.path.join(RAW_DIR, name)
      base = name
      if base.lower().endswith(".json"):
        base = base[:-5]
      output_path = os.path.join(FILTERED_DIR, f"{base}.bm25.json")
      process_single_file(input_path, output_path)


if __name__ == "__main__":
  main()
