#!/usr/bin/env python
"""Run local rerank budget experiments and judge by DeepSeek refine output."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


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


@dataclass
class BudgetProfile:
  name: str
  global_limit: int
  guaranteed_per_lane: int
  lane_top_k: Optional[int] = None


def parse_profile(raw: str) -> BudgetProfile:
  text = str(raw or "").strip()
  if not text:
    raise ValueError("profile 不能为空")
  if "=" in text:
    name, body = text.split("=", 1)
  else:
    body = text
    name = body.replace(":", "-")
  parts = [item.strip() for item in body.split(":")]
  if len(parts) not in (2, 3):
    raise ValueError("profile 格式应为 name=global_limit:guaranteed_per_lane[:lane_top_k]")
  global_limit = int(parts[0])
  guaranteed = int(parts[1])
  lane_top_k = int(parts[2]) if len(parts) == 3 and parts[2] else None
  safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in name.strip())
  return BudgetProfile(
    name=safe_name or f"g{global_limit}-lane{guaranteed}",
    global_limit=global_limit,
    guaranteed_per_lane=guaranteed,
    lane_top_k=lane_top_k,
  )


def load_json(path: Path) -> Dict[str, Any]:
  with path.open("r", encoding="utf-8") as f:
    data = json.load(f)
  return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)


def count_star_candidates(path: Path, min_star: int) -> int:
  data = load_json(path)
  ids = set()
  for query in data.get("queries") or []:
    for item in query.get("ranked") or []:
      if int(item.get("star_rating") or 0) >= min_star:
        paper_id = str(item.get("paper_id") or "").strip()
        if paper_id:
          ids.add(paper_id)
  return len(ids)


def score_summary(path: Path) -> Dict[str, Any]:
  data = load_json(path)
  ranked = data.get("llm_ranked") or []
  scores: List[float] = []
  paper_ids: List[str] = []
  for item in ranked:
    try:
      score = float(item.get("score") or 0.0)
    except Exception:
      score = 0.0
    scores.append(score)
    paper_id = str(item.get("paper_id") or item.get("id") or "").strip()
    if paper_id:
      paper_ids.append(paper_id)
  top10 = scores[:10]
  top20 = scores[:20]
  return {
    "llm_ranked": len(ranked),
    "score_sum": round(sum(scores), 4),
    "top10_score_sum": round(sum(top10), 4),
    "top20_score_sum": round(sum(top20), 4),
    "top10_mean": round(sum(top10) / len(top10), 4) if top10 else 0.0,
    "top20_mean": round(sum(top20) / len(top20), 4) if top20 else 0.0,
    "score_ge_9": sum(1 for score in scores if score >= 9.0),
    "score_ge_8": sum(1 for score in scores if score >= 8.0),
    "score_ge_7": sum(1 for score in scores if score >= 7.0),
    "top20_paper_ids": paper_ids[:20],
  }


def main() -> None:
  parser = argparse.ArgumentParser(description="用 DeepSeek 结果评估 rerank 候选池预算。")
  parser.add_argument("--input", required=True, help="RRF 输入 JSON。")
  parser.add_argument("--output-dir", required=True, help="实验输出目录。")
  parser.add_argument(
    "--profile",
    action="append",
    default=[],
    help="预算配置，格式 name=global_limit:guaranteed_per_lane[:lane_top_k]。",
  )
  parser.add_argument("--config", default=str(ROOT_DIR / "config.yaml"))
  parser.add_argument("--top-n", type=int, default=80)
  parser.add_argument("--min-star", type=int, default=4)
  parser.add_argument("--llm-batch-size", type=int, default=10)
  parser.add_argument("--llm-filter-concurrency", type=int, default=2)
  parser.add_argument("--llm-max-chars", type=int, default=850)
  parser.add_argument("--llm-max-output-tokens", type=int, default=4096)
  parser.add_argument("--rerank-model", default=os.getenv("LOCAL_RERANK_MODEL") or "Qwen/Qwen3-Reranker-0.6B")
  parser.add_argument("--rerank-device", default=os.getenv("LOCAL_RERANK_DEVICE", "cpu"))
  parser.add_argument("--rerank-batch-size", type=int, default=int(os.getenv("LOCAL_RERANK_BATCH_SIZE") or "4"))
  parser.add_argument("--seed", type=int, default=20260503, help="固定 Step 3/Step 4 随机分批顺序，便于预算/模型对比。")
  parser.add_argument("--skip-existing", action="store_true")
  args = parser.parse_args()

  os.environ.setdefault("MKL_THREADING_LAYER", "GNU")

  input_path = Path(args.input)
  if not input_path.is_absolute():
    input_path = ROOT_DIR / input_path
  output_dir = Path(args.output_dir)
  if not output_dir.is_absolute():
    output_dir = ROOT_DIR / output_dir
  output_dir.mkdir(parents=True, exist_ok=True)

  profiles = [parse_profile(item) for item in (args.profile or [])]
  if not profiles:
    profiles = [
      BudgetProfile("tiny", 40, 1),
      BudgetProfile("fast", 80, 1),
      BudgetProfile("balanced", 120, 2),
    ]

  rank_mod = load_module("rank_budget_experiment_rank", SCRIPT_DIR / "3.rank_papers.py")
  llm_mod = load_module("rank_budget_experiment_llm", SCRIPT_DIR / "4.llm_refine_papers.py")

  log(
    f"[experiment] 加载 reranker model={args.rerank_model} "
    f"device={args.rerank_device or 'auto'} batch_size={args.rerank_batch_size}"
  )
  reranker = rank_mod.LocalQwenReranker(
    model_name=args.rerank_model,
    device=args.rerank_device,
    batch_size=args.rerank_batch_size,
  )

  summary: Dict[str, Any] = {
    "input": str(input_path),
    "profiles": [],
    "judge": "DeepSeek Step 4 llm_ranked",
    "top_n": args.top_n,
    "min_star": args.min_star,
  }

  for profile in profiles:
    profile_dir = output_dir / profile.name
    rerank_path = profile_dir / f"{profile.name}.rerank.json"
    llm_path = profile_dir / f"{profile.name}.llm.json"
    profile_dir.mkdir(parents=True, exist_ok=True)

    log(
      f"[experiment] profile={profile.name} "
      f"global_limit={profile.global_limit} guaranteed_per_lane={profile.guaranteed_per_lane}"
    )
    rerank_start = time.perf_counter()
    if args.skip_existing and rerank_path.exists():
      log(f"[experiment] reuse rerank: {rerank_path}")
    else:
      if hasattr(rank_mod, "random"):
        rank_mod.random.seed(args.seed)
      rank_mod.process_file(
        reranker=reranker,
        input_path=str(input_path),
        output_path=str(rerank_path),
        top_n=args.top_n,
        rerank_model=args.rerank_model,
        rerank_lane_top_k=profile.lane_top_k,
        rerank_guaranteed_per_lane=profile.guaranteed_per_lane,
        rerank_global_pool_limit=profile.global_limit,
      )
    rerank_seconds = time.perf_counter() - rerank_start

    llm_start = time.perf_counter()
    if args.skip_existing and llm_path.exists():
      log(f"[experiment] reuse llm: {llm_path}")
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
    scores = score_summary(llm_path)
    item = {
      "name": profile.name,
      "global_limit": profile.global_limit,
      "guaranteed_per_lane": profile.guaranteed_per_lane,
      "lane_top_k": profile.lane_top_k,
      "rerank_seconds": round(rerank_seconds, 3),
      "llm_seconds": round(llm_seconds, 3),
      "global_pool_effective_size": rerank_data.get("global_pool_effective_size"),
      "star_candidates": count_star_candidates(rerank_path, args.min_star),
      "rerank_path": str(rerank_path),
      "llm_path": str(llm_path),
      **scores,
    }
    summary["profiles"].append(item)
    write_json(output_dir / "summary.json", summary)
    log(
      "[experiment] done "
      f"{profile.name}: pool={item['global_pool_effective_size']} "
      f"star_candidates={item['star_candidates']} "
      f"score_ge_8={item['score_ge_8']} "
      f"top20_sum={item['top20_score_sum']} "
      f"rerank={item['rerank_seconds']:.1f}s llm={item['llm_seconds']:.1f}s"
    )

  ranked_profiles = sorted(
    summary["profiles"],
    key=lambda x: (
      -float(x.get("top20_score_sum") or 0.0),
      -int(x.get("score_ge_8") or 0),
      float(x.get("rerank_seconds") or 0.0),
    ),
  )
  summary["recommended"] = ranked_profiles[0]["name"] if ranked_profiles else ""
  write_json(output_dir / "summary.json", summary)
  log(f"[experiment] summary: {output_dir / 'summary.json'}")
  log(f"[experiment] recommended={summary['recommended']}")


if __name__ == "__main__":
  main()
