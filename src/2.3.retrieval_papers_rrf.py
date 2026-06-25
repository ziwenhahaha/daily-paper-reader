#!/usr/bin/env python
# Fuse BM25 + Embedding recall results with RRF (Reciprocal Rank Fusion):
# 1. Read BM25 and Embedding filtered JSON outputs;
# 2. For each query, fuse rankings via RRF and deduplicate;
# 3. Truncate to Top N and tag the selected papers;
# 4. Write fused JSON for the next reranker step.

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TODAY_STR = str(os.getenv("DPR_RUN_DATE") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
ARCHIVE_DIR = os.path.join(ROOT_DIR, "archive", TODAY_STR)
FILTERED_DIR = os.path.join(ARCHIVE_DIR, "filtered")

def log(message: str) -> None:
  ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
  print(f"[{ts}] {message}", flush=True)


def group_start(title: str) -> None:
  print(f"::group::{title}", flush=True)


def group_end() -> None:
  print("::endgroup::", flush=True)


def load_json(path: str) -> Dict[str, Any]:
  if not os.path.exists(path):
    raise FileNotFoundError(f"File not found: {path}")
  with open(path, "r", encoding="utf-8") as f:
    return json.load(f)


def save_json(data: Dict[str, Any], path: str) -> None:
  os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
  log(f"[INFO] Wrote fused results to: {path}")


def make_query_key(q: Dict[str, Any]) -> Tuple[str, str, str]:
  """
  Build a stable key to align BM25 / Embedding queries.
  Keep both paper_tag and query_text so multiple semantic queries under the same tag are not overwritten.
  """
  q_type = str(q.get("type") or "")
  paper_tag = str(q.get("paper_tag") or q.get("tag") or "")
  query_text = str(q.get("query_text") or "")
  return (q_type, paper_tag, query_text)


def normalize_rank_list(sim_scores: Any) -> List[Tuple[str, int]]:
  """Extract a (paper_id, rank) list from sim_scores."""
  if not isinstance(sim_scores, dict) or not sim_scores:
    return []

  items: List[Tuple[str, float | None, int | None]] = []
  for pid, meta in sim_scores.items():
    if isinstance(meta, dict):
      score = meta.get("score")
      rank = meta.get("rank")
    else:
      score = None
      rank = None
    items.append((str(pid), float(score) if score is not None else None, int(rank) if rank is not None else None))

  has_rank = all(r is not None for _, _, r in items)
  if has_rank:
    items_sorted = sorted(items, key=lambda x: x[2] if x[2] is not None else 0)
  else:
    items_sorted = sorted(items, key=lambda x: (x[1] is None, -(x[1] or 0.0)))

  rank_list: List[Tuple[str, int]] = []
  for idx, (pid, _score, _rank) in enumerate(items_sorted, start=1):
    rank_list.append((pid, idx))
  return rank_list


def rrf_fuse(
  bm25_ranks: List[Tuple[str, int]],
  emb_ranks: List[Tuple[str, int]],
  rrf_k: int,
) -> Dict[str, float]:
  score_map: Dict[str, float] = {}

  for pid, rank in bm25_ranks:
    score_map[pid] = score_map.get(pid, 0.0) + 1.0 / (rrf_k + rank)
  for pid, rank in emb_ranks:
    score_map[pid] = score_map.get(pid, 0.0) + 1.0 / (rrf_k + rank)

  return score_map


def build_paper_map(papers_list: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
  id_to_paper: Dict[str, Dict[str, Any]] = {}
  for p in papers_list:
    pid = str(p.get("id") or "").strip()
    if not pid:
      continue
    if pid not in id_to_paper:
      copied = dict(p)
      copied["tags"] = set(p.get("tags") or [])
      id_to_paper[pid] = copied
    else:
      id_to_paper[pid]["tags"].update(p.get("tags") or [])
  return id_to_paper


def merge_paper_maps(
  base: Dict[str, Dict[str, Any]],
  incoming: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
  """Merge two paper maps; tags are unioned, other fields prefer existing values."""
  for pid, paper in incoming.items():
    if pid not in base:
      base[pid] = paper
      continue
    base_tags = base[pid].get("tags") or set()
    incoming_tags = paper.get("tags") or set()
    if not isinstance(base_tags, set):
      base_tags = set(base_tags)
    if not isinstance(incoming_tags, set):
      incoming_tags = set(incoming_tags)
    base[pid]["tags"] = base_tags.union(incoming_tags)
    for k, v in paper.items():
      if k == "tags":
        continue
      if not base[pid].get(k) and v:
        base[pid][k] = v
  return base


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 2.3: fuse BM25 + Embedding recall results with RRF and tag papers.",
  )

  parser.add_argument(
    "--bm25-input",
    type=str,
    default=os.path.join(FILTERED_DIR, f"arxiv_papers_{TODAY_STR}.bm25.json"),
    help="BM25 recall JSON (default archive/YYYYMMDD/filtered/arxiv_papers_YYYYMMDD.bm25.json).",
  )
  parser.add_argument(
    "--embedding-input",
    type=str,
    default=os.path.join(FILTERED_DIR, f"arxiv_papers_{TODAY_STR}.embedding.json"),
    help="Embedding recall JSON (default archive/YYYYMMDD/filtered/arxiv_papers_YYYYMMDD.embedding.json).",
  )
  parser.add_argument(
    "--output",
    type=str,
    default=os.path.join(FILTERED_DIR, f"arxiv_papers_{TODAY_STR}.json"),
    help="Fused output JSON (default archive/YYYYMMDD/filtered/arxiv_papers_YYYYMMDD.json).",
  )
  parser.add_argument(
    "--top-n",
    type=int,
    default=200,
    help="Top N papers to keep after RRF fusion (default 200).",
  )
  parser.add_argument(
    "--rrf-k",
    type=int,
    default=60,
    help="RRF k parameter (default 60).",
  )

  args = parser.parse_args()

  bm25_path = args.bm25_input
  if not os.path.isabs(bm25_path):
    bm25_path = os.path.abspath(os.path.join(ROOT_DIR, bm25_path))

  emb_path = args.embedding_input
  if not os.path.isabs(emb_path):
    emb_path = os.path.abspath(os.path.join(ROOT_DIR, emb_path))

  out_path = args.output
  if not os.path.isabs(out_path):
    out_path = os.path.abspath(os.path.join(ROOT_DIR, out_path))

  # If input files are missing, there are no new papers today; exit gracefully
  if not os.path.exists(bm25_path) and not os.path.exists(emb_path):
    log("[INFO] Neither BM25 nor Embedding result file exists (no new papers today; skipping RRF fusion)")
    return

  if not os.path.exists(bm25_path):
    log(f"[INFO] BM25 result file not found: {bm25_path} (skipping RRF fusion)")
    return

  if not os.path.exists(emb_path):
    log(f"[INFO] Embedding result file not found: {emb_path} (skipping RRF fusion)")
    return

  group_start("Step 2.3 - load inputs")
  bm25_data = load_json(bm25_path)
  emb_data = load_json(emb_path)
  group_end()

  bm25_queries = bm25_data.get("queries") or []
  emb_queries = emb_data.get("queries") or []

  bm25_map = {make_query_key(q): q for q in bm25_queries}
  emb_map = {make_query_key(q): q for q in emb_queries}

  all_keys = sorted({*bm25_map.keys(), *emb_map.keys()})
  log(f"[INFO] RRF keys={len(all_keys)} | bm25_queries={len(bm25_queries)} | emb_queries={len(emb_queries)}")

  group_start("Step 2.3 - merge papers")
  id_to_paper = build_paper_map(bm25_data.get("papers") or [])
  id_to_paper = merge_paper_maps(id_to_paper, build_paper_map(emb_data.get("papers") or []))
  log(f"[INFO] merged papers={len(id_to_paper)}")
  group_end()

  fused_queries: List[Dict[str, Any]] = []

  group_start("Step 2.3 - fuse queries")
  for idx, key in enumerate(all_keys, start=1):
    bm25_q = bm25_map.get(key) or {}
    emb_q = emb_map.get(key) or {}

    q_type, q_key_tag, q_key_text = key
    if not q_key_text and not q_key_tag:
      continue
    log(f"[INFO] fuse {idx}/{len(all_keys)} type={q_type} key={q_key_tag} | text={q_key_text[:80]}")
    q_tag = bm25_q.get("tag") or emb_q.get("tag") or ""
    q_paper_tag = bm25_q.get("paper_tag") or emb_q.get("paper_tag") or ""
    q_text = bm25_q.get("query_text") or emb_q.get("query_text") or ""

    bm25_ranks = normalize_rank_list(bm25_q.get("sim_scores"))
    emb_ranks = normalize_rank_list(emb_q.get("sim_scores"))

    score_map = rrf_fuse(bm25_ranks, emb_ranks, args.rrf_k)
    if not score_map:
      continue

    sorted_items = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
    top_items = sorted_items[: args.top_n]

    sim_scores: Dict[str, Dict[str, float | int]] = {}
    for rank_idx, (pid, score) in enumerate(top_items, start=1):
      sim_scores[pid] = {"score": float(score), "rank": rank_idx}
      if q_paper_tag and pid in id_to_paper:
        id_to_paper[pid]["tags"].add(q_paper_tag)

    fused_queries.append(
      {
        "type": q_type,
        "tag": q_tag,
        "paper_tag": q_paper_tag,
        "query_text": q_text,
        "sim_scores": sim_scores,
      }
    )
  group_end()

  tagged_papers = []
  for p in id_to_paper.values():
    tags = p.get("tags") or set()
    if isinstance(tags, set):
      p["tags"] = sorted(tags)
    if p.get("tags"):
      tagged_papers.append(p)

  payload = {
    "top_k": args.top_n,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "papers": tagged_papers,
    "queries": fused_queries,
  }

  save_json(payload, out_path)


if __name__ == "__main__":
  main()
