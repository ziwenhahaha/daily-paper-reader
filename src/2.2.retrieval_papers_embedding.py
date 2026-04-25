#!/usr/bin/env python
# 基于全量 ArXiv 元数据池做二次筛选：
# 1. 读取 arxiv_fetch_raw.py 生成的 JSON（所有论文）；
# 2. 使用 sentence-transformers 将「标题 + 摘要」编码为向量；
# 3. 使用 config.yaml 中的 intent_profiles -> keywords / intent_queries 作为查询，计算相似度；
# 4. 每个查询保留前 top_k 篇论文，并为这些论文打上 tag（tag），一篇论文可拥有多个 tag；
# 5. 将带 tag 的论文列表和每个查询的 top_k arxiv_id 写回到一个新的 JSON 文件中。

import argparse
import json
import os
import math
import hashlib
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional, Callable
import re

import numpy as np

from filter import E5_QUERY_PREFIX, EmbeddingCoarseFilter, encode_queries
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
  match_papers_by_embedding,
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
SUPABASE_VECTOR_SHARD_DAYS = 7
EMBEDDING_CACHE_VERSION = 1
EMBEDDING_CACHE_FIELD = "embedding_cache"
LEGACY_EMBEDDING_CACHE_KEY = "embedding_cache"

def log(message: str) -> None:
  ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
  print(f"[{ts}] {message}", flush=True)


def multi_source_rpc_enabled() -> bool:
  return str(os.getenv("DPR_ENABLE_MULTI_SOURCE_RPC") or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_multi_source_vector_backend(config: Dict[str, Any], queries: List[dict]) -> Dict[str, Any] | None:
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
  if not all(bool(item.get("use_vector_rpc")) for item in backends):
    return None

  rpc_name = str(os.getenv("DPR_MULTI_SOURCE_VECTOR_RPC_EXACT") or "match_multi_source_papers_exact").strip()
  return {
    "enabled": True,
    "use_vector_rpc": True,
    "url": first_key[0],
    "anon_key": first_key[1],
    "schema": first_key[2],
    "vector_rpc": rpc_name,
    "vector_rpc_exact": rpc_name,
  }


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


@dataclass
class Paper:
  """用于向量检索阶段的论文结构（只关心元数据和 tag）"""

  id: str
  title: str
  abstract: str
  authors: List[str]
  primary_category: str | None = None
  categories: List[str] = field(default_factory=list)
  published: str | None = None
  link: str | None = None
  source: str = "arxiv"
  embedding: Optional[np.ndarray] = None
  embedding_model: str = ""
  tags: Set[str] = field(default_factory=set)

  @property
  def text_for_embedding(self) -> str:
    """用于向量化的文本：E5 passage 前缀 + 标题/摘要"""
    title = (self.title or "").strip()
    abstract = (self.abstract or "").strip()
    if title and abstract:
      return f"passage: Title: {title}\n\nAbstract: {abstract}"
    if title:
      return f"passage: Title: {title}"
    if abstract:
      return f"passage: Abstract: {abstract}"
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
      # tags 输出为去重后的列表
      "tags": sorted(self.tags),
    }


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


def build_prefixed_query_text(text: str) -> str:
  value = str(text or "").strip()
  if not value:
    return ""
  return f"{E5_QUERY_PREFIX}{value}"


def build_query_embedding_hash(model_name: str, query_text: str) -> str:
  payload = f"v1|{str(model_name or '').strip().lower()}|{build_prefixed_query_text(query_text)}"
  return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _remove_legacy_embedding_cache(config: Dict[str, Any]) -> None:
  if not isinstance(config, dict):
    return
  subs = config.get("subscriptions")
  if not isinstance(subs, dict):
    return
  legacy = subs.get(LEGACY_EMBEDDING_CACHE_KEY)
  if isinstance(legacy, dict) and "query_vectors" in legacy:
    subs.pop(LEGACY_EMBEDDING_CACHE_KEY, None)


def _parse_cached_query_embedding(entry: Dict[str, Any], expected_model: str, expected_text: str) -> Optional[np.ndarray]:
  if not isinstance(entry, dict):
    return None
  stored_model = str(entry.get("model") or "").strip().lower()
  if stored_model and stored_model != str(expected_model or "").strip().lower():
    return None
  stored_text = str(entry.get("prefixed_text") or "").strip()
  if stored_text and stored_text != expected_text:
    return None

  raw_embedding = entry.get("embedding_json")
  if isinstance(raw_embedding, str) and raw_embedding.strip():
    try:
      loaded = json.loads(raw_embedding)
      if isinstance(loaded, list):
        raw_embedding = loaded
    except Exception:
      return None

  if not isinstance(raw_embedding, list) or not raw_embedding:
    raw_embedding = entry.get("embedding")
  if not isinstance(raw_embedding, list) or not raw_embedding:
    return None
  try:
    vec = np.asarray([float(x) for x in raw_embedding], dtype=np.float32)
  except Exception:
    return None
  if vec.ndim != 1 or vec.shape[0] <= 0:
    return None
  return vec


def save_config_with_embedding_cache(config: Dict[str, Any], path: str = CONFIG_FILE) -> bool:
  try:
    import yaml  # type: ignore
  except Exception:
    log("[WARN] 未安装 PyYAML，跳过 embedding cache 写回 config.yaml。")
    return False

  with open(path, "w", encoding="utf-8") as f:
    yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False, width=10**9)
  return True


def _build_query_cache_payload(model_name: str, query_text: str, vec: np.ndarray, now_iso: str) -> Dict[str, Any]:
  cache_hash = build_query_embedding_hash(model_name, query_text)
  rounded = [float(f"{float(x):.6f}") for x in vec.tolist()]
  return {
    "version": EMBEDDING_CACHE_VERSION,
    "hash": cache_hash,
    "model": model_name,
    "query_text": query_text,
    "prefixed_text": build_prefixed_query_text(query_text),
    "embedding_json": json.dumps(rounded, ensure_ascii=False, separators=(",", ":")),
    "updated_at": now_iso,
  }


def _ensure_query_cache_target(config: Dict[str, Any], cache_ref: Dict[str, Any], query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
  if not isinstance(config, dict) or not isinstance(cache_ref, dict):
    return None
  subs = config.get("subscriptions")
  if not isinstance(subs, dict):
    return None
  profiles = subs.get("intent_profiles")
  if not isinstance(profiles, list):
    return None

  try:
    profile_index = int(cache_ref.get("profile_index"))
    item_index = int(cache_ref.get("item_index"))
  except Exception:
    return None
  item_kind = str(cache_ref.get("item_kind") or "").strip()
  if item_kind not in {"keywords", "intent_queries"}:
    return None
  if profile_index < 0 or profile_index >= len(profiles):
    return None
  profile = profiles[profile_index]
  if not isinstance(profile, dict):
    return None
  items = profile.get(item_kind)
  if not isinstance(items, list):
    return None
  if item_index < 0 or item_index >= len(items):
    return None

  current = items[item_index]
  if isinstance(current, str):
    if item_kind == "keywords":
      items[item_index] = {
        "keyword": str(current or "").strip(),
        "query": str(query.get("query_text") or current or "").strip(),
      }
    else:
      items[item_index] = {
        "query": str(query.get("query_text") or current or "").strip(),
      }
    current = items[item_index]
  if not isinstance(current, dict):
    return None
  return current


def _cache_entry_matches_query(entry: Dict[str, Any], model_name: str, query_text: str) -> bool:
  return _parse_cached_query_embedding(entry, expected_model=model_name, expected_text=build_prefixed_query_text(query_text)) is not None


def hydrate_query_embeddings_from_config(
  *,
  config: Dict[str, Any],
  queries: List[dict],
  model_name: str,
  model_provider: Callable[[], Any],
  batch_size: int,
  max_length: int | None,
  config_path: str = CONFIG_FILE,
) -> Dict[str, int]:
  if not queries:
    return {"hits": 0, "misses": 0, "written": 0}

  prepared_vectors: Dict[str, np.ndarray] = {}
  prepared_payloads: Dict[str, Dict[str, Any]] = {}
  misses_by_hash: Dict[str, str] = {}
  hits = 0

  for q in queries:
    q_text = str(q.get("query_text") or "").strip()
    if not q_text:
      continue
    cache_hash = build_query_embedding_hash(model_name, q_text)
    prefixed_text = build_prefixed_query_text(q_text)
    q["query_embedding_hash"] = cache_hash
    q["prefixed_query_text"] = prefixed_text

    if cache_hash in prepared_vectors:
      q["query_embedding"] = prepared_vectors[cache_hash]
      continue

    cached_entry = q.get(EMBEDDING_CACHE_FIELD) if isinstance(q.get(EMBEDDING_CACHE_FIELD), dict) else {}
    cached_vec = _parse_cached_query_embedding(
      cached_entry,
      expected_model=model_name,
      expected_text=prefixed_text,
    )
    if cached_vec is not None:
      prepared_vectors[cache_hash] = cached_vec
      prepared_payloads[cache_hash] = dict(cached_entry)
      q["query_embedding"] = cached_vec
      hits += 1
      continue

    if cache_hash not in misses_by_hash:
      misses_by_hash[cache_hash] = q_text

  written = 0
  if misses_by_hash:
    model = model_provider()
    miss_hashes = list(misses_by_hash.keys())
    miss_texts = [misses_by_hash[h] for h in miss_hashes]
    miss_vectors = encode_queries(
      model,
      miss_texts,
      batch_size=max(int(batch_size or 1), 1),
      max_length=max_length,
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    for idx, cache_hash in enumerate(miss_hashes):
      vec = np.asarray(miss_vectors[idx], dtype=np.float32)
      prepared_vectors[cache_hash] = vec
      q_text = misses_by_hash[cache_hash]
      prepared_payloads[cache_hash] = _build_query_cache_payload(model_name, q_text, vec, now_iso)

  changed = False
  for q in queries:
    cache_hash = str(q.get("query_embedding_hash") or "").strip()
    q_text = str(q.get("query_text") or "").strip()
    if not cache_hash or cache_hash not in prepared_vectors or not q_text:
      continue
    payload = prepared_payloads.get(cache_hash) or {}
    q["query_embedding"] = prepared_vectors[cache_hash]
    q[EMBEDDING_CACHE_FIELD] = dict(payload) if isinstance(payload, dict) else None
    current_entry = q.get(EMBEDDING_CACHE_FIELD) if isinstance(q.get(EMBEDDING_CACHE_FIELD), dict) else {}
    target = _ensure_query_cache_target(config, q.get("cache_ref") or {}, q)
    if target is None:
      continue
    existing_entry = target.get(EMBEDDING_CACHE_FIELD) if isinstance(target.get(EMBEDDING_CACHE_FIELD), dict) else {}
    if _cache_entry_matches_query(existing_entry, model_name, q_text):
      continue
    target[EMBEDDING_CACHE_FIELD] = dict(payload)
    written += 1
    changed = True

  if changed:
    _remove_legacy_embedding_cache(config)
    save_config_with_embedding_cache(config, config_path)

  return {
    "hits": hits,
    "misses": len(misses_by_hash),
    "written": written,
  }


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
      emb = parse_embedding_value(item.get("embedding"))
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
        embedding=emb,
        embedding_model=str(item.get("embedding_model") or "").strip(),
      )
      if p.id:
        papers.append(p)
    except Exception as e:
      log(f"[WARN] 解析论文条目失败，将跳过：{e}")

  log(f"[INFO] 从 {path} 读取到 {len(papers)} 篇论文。")
  return papers


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
  shard_days: int = SUPABASE_VECTOR_SHARD_DAYS,
) -> list[tuple[datetime, datetime]]:
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


def _resolve_supabase_similarity(row: Dict[str, Any]) -> float:
  score_raw = row.get("similarity")
  if score_raw is None:
    score_raw = row.get("score")
  try:
    return float(score_raw)
  except Exception:
    return 0.0


def merge_supabase_vector_rows(
  rows_per_shard: list[list[Dict[str, Any]]],
  *,
  top_k: int,
) -> list[Dict[str, Any]]:
  merged_by_id: Dict[str, Dict[str, Any]] = {}

  for shard_idx, rows in enumerate(rows_per_shard):
    for local_rank, row in enumerate(rows, start=1):
      if not isinstance(row, dict):
        continue
      pid = str(row.get("id") or "").strip()
      if not pid:
        continue
      similarity = _resolve_supabase_similarity(row)
      existing = merged_by_id.get(pid)
      should_replace = False
      if existing is None:
        should_replace = True
      else:
        old_similarity = float(existing.get("_merged_similarity") or 0.0)
        old_shard_idx = int(existing.get("_merged_shard_idx") or 0)
        old_local_rank = int(existing.get("_merged_local_rank") or 0)
        if similarity > old_similarity:
          should_replace = True
        elif similarity == old_similarity and (
          shard_idx < old_shard_idx
          or (shard_idx == old_shard_idx and local_rank < old_local_rank)
        ):
          should_replace = True

      if not should_replace:
        continue

      normalized = dict(row)
      normalized["_merged_similarity"] = similarity
      normalized["_merged_shard_idx"] = shard_idx
      normalized["_merged_local_rank"] = local_rank
      merged_by_id[pid] = normalized

  merged = sorted(
    merged_by_id.values(),
    key=lambda item: (
      -float(item.get("_merged_similarity") or 0.0),
      int(item.get("_merged_shard_idx") or 0),
      int(item.get("_merged_local_rank") or 0),
      str(item.get("id") or ""),
    ),
  )
  if top_k > 0:
    merged = merged[:top_k]

  for item in merged:
    item.pop("_merged_similarity", None)
    item.pop("_merged_shard_idx", None)
    item.pop("_merged_local_rank", None)
  return merged


def _query_supabase_vector_window(
  *,
  url: str,
  api_key: str,
  rpc_name: str,
  query_embedding: list[float],
  match_count: int,
  schema: str,
  start_dt: datetime,
  end_dt: datetime,
  time_fields: tuple[str, ...],
  shard_days: int,
  min_shard_days: int = 1,
  depth: int = 0,
  rpc_mode: str = "exact",
  filter_sources: List[str] | None = None,
) -> tuple[list[list[Dict[str, Any]]], int, list[str]]:
  rows, msg = match_papers_by_embedding(
    url=url,
    api_key=api_key,
    rpc_name=rpc_name,
    query_embedding=query_embedding,
    match_count=match_count,
    schema=schema,
    start_dt=start_dt,
    end_dt=end_dt,
    time_fields=time_fields,
    filter_sources=filter_sources,
  )
  window = f"{start_dt.isoformat()} ~ {end_dt.isoformat()}"
  log(
    f"[Supabase Vector:{rpc_mode}] "
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
    f"[Supabase Vector:{rpc_mode}] "
    f"timeout fallback window={window} "
    f"split_to={len(sub_shards)} "
    f"sub_shard_days={next_shard_days}"
  )

  rows_per_shard: list[list[Dict[str, Any]]] = []
  success_count = 0
  failure_messages: list[str] = []
  for sub_start, sub_end in sub_shards:
    sub_rows, sub_success, sub_failures = _query_supabase_vector_window(
      url=url,
      api_key=api_key,
      rpc_name=rpc_name,
      query_embedding=query_embedding,
      match_count=match_count,
      schema=schema,
      start_dt=sub_start,
      end_dt=sub_end,
      time_fields=time_fields,
      shard_days=next_shard_days,
      min_shard_days=safe_min_shard_days,
      depth=depth + 1,
      rpc_mode=rpc_mode,
      filter_sources=filter_sources,
    )
    rows_per_shard.extend(sub_rows)
    success_count += sub_success
    failure_messages.extend(sub_failures)

  if success_count > 0:
    return (rows_per_shard, success_count, failure_messages)
  return ([], 0, [failure_message, *failure_messages])


def query_supabase_vector_with_shards(
  *,
  url: str,
  api_key: str,
  rpc_name: str,
  query_embedding: list[float],
  match_count: int,
  schema: str,
  start_dt: datetime | None,
  end_dt: datetime | None,
  time_fields: tuple[str, ...],
  shard_days: int = SUPABASE_VECTOR_SHARD_DAYS,
  rpc_mode: str = "exact",
  filter_sources: List[str] | None = None,
) -> tuple[list[Dict[str, Any]], str]:
  safe_start = _normalize_utc_datetime(start_dt)
  safe_end = _normalize_utc_datetime(end_dt)
  if safe_start is None or safe_end is None or safe_end <= safe_start:
    return match_papers_by_embedding(
      url=url,
      api_key=api_key,
      rpc_name=rpc_name,
      query_embedding=query_embedding,
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
    sub_rows, sub_success, sub_failures = _query_supabase_vector_window(
      url=url,
      api_key=api_key,
      rpc_name=rpc_name,
      query_embedding=query_embedding,
      match_count=match_count,
      schema=schema,
      start_dt=shard_start,
      end_dt=shard_end,
      time_fields=time_fields,
      shard_days=max(int(shard_days or 1), 1),
      rpc_mode=rpc_mode,
      filter_sources=filter_sources,
    )
    rows_per_shard.extend(sub_rows)
    success_count += sub_success
    failure_messages.extend(sub_failures)

  merged_rows = merge_supabase_vector_rows(
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


def parse_embedding_value(value: Any) -> Optional[np.ndarray]:
  if isinstance(value, np.ndarray):
    vec = value.astype(np.float32)
  elif isinstance(value, list):
    try:
      vec = np.array([float(x) for x in value], dtype=np.float32)
    except Exception:
      return None
  elif isinstance(value, str):
    text = value.strip()
    if not text:
      return None
    if text.startswith("[") and text.endswith("]"):
      text = text[1:-1]
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
      return None
    try:
      vec = np.array([float(p) for p in parts], dtype=np.float32)
    except Exception:
      return None
  else:
    return None

  if vec.ndim != 1 or vec.size == 0:
    return None
  norm = float(np.linalg.norm(vec))
  if norm <= 0:
    return None
  return vec / norm


def try_use_precomputed_embeddings(
  papers: List[Paper],
  expected_model: str,
) -> np.ndarray | None:
  if not papers:
    return None

  vectors: List[np.ndarray] = []
  dims: Set[int] = set()
  models: Set[str] = set()

  for p in papers:
    if p.embedding is None:
      return None
    vectors.append(p.embedding)
    dims.add(int(p.embedding.shape[0]))
    m = (p.embedding_model or "").strip().lower()
    if m:
      models.add(m)

  if len(dims) != 1:
    log("[WARN] 预置 embedding 维度不一致，回退本地重算论文 embedding。")
    return None

  expect = (expected_model or "").strip().lower()
  if models and expect and models != {expect}:
    log(
      "[WARN] 预置 embedding 模型与当前模型不一致："
      f"precomputed={sorted(models)} current={expect}，回退本地重算论文 embedding。"
    )
    return None

  return np.vstack(vectors)


def estimate_dynamic_top_k(total_papers: int | None) -> int:
  try:
    total = int(total_papers or 0)
  except Exception:
    total = 0
  if total <= 0:
    return 50
  blocks = (total - 1) // 1000
  return 50 * (blocks + 1)


def rank_papers_for_queries(
  model,
  papers: List[Paper],
  paper_embeddings: np.ndarray,
  queries: List[dict],
  top_k: int = 50,
) -> dict:
  """
  对每个查询分别进行相似度排序：
  - 使用 query_text 编码为向量，与所有论文向量做点积；
  - 取相似度最高的前 top_k 篇论文，记录 arxiv_id；
  - 为这些论文打上 tag（tag），一篇论文可拥有多个 tag；
  - 返回结构包含：
    {
      "queries": [ { type, tag, query_text, paper_tag, top_ids: [...] }, ... ],
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
    q_text = q.get("query_text") or ""
    paper_tag = q.get("paper_tag") or ""
    if not q_text:
      continue

    log(f"[INFO] 正在处理查询（{q.get('type')}）：tag={q.get('tag') or ''}")

    raw_cached = q.get("query_embedding")
    if isinstance(raw_cached, np.ndarray):
      q_emb = raw_cached
    elif isinstance(raw_cached, list) and raw_cached:
      q_emb = np.asarray([float(x) for x in raw_cached], dtype=np.float32)
    else:
      if model is None:
        raise RuntimeError("缺少 query embedding 且未提供可编码模型。")
      # 查询向量编码：若底层模型（如 Qwen3-Embedding）支持 "query" prompt，则自动使用
      q_emb = encode_queries(
        model,
        [q_text],
      )[0]  # 形状为 (D,)

    # 相似度 = 归一化向量的点积
    sims = np.dot(paper_embeddings, q_emb)  # 形状 (N,)

    # 从大到小排序，取前 top_k
    if top_k <= 0 or top_k > sims.shape[0]:
      k = sims.shape[0]
    else:
      k = top_k

    indices = np.argsort(-sims)[:k]
    # sim_scores: 以 paper_id 为键，记录该 query 下的相似度与排名
    sim_scores: Dict[str, Dict[str, float | int]] = {}
    for rank_idx, idx in enumerate(indices, start=1):
      pid = paper_ids[idx]
      score = float(sims[idx])
      sim_scores[pid] = {"score": score, "rank": rank_idx}
      if paper_tag:
        id_to_paper[pid].tags.add(paper_tag)

    results_per_query.append(
        {
          "type": q.get("type"),
          "tag": q.get("tag"),
          "paper_tag": q.get("paper_tag"),
          "paper_sources": q.get("paper_sources") or [q.get("active_source") or ARXIV_SOURCE_KEY],
          "query_text": q_text,
          # sim_scores 为字典：paper_id -> { score, rank }
          "sim_scores": sim_scores,
        }
    )

  return {
    "queries": results_per_query,
    "papers": id_to_paper,
  }


def rank_papers_for_queries_via_supabase(
  model,
  queries: List[dict],
  top_k: int,
  supabase_conf: Dict[str, Any],
  *,
  start_dt: datetime | None = None,
  end_dt: datetime | None = None,
  time_fields: tuple[str, ...] = SUPABASE_TIME_FIELDS,
  rpc_name_override: str | None = None,
  rpc_mode: str = "ann",
  query_filter_sources: bool = False,
) -> dict:
  if not queries:
    return {"queries": [], "papers": {}, "total_hits": 0}

  url = str(supabase_conf.get("url") or "").strip()
  api_key = str(supabase_conf.get("anon_key") or "").strip()
  rpc_name = str(rpc_name_override or supabase_conf.get("vector_rpc") or "match_arxiv_papers").strip()
  schema = str(supabase_conf.get("schema") or "public").strip()
  if not url or not api_key:
    return {"queries": [], "papers": {}, "total_hits": 0}

  q_embs: List[np.ndarray] = []
  missing_indices: List[int] = []
  missing_texts: List[str] = []
  for idx, q in enumerate(queries):
    raw_cached = q.get("query_embedding")
    if isinstance(raw_cached, np.ndarray):
      q_embs.append(raw_cached)
      continue
    if isinstance(raw_cached, list) and raw_cached:
      q_embs.append(np.asarray([float(x) for x in raw_cached], dtype=np.float32))
      continue
    q_embs.append(np.asarray([], dtype=np.float32))
    missing_indices.append(idx)
    missing_texts.append(str(q.get("query_text") or "").strip())

  if missing_indices:
    if model is None:
      raise RuntimeError("缺少 query embedding 且未提供可编码模型。")
    encoded_missing = encode_queries(model, missing_texts)
    for local_idx, query_idx in enumerate(missing_indices):
      q_embs[query_idx] = np.asarray(encoded_missing[local_idx], dtype=np.float32)

  id_to_paper: Dict[str, Paper] = {}
  results_per_query: List[dict] = []
  total_hits = 0
  non_empty_queries = 0

  for idx, q in enumerate(queries):
    q_text = str(q.get("query_text") or "").strip()
    paper_tag = str(q.get("paper_tag") or "").strip()
    if not q_text:
      continue

    published_window, updated_window, window_fields = _format_supabase_window_for_log(
      start_dt=start_dt,
      end_dt=end_dt,
      time_fields=time_fields,
    )
    log(
      f"[Supabase Vector:{rpc_mode}] "
      f"rpc={rpc_name} "
      f"batch={idx + 1} tag={q.get('tag') or ''} "
      f"type={q.get('type') or ''} "
      f"published_window={published_window} "
      f"updated_window={updated_window} "
      f"time_fields={window_fields}"
    )

    q_vec = q_embs[idx]
    query_embedding = q_vec.tolist()
    if rpc_mode == "exact":
      rows, msg = query_supabase_vector_with_shards(
        url=url,
        api_key=api_key,
        rpc_name=rpc_name,
        query_embedding=query_embedding,
        match_count=max(int(top_k or 1), 1),
        schema=schema,
        start_dt=start_dt,
        end_dt=end_dt,
        time_fields=time_fields,
        rpc_mode=rpc_mode,
        filter_sources=normalize_source_list(q.get("paper_sources")) if query_filter_sources else None,
      )
    else:
      rows, msg = match_papers_by_embedding(
        url=url,
        api_key=api_key,
        rpc_name=rpc_name,
        query_embedding=query_embedding,
        match_count=max(int(top_k or 1), 1),
        schema=schema,
        start_dt=start_dt,
        end_dt=end_dt,
        time_fields=time_fields,
        filter_sources=normalize_source_list(q.get("paper_sources")) if query_filter_sources else None,
      )
    log(f"[Supabase Vector:{rpc_mode}] {msg} | tag={q.get('tag') or ''}")

    # 语句超时（57014）是服务端配置限制，后续批次也会超时，直接跳过
    if not rows and "57014" in msg:
      log(f"[Supabase Vector:{rpc_mode}] 检测到数据库语句超时，跳过剩余批次。")
      break

    sim_scores: Dict[str, Dict[str, float | int]] = {}
    for rank_idx, row in enumerate(rows, start=1):
      pid = str(row.get("id") or "").strip()
      if not pid:
        continue
      score = _resolve_supabase_similarity(row)
      sim_scores[pid] = {"score": score, "rank": rank_idx}
      total_hits += 1

      if pid not in id_to_paper:
        id_to_paper[pid] = Paper(
          id=pid,
          source=str(row.get("source") or "supabase").strip() or "supabase",
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
        "sim_scores": sim_scores,
      }
    )
    if sim_scores:
      non_empty_queries += 1

  return {
    "queries": results_per_query,
    "papers": id_to_paper,
    "total_hits": total_hits,
    "non_empty_queries": non_empty_queries,
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
    "queries": [ { type, tag, paper_tag, query_text, top_ids: [...] }, ... ],
    "papers": [ { id, title, abstract, ..., tags: [...] }, ... ]  // 仅保留至少有一个 tag 的论文
  }
  """
  from datetime import datetime, timezone

  os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

  id_to_paper: Dict[str, Paper] = result.get("papers") or {}

  tagged_papers = [p.to_dict() for p in id_to_paper.values() if p.tags]

  # 根据第一个查询推断 top_k：优先使用 sim_scores，其次兼容旧版 top_ids
  q_list = result.get("queries") or []
  if q_list:
    q0 = q_list[0]
    sim_scores = q0.get("sim_scores") or {}
    if isinstance(sim_scores, dict) and sim_scores:
      inferred_top_k = len(sim_scores)
    else:
      top_ids = q0.get("top_ids") or []
      inferred_top_k = len(top_ids)
  else:
    inferred_top_k = 0

  payload = {
    "top_k": inferred_top_k,
    # 使用带时区的 UTC 时间，避免 DeprecationWarning
    "generated_at": datetime.now(timezone.utc).isoformat(),
    # 先输出 papers，再输出 queries，方便阅读和消费
    "papers": tagged_papers,
    "queries": result.get("queries") or [],
  }

  with open(output_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

  log(f"[INFO] 已将带 tag 的论文和每个查询的 top_k 结果写入：{output_path}")
  log(f"[INFO] 其中带 tag 的论文数：{len(tagged_papers)}")


def main() -> None:
  parser = argparse.ArgumentParser(
    description="基于 sentence-transformers 对 ArXiv 论文池做关键词 / LLM 查询相似度筛选，并为论文打 tag。",
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
    help="可选：当使用 --input 处理单个文件时，自定义输出 JSON 路径；批处理模式下将自动写入 archive/YYYYMMDD/filtered 目录，默认后缀 .embedding.json。",
  )
  parser.add_argument(
    "--top-k",
    type=int,
    default=None,
    help="每个查询保留的 Top K 论文数；未指定时根据原始论文总数自适应：<=1000 篇取 50，每增加 1000 篇增加 50。",
  )
  parser.add_argument(
    "--model",
    type=str,
    default="BAAI/bge-small-en-v1.5",
    help="用于向量检索的 sentence-transformers 模型名称（默认 BAAI/bge-small-en-v1.5）",
  )
  parser.add_argument(
    "--batch-size",
    type=int,
    default=8,
    help="向量编码批大小，显存不足时可降低（默认 8）。",
  )
  parser.add_argument(
    "--max-length",
    type=int,
    default=None,
    help="向量编码的最大 token 长度，过长文本可截断以节省显存（默认不截断）。",
  )
  parser.add_argument(
    "--device",
    type=str,
    default="cpu",
    help="向量模型运行设备，例如 cuda 或 cpu（默认 cpu）。",
  )
  parser.add_argument(
    "--disable-supabase-vector",
    action="store_true",
    help="关闭 Supabase 向量召回，强制使用本地 embedding 检索。",
  )

  args = parser.parse_args()

  config = load_config()
  pipeline_inputs = build_pipeline_inputs(config)
  supabase_conf = get_supabase_read_config(config)
  sb_start_dt, sb_end_dt = resolve_supabase_recall_window(config)
  log(
    "[INFO] Supabase 向量召回窗口："
    f"{sb_start_dt.isoformat()} ~ {sb_end_dt.isoformat()} "
    f"(time_fields={','.join(SUPABASE_TIME_FIELDS)})"
  )
  queries = pipeline_inputs.get("embedding_queries") or []
  comparison = pipeline_inputs.get("comparison") or {}
  if comparison:
    log(
      "[INFO] 迁移阶段A输入对比："
      f"embedding_only_new={comparison.get('embedding_only_new_count', 0)} "
      f"embedding_only_legacy={comparison.get('embedding_only_legacy_count', 0)}"
    )
  if not queries:
    log("[ERROR] 未能从订阅配置中解析到 Embedding 查询，退出。")
    return

  multi_source_backend = resolve_multi_source_vector_backend(config, queries) if multi_source_rpc_enabled() else None

  # 使用 EmbeddingCoarseFilter 类进行粗筛（模型只加载一次）
  coarse_filter = None

  def get_filter() -> EmbeddingCoarseFilter:
    nonlocal coarse_filter
    if coarse_filter is None:
      coarse_filter = EmbeddingCoarseFilter(
        model_name=args.model,
        top_k=50,  # 实际 top_k 会在每个文件内根据数据量动态调整
        device=args.device,
        batch_size=args.batch_size,
        max_length=args.max_length,
      )
    return coarse_filter

  cache_stats = hydrate_query_embeddings_from_config(
    config=config,
    queries=queries,
    model_name=args.model,
    model_provider=lambda: get_filter().model,
    batch_size=args.batch_size,
    max_length=args.max_length,
    config_path=CONFIG_FILE,
  )
  log(
    "[INFO] Query embedding cache："
    f"hits={cache_stats.get('hits', 0)} "
    f"misses={cache_stats.get('misses', 0)} "
    f"written={cache_stats.get('written', 0)}"
  )
  # 注意：分组会复制 query dict。必须在 embedding hydrate 之后再分组，
  # 否则 source_queries 会拿到不含 query_embedding 的旧副本。
  query_groups = group_queries_by_source(queries)
  for source_key in query_groups:
    if source_key == ARXIV_SOURCE_KEY:
      continue
    if not get_source_backend(config, source_key):
      log(f"[ERROR] 词条引用了论文源「{source_key}」，但未配置 source_backends.{source_key}。")
      return

  def run_supabase_vector_recall_for_source(
    output_path: str,
    source_key: str,
    source_queries: List[dict],
    *,
    top_k: int | None = None,
  ) -> dict | None:
    """指定 source 的 Supabase-only 向量召回。"""
    backend_conf = supabase_conf if source_key == ARXIV_SOURCE_KEY else get_source_backend(config, source_key)
    backend_enabled = (
      bool(backend_conf.get("enabled"))
      and bool(backend_conf.get("use_vector_rpc"))
      and not bool(args.disable_supabase_vector)
    )
    if not source_queries:
      return None
    if not backend_enabled:
      if source_key == ARXIV_SOURCE_KEY:
        return None
      raise RuntimeError(f"论文源「{source_key}」未配置可用的向量 RPC。")

    label = os.path.basename(output_path)
    if isinstance(top_k, int) and top_k > 0:
      dynamic_top_k = top_k
      count_value = None
    else:
      count_value, count_msg = count_papers_by_date_range(
        url=str(backend_conf.get("url") or "").strip(),
        api_key=str(backend_conf.get("anon_key") or "").strip(),
        papers_table=str(backend_conf.get("papers_table") or "papers").strip(),
        start_dt=sb_start_dt,
        end_dt=sb_end_dt,
        schema=str(backend_conf.get("schema") or "public").strip(),
      )
      log(f"[INFO] Supabase 向量召回窗口计数（source={source_key}）：{count_msg}")
      dynamic_top_k = estimate_dynamic_top_k(count_value)
    if not (isinstance(top_k, int) and top_k > 0):
      log(
        f"[INFO] Supabase 向量召回自适应 Top K = {dynamic_top_k} "
        f"(source={source_key}, window_count={count_value if count_value is not None else 'unknown'})，"
        f"输出文件：{label}"
      )
    group_start(f"Step 2.2 - supabase vector recall ({source_key}:{label})")
    try:
      exact_rpc = str(
        backend_conf.get("vector_rpc_exact")
        or backend_conf.get("vector_rpc")
        or "match_papers_exact"
      ).strip()
      if not exact_rpc:
        log("[WARN] Supabase 向量召回未配置可用 RPC。")
        return None

      mode = "exact"
      rpc_name = exact_rpc
      log(f"[INFO] Supabase 向量召回尝试：mode={mode} rpc={rpc_name}")
      result_sb = rank_papers_for_queries_via_supabase(
        model=None,
        queries=source_queries,
        top_k=dynamic_top_k,
        supabase_conf=backend_conf,
        start_dt=sb_start_dt,
        end_dt=sb_end_dt,
        time_fields=SUPABASE_TIME_FIELDS,
        rpc_name_override=rpc_name,
        rpc_mode=mode,
      )
      total_hits = int(result_sb.get("total_hits") or 0)
      non_empty_queries = int(result_sb.get("non_empty_queries") or 0)
      query_total = len(queries)
      avg_hits_per_query = (float(total_hits) / float(query_total)) if query_total > 0 else 0.0

      if total_hits <= 0:
        log(f"[WARN] Supabase 向量召回无命中（mode={mode} rpc={rpc_name}）。")
        return None

      log(
        f"[INFO] Supabase 向量召回命中 {total_hits} 条。"
        f" mode={mode} rpc={rpc_name} "
        f"non_empty_queries={non_empty_queries}/{query_total} "
        f"avg_hits_per_query={avg_hits_per_query:.1f}"
      )
      return result_sb
    except Exception as e:
      if source_key == ARXIV_SOURCE_KEY:
        log(f"[WARN] Supabase 向量召回异常：{e}")
        return None
      raise
    finally:
      group_end()
    return None

  def run_multi_source_vector_recall(output_path: str, source_queries: List[dict]) -> dict | None:
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
    log(f"[INFO] Multi-source 向量召回窗口计数：{count_msg}")
    dynamic_top_k = args.top_k if isinstance(args.top_k, int) and args.top_k > 0 else estimate_dynamic_top_k(count_value)
    group_start(f"Step 2.2 - multi-source vector recall ({label})")
    try:
      result_sb = rank_papers_for_queries_via_supabase(
        model=None,
        queries=source_queries,
        top_k=dynamic_top_k,
        supabase_conf=multi_source_backend,
        start_dt=sb_start_dt,
        end_dt=sb_end_dt,
        time_fields=SUPABASE_TIME_FIELDS,
        rpc_name_override=str(multi_source_backend.get("vector_rpc_exact") or multi_source_backend.get("vector_rpc") or "").strip(),
        rpc_mode="exact",
        query_filter_sources=True,
      )
      total_hits = int(result_sb.get("total_hits") or 0)
      if total_hits > 0:
        log(f"[INFO] Multi-source 向量召回命中 {total_hits} 条。")
        return result_sb
      log("[WARN] Multi-source 向量召回未命中。")
      return None
    finally:
      group_end()

  def process_single_file(input_path: str, output_path: str) -> None:
    merged_results: List[dict] = []
    if multi_source_backend:
      multi_source_result = run_multi_source_vector_recall(output_path, queries)
      if multi_source_result:
        save_tagged_results(multi_source_result, output_path)
        return
    arxiv_queries = query_groups.get(ARXIV_SOURCE_KEY) or []
    arxiv_supabase_result = run_supabase_vector_recall_for_source(
      output_path,
      ARXIV_SOURCE_KEY,
      arxiv_queries,
      top_k=args.top_k,
    )
    arxiv_hits = int((arxiv_supabase_result or {}).get("total_hits") or 0)
    if arxiv_supabase_result and arxiv_hits > 0:
      merged_results.append(arxiv_supabase_result)

    for source_key, source_queries in query_groups.items():
      if source_key == ARXIV_SOURCE_KEY:
        continue
      result_sb = run_supabase_vector_recall_for_source(
        output_path,
        source_key,
        source_queries,
        top_k=args.top_k,
      )
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

        filter_inst = get_filter()
        filter_inst.top_k = dynamic_top_k
        paper_embeddings = try_use_precomputed_embeddings(papers, expected_model=args.model)
        if paper_embeddings is not None:
          group_start(f"Step 2.2 - use precomputed embeddings ({os.path.basename(input_path)})")
          log(
            f"[INFO] 使用预置论文 embedding：{paper_embeddings.shape[0]} 篇，"
            f"dim={paper_embeddings.shape[1]}。"
          )
          group_end()
        else:
          group_start(f"Step 2.2 - compute embeddings ({os.path.basename(input_path)})")
          coarse_result = filter_inst.filter(items=papers, queries=arxiv_queries)
          group_end()
          paper_embeddings = coarse_result["embeddings"]

        group_start(f"Step 2.2 - rank queries ({os.path.basename(input_path)})")
        result_local = rank_papers_for_queries(
          model=filter_inst.model,
          papers=papers,
          paper_embeddings=paper_embeddings,
          queries=arxiv_queries,
          top_k=dynamic_top_k,
        )
        group_end()
        merged_results.append(result_local)

    merged = merge_pipeline_results(merged_results)
    if not merged.get("queries"):
      log(f"[WARN] 当前文件没有产出任何 Embedding 结果：{input_path}")
      return
    save_tagged_results(merged, output_path)

  # 决定处理哪些输入文件：
  # - 如果指定了 --input，则只处理该文件；
  # - 否则遍历 archive/YYYYMMDD/raw 目录下所有 .json 文件。
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
      # 单文件模式下，如未指定输出路径，则写入 archive/YYYYMMDD/filtered，文件名与原始 JSON 保持一致
      base = os.path.basename(input_path)
      if base.lower().endswith(".json"):
        base = base[:-5]
      output_path = os.path.join(FILTERED_DIR, f"{base}.embedding.json")

    process_single_file(input_path, output_path)
  else:
    if os.path.isdir(RAW_DIR):
      raw_files = sorted(f for f in os.listdir(RAW_DIR) if f.lower().endswith(".json"))
    else:
      raw_files = []

    if not raw_files:
      output_path = os.path.join(FILTERED_DIR, f"arxiv_papers_{TODAY_STR}.embedding.json")
      if multi_source_backend:
        multi_source_result = run_multi_source_vector_recall(output_path, queries)
        if multi_source_result:
          save_tagged_results(multi_source_result, output_path)
          return
      merged_results: List[dict] = []
      for source_key, source_queries in query_groups.items():
        result_sb = run_supabase_vector_recall_for_source(
          output_path,
          source_key,
          source_queries,
          top_k=args.top_k,
        )
        if result_sb:
          merged_results.append(result_sb)
      if merged_results:
        save_tagged_results(merge_pipeline_results(merged_results), output_path)
      else:
        log("[WARN] 无本地原始文件，且没有任何 source backend 返回向量结果。")
      return

    log(f"[INFO] 批量模式：将在 {RAW_DIR} 下处理 {len(raw_files)} 个 JSON 文件。")
    for name in raw_files:
      input_path = os.path.join(RAW_DIR, name)
      # 批量模式下，输出文件名与原始文件名保持一致，但目录变为 archive/YYYYMMDD/filtered
      base = name
      if base.lower().endswith(".json"):
        base = base[:-5]
      output_path = os.path.join(FILTERED_DIR, f"{base}.embedding.json")
      process_single_file(input_path, output_path)


if __name__ == "__main__":
  main()
