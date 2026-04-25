#!/usr/bin/env python
# 自动补全 config.yaml 中的 related / rewrite 字段：
# - keywords 缺少 related 时，调用 BLT gpt-4o-mini 生成相关词
# - llm_queries 缺少 rewrite 时，调用 BLT gpt-4o-mini 生成英文改写

import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import yaml  # type: ignore

from llm import BltClient

SCRIPT_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "config.yaml"))

MODEL_NAME = os.getenv("BLT_REWRITE_MODEL", "gemini-3-flash-preview")

def log(message: str) -> None:
  ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
  print(f"[{ts}] {message}", flush=True)


def group_start(title: str) -> None:
  print(f"::group::{title}", flush=True)


def group_end() -> None:
  print("::endgroup::", flush=True)


def build_related_prompt(keyword: str) -> List[Dict[str, str]]:
  return [
    {
      "role": "system",
      "content": (
        "You are a query expansion assistant. Generate related academic search terms for the given keyword. "
        "Do NOT output simple synonyms or translations. Include adjacent concepts, tasks, methods, and application domains. "
        "Output JSON only. All terms must be in English."
      ),
    },
    {
      "role": "user",
      "content": (
        f"Keyword: {keyword}\n"
        "Generate 4-6 related search terms. Avoid duplicates and obvious synonyms. "
        "Output JSON in the format:\n"
        "{\"related\": [\"term1\", \"term2\", \"term3\", \"term4\"]}"
      ),
    },
  ]


def build_keyword_rewrite_prompt(keyword: str) -> List[Dict[str, str]]:
  return [
    {
      "role": "system",
      "content": (
        "You are a query rewriter for academic retrieval. "
        "Write a single natural-language sentence that describes the ideal paper. "
        "Do NOT use boolean operators, parentheses, or query syntax. "
        "The rewrite must start with: \"Find research papers describing\". "
        "Output JSON only. English only."
      ),
    },
    {
      "role": "user",
      "content": (
        "Task: Expand this keyword into a clear, detailed academic search sentence focused on recent research. "
        "Write one sentence that reads like a paper title/abstract fragment.\n"
        f"Keyword: {keyword}\n"
        "Output JSON in the format:\n"
        "{\"rewrite\": \"...\"}\n"
        "The rewrite must be in English and start with: \"Find research papers describing\"."
      ),
    },
  ]


def build_rewrite_prompt(query: str) -> List[Dict[str, str]]:
  return [
    {
      "role": "system",
      "content": (
        "You are a query rewriter for a cross-encoder reranker. "
        "Write a single English sentence describing the ideal paper (not a command). "
        "Do NOT translate literally; reframe the intent. "
        "The rewrite must start with: \"Find research papers describing\". "
        "Output JSON only."
      ),
    },
    {
      "role": "user",
      "content": (
        "Rewrite the user's query into a concise, intent-focused academic search sentence. "
        "Include key constraints (e.g., benchmarks, datasets, evaluation, technical reports). "
        "Optionally add example entities if helpful (e.g., Google, OpenAI, Meta). "
        "Keep it to 1 sentence.\n"
        f"User query: {query}\n"
        "Output JSON in the format:\n"
        "{\"rewrite\": \"...\"}\n"
        "The rewrite must be in English and start with: \"Find research papers describing\"."
      ),
    },
  ]


def call_llm_json(client: BltClient, messages: List[Dict[str, str]], schema_name: str, schema: Dict[str, Any]) -> Dict[str, Any]:
  resp = client.chat_structured(
    messages,
    schema_name=schema_name,
    schema=schema,
    strict=True,
    allow_json_object_fallback=True,
  )
  if resp.get("refusal"):
    raise ValueError(f"模型拒绝输出结构化结果：{resp.get('refusal')}")
  if resp.get("finish_reason") not in (None, "stop"):
    raise ValueError(f"结构化输出未完成：finish_reason={resp.get('finish_reason')}")
  if resp.get("parse_error") is not None:
    raise ValueError(f"模型未返回合法 JSON：{resp.get('content')}")

  parsed = resp.get("parsed")
  if not isinstance(parsed, dict):
    raise ValueError(f"模型未返回合法 JSON：{resp.get('content')}")
  return parsed


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="补全 config.yaml 中的 related / rewrite 字段。")
    parser.add_argument(
      "--force",
      action="store_true",
      help="强制更新 related / rewrite，即使已存在。",
    )
    args = parser.parse_args()

    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"找不到 config.yaml：{CONFIG_FILE}")

    api_key = os.getenv("BLT_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 BLT_API_KEY 环境变量，无法调用 BLT。")

    group_start("Step 0.0 - load config")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    group_end()

    subs = (data or {}).get("subscriptions") or {}
    keywords = subs.get("keywords") or []
    llm_queries = subs.get("llm_queries") or []

    client = BltClient(api_key=api_key, model=MODEL_NAME)

    related_schema = {
      "type": "object",
      "properties": {
        "related": {
          "type": "array",
          "items": {"type": "string"},
        }
      },
      "required": ["related"],
      "additionalProperties": False,
    }

    rewrite_schema = {
      "type": "object",
      "properties": {
        "rewrite": {"type": "string"}
      },
      "required": ["rewrite"],
      "additionalProperties": False,
    }
    keyword_rewrite_schema = {
      "type": "object",
      "properties": {
        "rewrite": {"type": "string"}
      },
      "required": ["rewrite"],
      "additionalProperties": False,
    }

    # ===== 检查哪些字段需要扩充 =====
    missing_kw_related = []
    missing_kw_rewrite = []
    missing_llm_rewrite = []

    for idx, item in enumerate(keywords, start=1):
      if not isinstance(item, dict):
        continue
      keyword = (item.get("keyword") or "").strip()
      if not keyword:
        continue

      # 检查 related 字段
      related = item.get("related")
      if args.force or not related or (isinstance(related, list) and not related):
        missing_kw_related.append((idx, keyword, item))

      # 检查 rewrite 字段
      rewrite = (item.get("rewrite") or "").strip()
      if args.force or not rewrite:
        missing_kw_rewrite.append((idx, keyword, item))

    for idx, item in enumerate(llm_queries, start=1):
      if not isinstance(item, dict):
        continue
      query = (item.get("query") or "").strip()
      if not query:
        continue

      # 检查 rewrite 字段
      rewrite = (item.get("rewrite") or "").strip()
      if args.force or not rewrite:
        missing_llm_rewrite.append((idx, query, item))

    # ===== 输出检查结果 =====
    log(f"[CHECK] 需要扩充 keywords.related: {len(missing_kw_related)} 个")
    log(f"[CHECK] 需要扩充 keywords.rewrite: {len(missing_kw_rewrite)} 个")
    log(f"[CHECK] 需要扩充 llm_queries.rewrite: {len(missing_llm_rewrite)} 个")

    # 如果所有字段都完整且不强制更新，直接返回
    if not args.force and not missing_kw_related and not missing_kw_rewrite and not missing_llm_rewrite:
      log("[INFO] config.yaml 所有字段都完整，无需扩充。使用 --force 参数可强制重新生成。")
      return

    # ===== 只扩充缺失的字段 =====
    # keywords: 补齐 related
    if missing_kw_related:
      group_start("Step 0.1 - enrich keywords.related")
      for idx, keyword, item in missing_kw_related:
        log(f"[0.1] keyword related {idx}/{len(keywords)}: {keyword}")
        messages = build_related_prompt(keyword)
        result = call_llm_json(client, messages, "related_terms", related_schema)
        related_terms = [t.strip() for t in (result.get("related") or []) if str(t).strip()]
        if related_terms:
          item["related"] = related_terms
      group_end()

    # keywords: 补齐 rewrite
    if missing_kw_rewrite:
      group_start("Step 0.2 - enrich keywords.rewrite")
      for idx, keyword, item in missing_kw_rewrite:
        log(f"[0.2] keyword rewrite {idx}/{len(keywords)}: {keyword}")
        messages = build_keyword_rewrite_prompt(keyword)
        result = call_llm_json(client, messages, "keyword_rewrite", keyword_rewrite_schema)
        new_rewrite = str(result.get("rewrite") or "").strip()
        if new_rewrite:
          item["rewrite"] = new_rewrite
      group_end()

    # llm_queries: 补齐 rewrite
    if missing_llm_rewrite:
      group_start("Step 0.3 - enrich llm_queries.rewrite")
      for idx, query, item in missing_llm_rewrite:
        log(f"[0.3] llm_query rewrite {idx}/{len(llm_queries)}")
        messages = build_rewrite_prompt(query)
        result = call_llm_json(client, messages, "rewrite_query", rewrite_schema)
        rewrite_text = str(result.get("rewrite") or "").strip()
        if rewrite_text:
          item["rewrite"] = rewrite_text
      group_end()

    # 保存更新后的配置
    subs["keywords"] = keywords
    subs["llm_queries"] = llm_queries
    data["subscriptions"] = subs

    group_start("Step 0.4 - save config")
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
      yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    log("[INFO] 已更新 config.yaml 的相关字段。")
    group_end()


if __name__ == "__main__":
    main()
