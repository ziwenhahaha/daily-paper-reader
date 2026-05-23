#!/usr/bin/env python
"""Compare Qwen3 reranker API model sizes using DeepSeek as the judge."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reranker_api import (
  DEFAULT_QWEN3_RERANK_INSTRUCTION,
  SILICONFLOW_QWEN3_RERANKER_MODELS,
  SiliconFlowReranker,
)
from rerank_budget_experiment import (
  count_star_candidates,
  load_json,
  score_summary,
  write_json,
)


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent


def log(message: str) -> None:
  print(message, flush=True)


def load_module(name: str, path: Path):
  spec = importlib.util.spec_from_file_location(name, path)
  if not spec or not spec.loader:
    raise RuntimeError(f"无法加载模块：{path}")
  module = importlib.util.module_from_spec(spec)
  sys.modules[name] = module
  spec.loader.exec_module(module)
  return module


def safe_name(raw: str) -> str:
  text = str(raw or "").strip().split("/")[-1].lower()
  return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in text) or "model"


def resolve_path(raw: str) -> Path:
  path = Path(raw)
  return path if path.is_absolute() else ROOT_DIR / path


def top_overlap(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
  id_sets: Dict[str, set[str]] = {}
  for item in items:
    if item.get("error"):
      continue
    ids = item.get("top20_paper_ids") or []
    id_sets[str(item.get("name") or item.get("model") or "")] = {str(pid) for pid in ids if pid}

  matrix: Dict[str, Dict[str, int]] = {}
  for left, left_ids in id_sets.items():
    matrix[left] = {}
    for right, right_ids in id_sets.items():
      matrix[left][right] = len(left_ids & right_ids)
  return matrix


def parse_model(raw: str) -> Tuple[str, str]:
  text = str(raw or "").strip()
  if not text:
    raise ValueError("model 不能为空")
  if "=" in text:
    name, model = text.split("=", 1)
    return safe_name(name), model.strip()
  return safe_name(text), text


def main() -> None:
  parser = argparse.ArgumentParser(
    description="用 SiliconFlow Qwen3 Reranker API 三个尺寸做推荐链路对比，DeepSeek 结果为最终评判。",
  )
  parser.add_argument("--input", required=True, help="RRF 输入 JSON。")
  parser.add_argument("--output-dir", required=True, help="实验输出目录。")
  parser.add_argument("--config", default=str(ROOT_DIR / "config.yaml"))
  parser.add_argument(
    "--model",
    action="append",
    default=[],
    help="模型名或别名，格式 alias=Qwen/Qwen3-Reranker-8B；可重复传入。",
  )
  parser.add_argument("--top-n", type=int, default=80)
  parser.add_argument("--global-limit", type=int, default=120)
  parser.add_argument("--guaranteed-per-lane", type=int, default=2)
  parser.add_argument("--lane-top-k", type=int, default=None)
  parser.add_argument("--min-star", type=int, default=4)
  parser.add_argument("--llm-batch-size", type=int, default=10)
  parser.add_argument("--llm-filter-concurrency", type=int, default=2)
  parser.add_argument("--llm-max-chars", type=int, default=850)
  parser.add_argument("--llm-max-output-tokens", type=int, default=4096)
  parser.add_argument("--api-base-url", default=os.getenv("SILICONFLOW_RERANK_URL") or os.getenv("RERANK_API_BASE_URL") or "")
  parser.add_argument("--api-timeout", type=int, default=120)
  parser.add_argument("--rerank-instruction", default=DEFAULT_QWEN3_RERANK_INSTRUCTION)
  parser.add_argument("--seed", type=int, default=20260503, help="固定 Step 3/Step 4 随机分批顺序，便于模型横评。")
  parser.add_argument("--skip-existing", action="store_true")
  parser.add_argument("--fail-fast", action="store_true", help="某个模型失败时立即退出；默认记录失败并继续。")
  args = parser.parse_args()

  os.environ.setdefault("MKL_THREADING_LAYER", "GNU")

  input_path = resolve_path(args.input)
  output_dir = resolve_path(args.output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)

  models = [parse_model(item) for item in (args.model or [])]
  if not models:
    models = [(safe_name(model), model) for model in SILICONFLOW_QWEN3_RERANKER_MODELS]

  rank_mod = load_module("rerank_size_experiment_rank", SCRIPT_DIR / "3.rank_papers.py")
  llm_mod = load_module("rerank_size_experiment_llm", SCRIPT_DIR / "4.llm_refine_papers.py")

  summary: Dict[str, Any] = {
    "input": str(input_path),
    "judge": "DeepSeek Step 4 llm_ranked",
    "provider": "siliconflow",
    "models": [],
    "top_n": args.top_n,
    "min_star": args.min_star,
    "global_limit": args.global_limit,
    "guaranteed_per_lane": args.guaranteed_per_lane,
    "lane_top_k": args.lane_top_k,
  }

  for name, model in models:
    model_dir = output_dir / name
    model_dir.mkdir(parents=True, exist_ok=True)
    rerank_path = model_dir / f"{name}.rerank.json"
    llm_path = model_dir / f"{name}.llm.json"
    log(f"[size-experiment] model={model} name={name}")

    reranker: Optional[SiliconFlowReranker] = None
    try:
      rerank_start = time.perf_counter()
      if args.skip_existing and rerank_path.exists():
        log(f"[size-experiment] reuse rerank: {rerank_path}")
        rerank_stats: Dict[str, Any] = {
          "api_calls": 0,
          "latency_seconds_total": 0.0,
          "latency_seconds_mean": 0.0,
          "latency_seconds_p95": 0.0,
          "input_tokens": 0,
          "output_tokens": 0,
          "estimated_cost_usd": None,
          "price_per_m_token_usd": None,
        }
      else:
        reranker = SiliconFlowReranker(
          base_url=args.api_base_url or None,
          timeout=args.api_timeout,
          instruction=args.rerank_instruction,
        )
        if hasattr(rank_mod, "random"):
          rank_mod.random.seed(args.seed)
        rank_mod.process_file(
          reranker=reranker,
          input_path=str(input_path),
          output_path=str(rerank_path),
          top_n=args.top_n,
          rerank_model=model,
          rerank_lane_top_k=args.lane_top_k,
          rerank_guaranteed_per_lane=args.guaranteed_per_lane,
          rerank_global_pool_limit=args.global_limit,
        )
        rerank_stats = reranker.stats(model)
      rerank_seconds = time.perf_counter() - rerank_start

      llm_start = time.perf_counter()
      if args.skip_existing and llm_path.exists():
        log(f"[size-experiment] reuse llm: {llm_path}")
      else:
        if hasattr(llm_mod, "random"):
          llm_mod.random.seed(args.seed)
        llm_mod.process_file(
          input_path=str(rerank_path),
          output_path=str(llm_path),
          config_path=args.config,
          min_star=args.min_star,
          batch_size=args.llm_batch_size,
          max_chars=args.llm_max_chars,
          filter_model=llm_mod.DEFAULT_FILTER_MODEL,
          max_output_tokens=args.llm_max_output_tokens,
          filter_concurrency=args.llm_filter_concurrency,
        )
      llm_seconds = time.perf_counter() - llm_start

      rerank_data = load_json(rerank_path)
      item = {
        "name": name,
        "model": model,
        "rerank_seconds": round(rerank_seconds, 3),
        "llm_seconds": round(llm_seconds, 3),
        "global_pool_effective_size": rerank_data.get("global_pool_effective_size"),
        "star_candidates": count_star_candidates(rerank_path, args.min_star),
        "rerank_path": str(rerank_path),
        "llm_path": str(llm_path),
        **rerank_stats,
        **score_summary(llm_path),
      }
      summary["models"].append(item)
      write_json(output_dir / "summary.json", summary)
      log(
        "[size-experiment] done "
        f"{name}: api_calls={item['api_calls']} star_candidates={item['star_candidates']} "
        f"score_ge_8={item['score_ge_8']} top20_sum={item['top20_score_sum']} "
        f"rerank={item['rerank_seconds']:.1f}s llm={item['llm_seconds']:.1f}s"
      )
    except Exception as exc:
      item = {
        "name": name,
        "model": model,
        "error": str(exc),
        "rerank_path": str(rerank_path),
        "llm_path": str(llm_path),
      }
      summary["models"].append(item)
      write_json(output_dir / "summary.json", summary)
      log(f"[size-experiment] failed {name}: {exc}")
      if args.fail_fast:
        raise

  finished = [item for item in summary["models"] if not item.get("error")]
  ranked = sorted(
    finished,
    key=lambda x: (
      -float(x.get("top20_score_sum") or 0.0),
      -int(x.get("score_ge_8") or 0),
      -int(x.get("score_ge_9") or 0),
      float(x.get("rerank_seconds") or 0.0),
    ),
  )
  summary["recommended"] = ranked[0]["name"] if ranked else ""
  summary["top20_overlap"] = top_overlap(finished)
  write_json(output_dir / "summary.json", summary)
  log(f"[size-experiment] summary: {output_dir / 'summary.json'}")
  log(f"[size-experiment] recommended={summary['recommended']}")


if __name__ == "__main__":
  main()
