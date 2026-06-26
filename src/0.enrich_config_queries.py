#!/usr/bin/env python
# Automatically complete related / rewrite fields in config.yaml:
# - keywords missing related, call DeepSeek to generate related terms
# - llm_queries missing rewrite, call DeepSeek to generate English rewrite

import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import yaml  # type: ignore

from llm import DeepSeekClient

SCRIPT_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "config.yaml"))

MODEL_NAME = (
  os.getenv("DEEPSEEK_REWRITE_MODEL")
  or os.getenv("SUMMARY_MODEL")
  or os.getenv("DEEPSEEK_MODEL")
  or "deepseek-v4-flash"
)
BASE_URL = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("SUMMARY_BASE_URL") or "https://api.deepseek.com"

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


def call_llm_json(client: DeepSeekClient, messages: List[Dict[str, str]], schema_name: str, schema: Dict[str, Any]) -> Dict[str, Any]:
  resp = client.chat_structured(
    messages,
    schema_name=schema_name,
    schema=schema,
    strict=True,
    allow_json_object_fallback=True,
  )
  if resp.get("refusal"):
    raise ValueError(f"Model refused structured output: {resp.get('refusal')}")
  if resp.get("finish_reason") not in (None, "stop"):
    raise ValueError(f"Structured output incomplete: finish_reason={resp.get('finish_reason')}")
  if resp.get("parse_error") is not None:
    raise ValueError(f"Model did not return valid JSON: {resp.get('content')}")

  parsed = resp.get("parsed")
  if not isinstance(parsed, dict):
    raise ValueError(f"Model did not return valid JSON: {resp.get('content')}")
  return parsed


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Enrich related / rewrite fields in config.yaml.")
    parser.add_argument(
      "--force",
      action="store_true",
      help="Force-update related / rewrite even when they already exist.",
    )
    args = parser.parse_args()

    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"config.yaml not found: {CONFIG_FILE}")

    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("SUMMARY_API_KEY")
    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY or SUMMARY_API_KEY; cannot call DeepSeek.")

    group_start("Step 0.0 - load config")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    group_end()

    subs = (data or {}).get("subscriptions") or {}
    keywords = subs.get("keywords") or []
    llm_queries = subs.get("llm_queries") or []

    client = DeepSeekClient(api_key=api_key, model=MODEL_NAME, base_url=BASE_URL)

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

    # ===== Check which fields need enrichment =====
    missing_kw_related = []
    missing_kw_rewrite = []
    missing_llm_rewrite = []

    for idx, item in enumerate(keywords, start=1):
      if not isinstance(item, dict):
        continue
      keyword = (item.get("keyword") or "").strip()
      if not keyword:
        continue

      # Check related field
      related = item.get("related")
      if args.force or not related or (isinstance(related, list) and not related):
        missing_kw_related.append((idx, keyword, item))

      # Check rewrite field
      rewrite = (item.get("rewrite") or "").strip()
      if args.force or not rewrite:
        missing_kw_rewrite.append((idx, keyword, item))

    for idx, item in enumerate(llm_queries, start=1):
      if not isinstance(item, dict):
        continue
      query = (item.get("query") or "").strip()
      if not query:
        continue

      # Check rewrite field
      rewrite = (item.get("rewrite") or "").strip()
      if args.force or not rewrite:
        missing_llm_rewrite.append((idx, query, item))

    # ===== Report check results =====
    log(f"[CHECK] keywords.related to enrich: {len(missing_kw_related)}")
    log(f"[CHECK] keywords.rewrite to enrich: {len(missing_kw_rewrite)}")
    log(f"[CHECK] llm_queries.rewrite to enrich: {len(missing_llm_rewrite)}")

    # If all fields are complete and --force is not set, exit early
    if not args.force and not missing_kw_related and not missing_kw_rewrite and not missing_llm_rewrite:
      log("[INFO] All config.yaml fields are complete; no enrichment needed. Use --force to regenerate.")
      return

    # ===== Enrich only missing fields =====
    # keywords: fill in related
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

    # keywords: fill in rewrite
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

    # llm_queries: fill in rewrite
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

    # Save updated config
    subs["keywords"] = keywords
    subs["llm_queries"] = llm_queries
    data["subscriptions"] = subs

    group_start("Step 0.4 - save config")
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
      yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    log("[INFO] Updated related fields in config.yaml.")
    group_end()


if __name__ == "__main__":
    main()
