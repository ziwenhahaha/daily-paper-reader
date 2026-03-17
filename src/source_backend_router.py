from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List, Tuple

try:
    from source_config import ARXIV_SOURCE_KEY, normalize_source_list
except Exception:  # pragma: no cover - 兼容 package 导入路径
    from src.source_config import ARXIV_SOURCE_KEY, normalize_source_list


def get_query_paper_sources(query: Dict[str, Any]) -> List[str]:
    if not isinstance(query, dict):
        return [ARXIV_SOURCE_KEY]
    sources = normalize_source_list(query.get("paper_sources"))
    return sources or [ARXIV_SOURCE_KEY]


def group_queries_by_source(queries: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for query in queries or []:
        if not isinstance(query, dict):
            continue
        for source_key in get_query_paper_sources(query):
            copied = dict(query)
            copied["active_source"] = source_key
            grouped.setdefault(source_key, []).append(copied)
    return grouped


def build_query_merge_key(query: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    return (
        str(query.get("type") or ""),
        str(query.get("tag") or ""),
        str(query.get("paper_tag") or ""),
        str(query.get("query_text") or ""),
        str(query.get("logic_cn") or ""),
        str(query.get("boolean_expr") or ""),
    )


def _merge_sim_scores(target: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    for paper_id, meta in incoming.items():
        if paper_id not in target:
            target[paper_id] = dict(meta) if isinstance(meta, dict) else meta
            continue
        if not isinstance(meta, dict):
            target[paper_id] = meta
            continue
        existing = target.get(paper_id)
        if not isinstance(existing, dict):
            target[paper_id] = dict(meta)
            continue

        new_rank = meta.get("rank")
        old_rank = existing.get("rank")
        if isinstance(new_rank, (int, float)):
            if not isinstance(old_rank, (int, float)) or int(new_rank) < int(old_rank):
                existing["rank"] = int(new_rank)

        new_score = meta.get("score")
        old_score = existing.get("score")
        if isinstance(new_score, (int, float)):
            if not isinstance(old_score, (int, float)) or float(new_score) > float(old_score):
                existing["score"] = float(new_score)

        for key, value in meta.items():
            if key not in ("rank", "score") and key not in existing:
                existing[key] = value


def merge_pipeline_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged_queries: "OrderedDict[Tuple[str, str, str, str, str, str], Dict[str, Any]]" = OrderedDict()
    merged_papers: Dict[str, Any] = {}

    for result in results or []:
        if not isinstance(result, dict):
            continue
        for paper_id, paper in (result.get("papers") or {}).items():
            if paper_id not in merged_papers:
                merged_papers[paper_id] = paper

        for query in result.get("queries") or []:
            if not isinstance(query, dict):
                continue
            key = build_query_merge_key(query)
            if key not in merged_queries:
                copied = dict(query)
                copied["sim_scores"] = {}
                copied["paper_sources"] = normalize_source_list(query.get("paper_sources"))
                merged_queries[key] = copied

            target = merged_queries[key]
            _merge_sim_scores(target.setdefault("sim_scores", {}), query.get("sim_scores") or {})
            merged_sources = normalize_source_list(target.get("paper_sources")) + normalize_source_list(query.get("paper_sources"))
            target["paper_sources"] = normalize_source_list(merged_sources)

    total_hits = sum(len((query.get("sim_scores") or {})) for query in merged_queries.values())
    non_empty_queries = sum(1 for query in merged_queries.values() if query.get("sim_scores"))
    return {
        "queries": list(merged_queries.values()),
        "papers": merged_papers,
        "total_hits": total_hits,
        "non_empty_queries": non_empty_queries,
    }
