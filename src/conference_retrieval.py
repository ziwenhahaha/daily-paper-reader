#!/usr/bin/env python
"""Supabase-first conference paper candidate retrieval.

This script does not fetch full conference tables. It reads shared subscription
terms from config, queries conference Supabase RPCs for BM25 and embedding
candidates, and writes small pipeline-compatible JSON files for RRF/rerank.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
TODAY_STR = str(os.getenv("DPR_RUN_DATE") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
DEFAULT_OUTPUT_DIR = ROOT_DIR / "archive" / TODAY_STR / "filtered"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from filter import E5_QUERY_PREFIX, encode_queries  # noqa: E402
from model_loader import load_sentence_transformer  # noqa: E402
from source_config import get_source_backend, get_supabase_shared_config  # noqa: E402
from subscription_plan import build_pipeline_inputs  # noqa: E402
from supabase_source import match_papers_by_bm25, match_papers_by_embedding  # noqa: E402


CONFERENCE_DEFAULTS: Dict[str, Dict[str, str]] = {
    "icml": {
        "label": "ICML",
        "papers_table": "icml_openreview_papers",
        "bm25_rpc": "match_icml_openreview_papers_bm25",
        "vector_rpc_exact": "match_icml_openreview_papers_exact",
    },
    "neurips": {
        "label": "NeurIPS",
        "papers_table": "neurips_openreview_papers",
        "bm25_rpc": "match_neurips_openreview_papers_bm25",
        "vector_rpc_exact": "match_neurips_openreview_papers_exact",
    },
    "iclr": {
        "label": "ICLR",
        "papers_table": "iclr_openreview_papers",
        "bm25_rpc": "match_iclr_openreview_papers_bm25",
        "vector_rpc_exact": "match_iclr_openreview_papers_exact",
    },
    "aaai": {
        "label": "AAAI",
        "papers_table": "aaai_papers",
        "bm25_rpc": "match_aaai_papers_bm25",
        "vector_rpc_exact": "match_aaai_papers_exact",
    },
    "cvpr": {
        "label": "CVPR",
        "papers_table": "cvpr_papers",
        "bm25_rpc": "match_cvpr_papers_bm25",
        "vector_rpc_exact": "match_cvpr_papers_exact",
    },
    "eccv": {
        "label": "ECCV",
        "papers_table": "eccv_papers",
        "bm25_rpc": "match_eccv_papers_bm25",
        "vector_rpc_exact": "match_eccv_papers_exact",
    },
    "ijcai": {
        "label": "IJCAI",
        "papers_table": "ijcai_papers",
        "bm25_rpc": "match_ijcai_papers_bm25",
        "vector_rpc_exact": "match_ijcai_papers_exact",
    },
    "acl": {
        "label": "ACL",
        "papers_table": "acl_papers",
        "bm25_rpc": "match_acl_papers_bm25",
        "vector_rpc_exact": "match_acl_papers_exact",
    },
    "emnlp": {
        "label": "EMNLP",
        "papers_table": "emnlp_papers",
        "bm25_rpc": "match_emnlp_papers_bm25",
        "vector_rpc_exact": "match_emnlp_papers_exact",
    },
}

CONFERENCE_ALIASES = {
    "icml": "icml",
    "nips": "neurips",
    "neurips": "neurips",
    "iclr": "iclr",
    "aaai": "aaai",
    "cvpr": "cvpr",
    "eccv": "eccv",
    "ijcai": "ijcai",
    "acl": "acl",
    "emnlp": "emnlp",
}


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


@dataclass
class PaperHit:
    id: str
    title: str = ""
    abstract: str = ""
    authors: List[str] = field(default_factory=list)
    primary_category: str | None = None
    categories: List[str] = field(default_factory=list)
    published: str | None = None
    link: str | None = None
    pdf_url: str | None = None
    source: str = ""
    tags: set[str] = field(default_factory=set)
    best_score: float = 0.0

    @classmethod
    def from_row(cls, row: Dict[str, Any], score: float) -> "PaperHit":
        return cls(
            id=str(row.get("id") or "").strip(),
            title=str(row.get("title") or "").strip(),
            abstract=str(row.get("abstract") or "").strip(),
            authors=[str(a) for a in (row.get("authors") or [])],
            primary_category=str(row.get("primary_category") or "").strip() or None,
            categories=[str(c) for c in (row.get("categories") or [])],
            published=str(row.get("published") or "").strip() or None,
            link=str(row.get("link") or "").strip() or None,
            pdf_url=str(row.get("pdf_url") or "").strip() or None,
            source=str(row.get("source") or "").strip(),
            best_score=float(score),
        )

    def to_dict(self) -> Dict[str, Any]:
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
            "pdf_url": self.pdf_url,
            "tags": sorted(self.tags),
        }


def parse_csv_items(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def parse_conferences(value: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in parse_csv_items(value):
        key = CONFERENCE_ALIASES.get(raw.strip().lower())
        if not key:
            raise ValueError(f"不支持的会议：{raw}，当前仅支持 ICML / NIPS(NeurIPS)。")
        if key not in seen:
            seen.add(key)
            out.append(key)
    if not out:
        raise ValueError("至少需要指定一个会议。")
    return out


def parse_years(value: str) -> List[int]:
    years: List[int] = []
    seen = set()
    for raw in parse_csv_items(value):
        try:
            year = int(raw)
        except ValueError as exc:
            raise ValueError(f"年份不是整数：{raw}") from exc
        if year < 2000 or year > 2100:
            raise ValueError(f"年份超出合理范围：{year}")
        if year not in seen:
            seen.add(year)
            years.append(year)
    if not years:
        raise ValueError("至少需要指定一个年份。")
    return years


def year_window(year: int) -> Tuple[datetime, datetime]:
    # 会议论文的 published 日期通常比会议年份早 1 年（OpenReview 提交时间），
    # 所以窗口向前扩展 1 年以覆盖 "CONF-{year}" 的全部论文。
    # 后续由 source 字段中的年份标签做精确过滤。
    return (
        datetime(int(year) - 1, 1, 1, tzinfo=timezone.utc),
        datetime(int(year) + 1, 1, 1, tzinfo=timezone.utc),
    )


def build_years_token(years: Iterable[int]) -> str:
    values = [int(y) for y in years]
    if not values:
        return "unknown-years"
    sorted_values = sorted(values)
    if sorted_values == list(range(sorted_values[0], sorted_values[-1] + 1)):
        return f"{sorted_values[0]}-{sorted_values[-1]}" if len(sorted_values) > 1 else str(sorted_values[0])
    return "-".join(str(y) for y in values)


def load_config(path: str) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("未安装 PyYAML，无法解析配置。")
    if str(path or "").strip() == "-":
        data = yaml.safe_load(sys.stdin.read()) or {}
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("配置顶层结构必须是对象。")
    return data


def _fallback_shared_supabase(config: Dict[str, Any]) -> Dict[str, str]:
    shared = get_supabase_shared_config(config)
    legacy = config.get("supabase") if isinstance(config.get("supabase"), dict) else {}
    return {
        "url": str(shared.get("url") or legacy.get("url") or "").strip(),
        "anon_key": str(shared.get("anon_key") or legacy.get("anon_key") or "").strip(),
        "schema": str(shared.get("schema") or legacy.get("schema") or "public").strip() or "public",
    }


def resolve_conference_backend(config: Dict[str, Any], conference_key: str) -> Dict[str, Any]:
    defaults = CONFERENCE_DEFAULTS[conference_key]
    backend = {
        "enabled": True,
        "url": _fallback_shared_supabase(config).get("url", ""),
        "anon_key": _fallback_shared_supabase(config).get("anon_key", ""),
        "schema": _fallback_shared_supabase(config).get("schema", "public"),
        "papers_table": defaults["papers_table"],
        "use_bm25_rpc": True,
        "bm25_rpc": defaults["bm25_rpc"],
        "use_vector_rpc": True,
        "vector_rpc": defaults["vector_rpc_exact"],
        "vector_rpc_exact": defaults["vector_rpc_exact"],
    }
    configured = get_source_backend(config, conference_key)
    for key, value in configured.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        backend[key] = value
    return backend


def build_prefixed_query_text(text: str) -> str:
    value = str(text or "").strip()
    return f"{E5_QUERY_PREFIX}{value}" if value else ""


def parse_cached_embedding(entry: Any, *, expected_model: str, query_text: str) -> np.ndarray | None:
    if not isinstance(entry, dict):
        return None
    stored_model = str(entry.get("model") or "").strip().lower()
    if stored_model and stored_model != str(expected_model or "").strip().lower():
        return None
    stored_text = str(entry.get("prefixed_text") or "").strip()
    expected_text = build_prefixed_query_text(query_text)
    if stored_text and stored_text != expected_text:
        return None
    raw = entry.get("embedding_json")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    if not isinstance(raw, list) or not raw:
        raw = entry.get("embedding")
    if not isinstance(raw, list) or not raw:
        return None
    try:
        vec = np.asarray([float(x) for x in raw], dtype=np.float32)
    except Exception:
        return None
    if vec.ndim != 1 or vec.shape[0] <= 0:
        return None
    return vec


def clone_queries_for_conference(queries: List[Dict[str, Any]], conference_key: str) -> List[Dict[str, Any]]:
    cloned: List[Dict[str, Any]] = []
    for query in queries:
        item = copy.deepcopy(query)
        item["paper_sources"] = [conference_key]
        item["active_source"] = conference_key
        cloned.append(item)
    return cloned


def prepare_embedding_queries(
    queries: List[Dict[str, Any]],
    *,
    model_name: str,
    device: str,
    batch_size: int,
    max_length: int,
) -> None:
    missing_indices: List[int] = []
    missing_texts: List[str] = []
    cache_hits = 0
    for idx, query in enumerate(queries):
        q_text = str(query.get("query_text") or "").strip()
        cached = parse_cached_embedding(query.get("embedding_cache"), expected_model=model_name, query_text=q_text)
        if cached is not None:
            query["query_embedding"] = cached
            cache_hits += 1
            continue
        missing_indices.append(idx)
        missing_texts.append(q_text)

    if missing_indices:
        log(
            f"[INFO] 会议向量查询缓存：hits={cache_hits} misses={len(missing_indices)}，"
            "缺失部分将即时编码但不写回 config。"
        )
        model = load_sentence_transformer(model_name, device=device, log=log)
        encoded = encode_queries(model, missing_texts, batch_size=batch_size, max_length=max_length)
        for local_idx, query_idx in enumerate(missing_indices):
            queries[query_idx]["query_embedding"] = np.asarray(encoded[local_idx], dtype=np.float32)
    else:
        log(f"[INFO] 会议向量查询缓存：hits={cache_hits} misses=0。")


def score_from_row(row: Dict[str, Any], mode: str) -> float:
    key = "similarity" if mode == "embedding" else "score"
    value = row.get(key)
    if value is None:
        value = row.get("similarity")
    try:
        return float(value)
    except Exception:
        return 0.0


def build_result_for_queries(
    *,
    mode: str,
    queries: List[Dict[str, Any]],
    conferences: List[str],
    years: List[int],
    config: Dict[str, Any],
    top_k: int,
) -> Dict[str, Any]:
    id_to_paper: Dict[str, PaperHit] = {}
    output_queries: List[Dict[str, Any]] = []
    total_rpc_hits = 0

    for q_idx, query in enumerate(queries, start=1):
        q_text = str(query.get("query_text") or "").strip()
        paper_tag = str(query.get("paper_tag") or "").strip()
        candidates: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        if not q_text:
            continue

        for conference_key in conferences:
            backend = resolve_conference_backend(config, conference_key)
            if not backend.get("url") or not backend.get("anon_key"):
                raise RuntimeError(f"{CONFERENCE_DEFAULTS[conference_key]['label']} 缺少 Supabase url/anon_key。")
            for year in years:
                start_dt, end_dt = year_window(year)
                label = CONFERENCE_DEFAULTS[conference_key]["label"]
                if mode == "bm25":
                    rows, msg = match_papers_by_bm25(
                        url=str(backend.get("url") or ""),
                        api_key=str(backend.get("anon_key") or ""),
                        rpc_name=str(backend.get("bm25_rpc") or CONFERENCE_DEFAULTS[conference_key]["bm25_rpc"]),
                        query_text=q_text,
                        match_count=top_k,
                        schema=str(backend.get("schema") or "public"),
                        start_dt=start_dt,
                        end_dt=end_dt,
                        time_fields=("published",),
                    )
                else:
                    raw_embedding = query.get("query_embedding")
                    if isinstance(raw_embedding, np.ndarray):
                        query_embedding = raw_embedding.astype(np.float32).tolist()
                    else:
                        query_embedding = [float(x) for x in (raw_embedding or [])]
                    rows, msg = match_papers_by_embedding(
                        url=str(backend.get("url") or ""),
                        api_key=str(backend.get("anon_key") or ""),
                        rpc_name=str(
                            backend.get("vector_rpc_exact")
                            or backend.get("vector_rpc")
                            or CONFERENCE_DEFAULTS[conference_key]["vector_rpc_exact"]
                        ),
                        query_embedding=query_embedding,
                        match_count=top_k,
                        schema=str(backend.get("schema") or "public"),
                        start_dt=start_dt,
                        end_dt=end_dt,
                        time_fields=("published",),
                    )
                log(
                    f"[Supabase Conference {mode}] query={q_idx}/{len(queries)} "
                    f"tag={query.get('tag') or ''} conference={label} year={year} | {msg}"
                )
                total_rpc_hits += len(rows)
                # 按 source 字段中的会议年份过滤，避免时间窗口查询
                # 把不属于目标会议年份的论文剔除
                # source 格式如 "ICLR-2026-Public"、"AAAI-2025-Accepted"
                year_tag = f"-{year}-"
                for row in rows:
                    pid = str(row.get("id") or "").strip()
                    if not pid:
                        continue
                    row_source = str(row.get("source") or "")
                    if year_tag not in row_source:
                        continue
                    score = score_from_row(row, mode)
                    old = candidates.get(pid)
                    if old is None or score > old[0]:
                        candidates[pid] = (score, row)

        ranked = sorted(candidates.items(), key=lambda item: item[1][0], reverse=True)[:top_k]
        sim_scores: Dict[str, Dict[str, float | int]] = {}
        for rank, (pid, (score, row)) in enumerate(ranked, start=1):
            sim_scores[pid] = {"score": float(score), "rank": rank}
            paper = id_to_paper.get(pid)
            if paper is None:
                paper = PaperHit.from_row(row, score=score)
                id_to_paper[pid] = paper
            elif score > paper.best_score:
                replacement = PaperHit.from_row(row, score=score)
                replacement.tags = paper.tags
                paper = replacement
                id_to_paper[pid] = paper
            if paper_tag:
                paper.tags.add(paper_tag)

        output_queries.append(
            {
                "type": query.get("type"),
                "tag": query.get("tag"),
                "paper_tag": query.get("paper_tag"),
                "paper_sources": conferences,
                "query_text": q_text,
                "logic_cn": query.get("logic_cn") or "",
                "retrieval_mode": f"supabase_{mode}",
                "sim_scores": sim_scores,
            }
        )

    return {
        "queries": output_queries,
        "papers": id_to_paper,
        "total_rpc_hits": total_rpc_hits,
    }


def save_result(
    result: Dict[str, Any],
    path: Path,
    *,
    mode: str,
    top_k: int,
    conferences: List[str],
    years: List[int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    papers = [paper.to_dict() for paper in result.get("papers", {}).values() if paper.tags]
    payload = {
        "top_k": top_k,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "retrieval": {
            "mode": f"supabase_{mode}",
            "conferences": conferences,
            "years": years,
            "total_rpc_hits": int(result.get("total_rpc_hits") or 0),
        },
        "papers": papers,
        "queries": result.get("queries") or [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    non_empty = sum(1 for q in payload["queries"] if q.get("sim_scores"))
    log(
        f"[INFO] 已写入 {mode} 候选：{path} | "
        f"queries={len(payload['queries'])} non_empty={non_empty} papers={len(papers)}"
    )


def output_paths(output_dir: Path, conferences: List[str], years: List[int]) -> Tuple[Path, Path]:
    conf_token = "-".join(conferences)
    year_token = build_years_token(years)
    base = f"conference-{conf_token}-{year_token}.supabase"
    return (
        output_dir / f"{base}.bm25.json",
        output_dir / f"{base}.embedding.json",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="会议论文 Supabase-first 候选召回。")
    parser.add_argument("--config", type=str, default=str(ROOT_DIR / "config.yaml"), help="配置文件路径；传 - 可从 stdin 读取。")
    parser.add_argument("--conferences", "--conference", dest="conferences", type=str, required=True, help="会议列表：ICML,NIPS。")
    parser.add_argument("--years", type=str, required=True, help="年份列表，例如 2024,2025。")
    parser.add_argument("--top-k", type=int, default=50, help="每个查询最终保留的候选数。")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="输出目录。")
    parser.add_argument("--embedding-model", type=str, default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--embedding-device", type=str, default="cpu")
    parser.add_argument("--embedding-batch-size", type=int, default=8)
    parser.add_argument("--embedding-max-length", type=int, default=512)
    parser.add_argument("--skip-bm25", action="store_true")
    parser.add_argument("--skip-embedding", action="store_true")
    args = parser.parse_args()

    conferences = parse_conferences(args.conferences)
    years = parse_years(args.years)
    top_k = max(int(args.top_k or 1), 1)
    config = load_config(args.config)
    os.environ["DPR_INCLUDE_CONFERENCE_ONLY_PROFILES"] = "1"
    plan = build_pipeline_inputs(config)
    bm25_queries = clone_queries_for_conference(plan.get("bm25_queries") or [], ",".join(conferences))
    embedding_queries = clone_queries_for_conference(plan.get("embedding_queries") or [], ",".join(conferences))
    if not bm25_queries and not embedding_queries:
        raise SystemExit("未从配置解析到 intent_profiles 查询；请先保存词条配置。")

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT_DIR / output_dir
    bm25_path, embedding_path = output_paths(output_dir, conferences, years)
    log(
        f"[INFO] 会议候选召回：conferences={conferences} years={years} "
        f"top_k={top_k} bm25_queries={len(bm25_queries)} embedding_queries={len(embedding_queries)}"
    )

    if not args.skip_bm25:
        bm25_result = build_result_for_queries(
            mode="bm25",
            queries=bm25_queries,
            conferences=conferences,
            years=years,
            config=config,
            top_k=top_k,
        )
        save_result(bm25_result, bm25_path, mode="bm25", top_k=top_k, conferences=conferences, years=years)

    if not args.skip_embedding:
        prepare_embedding_queries(
            embedding_queries,
            model_name=args.embedding_model,
            device=args.embedding_device,
            batch_size=max(int(args.embedding_batch_size or 1), 1),
            max_length=max(int(args.embedding_max_length or 1), 1),
        )
        emb_result = build_result_for_queries(
            mode="embedding",
            queries=embedding_queries,
            conferences=conferences,
            years=years,
            config=config,
            top_k=top_k,
        )
        save_result(emb_result, embedding_path, mode="embedding", top_k=top_k, conferences=conferences, years=years)


if __name__ == "__main__":
    main()
