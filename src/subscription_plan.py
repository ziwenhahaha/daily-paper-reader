#!/usr/bin/env python
# 统一订阅解析模块：
# - 输出 BM25 / Embedding / LLM refine 可直接消费的数据（仅基于 intent_profiles）
# - 支持迁移阶段门禁（A/B/C）

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
import re

try:
  from query_boolean import clean_expr_for_embedding
except Exception:  # pragma: no cover - 兼容 package 导入路径
  from src.query_boolean import clean_expr_for_embedding


MAIN_TERM_WEIGHT = 1.0
RELATED_TERM_WEIGHT = 0.5
OR_SOFT_WEIGHT = 0.3
DEFAULT_STAGE = "A"
SUPPORTED_STAGES = {"A", "B", "C"}
DEFAULT_KEYWORD_RECALL_MODE = "or"
SUPPORTED_KEYWORD_RECALL_MODES = {"or", "boolean_mixed"}


def _now_iso() -> str:
  return datetime.now(timezone.utc).isoformat()


def _norm_text(v: Any) -> str:
  return str(v or "").strip()


def _slug(s: str) -> str:
  t = _norm_text(s).lower()
  t = re.sub(r"[^a-z0-9]+", "-", t)
  t = re.sub(r"-+", "-", t).strip("-")
  return t or "profile"


def _as_bool(v: Any, default: bool = True) -> bool:
  if isinstance(v, bool):
    return v
  if v is None:
    return default
  s = str(v).strip().lower()
  if s in ("0", "false", "no", "off"):
    return False
  if s in ("1", "true", "yes", "on"):
    return True
  return default


def _uniq_keep_order(items: List[str]) -> List[str]:
  seen = set()
  out: List[str] = []
  for i in items:
    t = _norm_text(i)
    if not t:
      continue
    key = t.lower()
    if key in seen:
      continue
    seen.add(key)
    out.append(t)
  return out


def _normalize_text_item(item: Any) -> str:
  if isinstance(item, str):
    return _norm_text(item)
  if not isinstance(item, dict):
    return ''
  return _norm_text(item.get('text') or item.get('keyword') or item.get('expr') or '')


def _normalize_query_item(item: Any) -> str:
  if isinstance(item, str):
    return _norm_text(item)
  if not isinstance(item, dict):
    return ''
  return _norm_text(
    item.get('query')
    or item.get('rewrite')
    or item.get('rewrite_for_embedding')
    or item.get('text')
    or ''
  )


def _normalize_intent_query_entry(item: Any) -> Dict[str, Any]:
  if isinstance(item, str):
    query = _norm_text(item)
    if not query:
      return {}
    return {
      "query": query,
      "enabled": True,
      "source": "manual",
    }

  if not isinstance(item, dict):
    return {}

  query = _norm_text(item.get("query") or item.get("text") or item.get("keyword") or item.get("expr") or "")
  if not query:
    return {}

  return {
    "query": query,
    "enabled": _as_bool(item.get("enabled"), True),
    "source": _norm_text(item.get("source") or "manual"),
    "note": _norm_text(item.get("note") or ""),
  }


def _normalize_query_list(items: Any) -> List[Dict[str, Any]]:
  if not isinstance(items, list):
    return []

  out: List[Dict[str, Any]] = []
  for raw in items:
    entry = _normalize_intent_query_entry(raw)
    if entry:
      out.append(entry)

  seen = set()
  deduped: List[Dict[str, Any]] = []
  for item in out:
    key = _norm_text(item.get("query")).lower()
    if not key or key in seen:
      continue
    seen.add(key)
    deduped.append(item)
  return deduped


def _normalize_keyword_entry(item: Any) -> Dict[str, Any]:
  if isinstance(item, str):
    keyword = _norm_text(item)
    if not keyword:
      return {}
    return {
      "keyword": keyword,
      "query": keyword,
      "logic_cn": "",
      "enabled": True,
      "source": "manual",
      "note": "",
    }

  if not isinstance(item, dict):
    return {}

  keyword = _norm_text(item.get("keyword") or item.get("text") or item.get("expr") or "")
  if not keyword:
    return {}
  query = _normalize_query_item(item)
  if not query:
    query = keyword

  return {
    "keyword": keyword,
    "query": query,
    "logic_cn": _norm_text(item.get("logic_cn") or ""),
    "enabled": _as_bool(item.get("enabled"), True),
    "source": _norm_text(item.get("source") or "manual"),
    "note": _norm_text(item.get("note") or ""),
  }


def _normalize_keyword_list(items: Any) -> List[Dict[str, Any]]:
  if not isinstance(items, list):
    return []

  out: List[Dict[str, Any]] = []
  for raw in items:
    entry = _normalize_keyword_entry(raw)
    if entry:
      out.append(entry)

  seen = set()
  deduped: List[Dict[str, Any]] = []
  for item in out:
    key = _norm_text(item.get("keyword")).lower()
    if not key or key in seen:
      continue
    seen.add(key)
    deduped.append(item)
  return deduped


def get_migration_stage(config: Dict[str, Any]) -> str:
  subs = (config or {}).get("subscriptions") or {}
  migration = subs.get("schema_migration") or {}
  stage = _norm_text((migration or {}).get("stage") or DEFAULT_STAGE).upper()
  if stage not in SUPPORTED_STAGES:
    stage = DEFAULT_STAGE
  return stage


def get_keyword_recall_mode(config_or_subs: Dict[str, Any]) -> str:
  base = config_or_subs or {}
  subs = base.get("subscriptions") if isinstance(base, dict) and isinstance(base.get("subscriptions"), dict) else base
  mode = _norm_text((subs or {}).get("keyword_recall_mode") or DEFAULT_KEYWORD_RECALL_MODE).lower()
  if mode not in SUPPORTED_KEYWORD_RECALL_MODES:
    mode = DEFAULT_KEYWORD_RECALL_MODE
  return mode


def _normalize_keyword_expr(expr: str) -> str:
  return clean_expr_for_embedding(_norm_text(expr)) or _norm_text(expr)


def _normalize_profile(profile: Dict[str, Any], idx: int) -> Dict[str, Any]:
  tag = _norm_text(profile.get("tag") or "")
  description = _norm_text(profile.get("description") or "")
  if not tag:
    tag = f"profile-{idx + 1}"

  kw_rules_in = profile.get("keywords") or []
  kw_rules: List[Dict[str, Any]] = _normalize_keyword_list(kw_rules_in)
  intent_queries: List[Dict[str, Any]] = _normalize_query_list(profile.get("intent_queries"))

  return {
    "tag": tag,
    "description": description,
    "enabled": _as_bool(profile.get("enabled"), True),
    "keywords": kw_rules,
    "intent_queries": intent_queries,
    "updated_at": _norm_text(profile.get("updated_at") or _now_iso()),
  }


def _build_from_profiles(subs: Dict[str, Any]) -> Dict[str, Any]:
  raw_profiles = subs.get("intent_profiles") or []
  profiles: List[Dict[str, Any]] = []
  if isinstance(raw_profiles, list):
    for idx, p in enumerate(raw_profiles):
      if not isinstance(p, dict):
        continue
      profiles.append(_normalize_profile(p, idx))

  bm25_queries: List[Dict[str, Any]] = []
  embedding_queries: List[Dict[str, Any]] = []
  context_keywords: List[Dict[str, str]] = []
  context_queries: List[Dict[str, str]] = []
  tags: List[str] = []

  for profile in profiles:
    if not profile.get("enabled", True):
      continue
    tag = _norm_text(profile.get("tag") or "")
    if not tag:
      continue
    tags.append(tag)
    paper_tag_keyword = f"keyword:{tag}"
    paper_tag_query = f"query:{tag}"

    for keyword_rule in profile.get("keywords") or []:
      normalized = _normalize_keyword_entry(keyword_rule)
      if not normalized:
        continue
      if not _as_bool(normalized.get("enabled"), True):
        continue

      raw_text = _norm_text(normalized.get("keyword") or "")
      raw_query = _norm_text(normalized.get("query") or "")
      if not raw_text:
        continue
      if not raw_query:
        raw_query = raw_text

      expr = _normalize_keyword_expr(raw_text)
      logic_cn = _norm_text(normalized.get("logic_cn") or "")
      source = _norm_text(normalized.get("source") or "manual")
      bm25_queries.append(
        {
          "type": "keyword",
          "tag": tag,
          "paper_tag": paper_tag_keyword,
          "query_text": expr,
          "query_terms": [{"text": expr, "weight": MAIN_TERM_WEIGHT}],
          "boolean_expr": "",
          "logic_cn": logic_cn,
          "source": source,
          "or_soft_weight": OR_SOFT_WEIGHT,
        }
      )
      embedding_queries.append(
        {
          "type": "keyword",
          "tag": tag,
          "paper_tag": paper_tag_keyword,
          "query_text": raw_query,
          "logic_cn": logic_cn,
          "source": source,
        }
      )
      context_keywords.append({"tag": paper_tag_keyword, "keyword": raw_text, "logic_cn": logic_cn})
      context_queries.append(
        {
          "tag": paper_tag_query,
          "query": raw_query,
          "logic_cn": logic_cn,
        }
      )

    for intent_query in profile.get("intent_queries") or []:
      normalized_intent = _normalize_intent_query_entry(intent_query)
      if not normalized_intent:
        continue
      if not _as_bool(normalized_intent.get("enabled"), True):
        continue

      raw_query = _norm_text(normalized_intent.get("query") or "")
      if not raw_query:
        continue

      source = _norm_text(normalized_intent.get("source") or "manual")
      intent_query_tag = paper_tag_query

      bm25_queries.append(
        {
          "type": "intent_query",
          "tag": tag,
          "paper_tag": f"query:{tag}",
          "query_text": raw_query,
          "query_terms": [{"text": raw_query, "weight": MAIN_TERM_WEIGHT}],
          "boolean_expr": "",
          "logic_cn": "",
          "source": source,
          "or_soft_weight": OR_SOFT_WEIGHT,
        }
      )
      embedding_queries.append(
        {
          "type": "intent_query",
          "tag": tag,
          "paper_tag": f"query:{tag}",
          "query_text": raw_query,
          "logic_cn": "",
          "source": source,
        }
      )
      context_queries.append(
        {
          "tag": intent_query_tag,
          "query": raw_query,
          "logic_cn": "",
        }
      )

  return {
    "profiles": profiles,
    "bm25_queries": bm25_queries,
    "embedding_queries": embedding_queries,
    "context_keywords": context_keywords,
    "context_queries": context_queries,
    "tags": _uniq_keep_order(tags),
  }


def build_pipeline_inputs(config: Dict[str, Any]) -> Dict[str, Any]:
  """
  统一输出流水线输入：
  - bm25_queries：供 Step 2.1 使用
  - embedding_queries：供 Step 2.2 使用
  - context_keywords/context_queries：供 Step 4 使用
  """
  cfg = config or {}
  subs = (cfg.get("subscriptions") or {}) if isinstance(cfg, dict) else {}
  stage = get_migration_stage(cfg)
  has_profiles = isinstance(subs.get("intent_profiles"), list) and bool(subs.get("intent_profiles"))

  profile_plan = _build_from_profiles(subs) if has_profiles else {}
  plan: Dict[str, Any]
  source = "legacy"
  fallback_used = False

  if has_profiles:
    plan = profile_plan
    source = "intent_profiles"
  else:
    # 阶段 A/B/C：未配置新链路则返回空输入，避免回退到旧结构。
    plan = {
      "profiles": [],
      "bm25_queries": [],
      "embedding_queries": [],
      "context_keywords": [],
      "context_queries": [],
      "tags": [],
    }
    source = "intent_profiles_required_but_missing"

  comparison = {}

  return {
    "stage": stage,
    "source": source,
    "fallback_used": fallback_used,
    "profiles": plan.get("profiles") or [],
    "bm25_queries": plan.get("bm25_queries") or [],
    "embedding_queries": plan.get("embedding_queries") or [],
    "context_keywords": plan.get("context_keywords") or [],
    "context_queries": plan.get("context_queries") or [],
    "tags": _uniq_keep_order(plan.get("tags") or []),
    "comparison": comparison,
  }


def count_subscription_tags(config: Dict[str, Any]) -> Tuple[int, List[str]]:
  plan = build_pipeline_inputs(config or {})
  tags = _uniq_keep_order([_norm_text(x) for x in (plan.get("tags") or [])])
  return len(tags), tags
