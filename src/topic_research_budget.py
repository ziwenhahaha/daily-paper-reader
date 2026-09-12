"""专题研究的资格、融合、云端重排与最终数量预算。"""

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path

from paper_dedupe import deduplicate_papers
from starter_pack_reading import _project_version, _qualified_version


def _limit(value, maximum, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= maximum
    ):
        raise ValueError(f"{name} 必须为 0–{maximum} 的整数")


def _identity(paper):
    return str(paper.get("canonical_id") or paper.get("id") or "")


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _project(work):
    # 已评审的代表本身合格时保持原版，避免无意义切换摘要与评审缓存键。
    if _qualified_version(work):
        return _project_version(work, work)
    versions = work.get("versions") or [work]
    qualified = [v for v in versions if _qualified_version(v)]
    if not qualified:
        return None
    qualified.sort(
        key=lambda p: (
            -len(str(p.get("abstract") or "")),
            not bool(p.get("pdf_url")),
            str(p.get("id") or ""),
        )
    )
    return _project_version(work, qualified[0])


def _remote_config():
    # 复用日常公共服务配置，但只创建远端适配器，不实例化或导入本地模型。
    spec = importlib.util.spec_from_file_location(
        "topic_budget_rank_config", Path(__file__).with_name("3.rank_papers.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profile = module._normalize_rerank_profile(
        os.getenv("RERANK_PROFILE", "public-zwwen-rerank")
    )
    config = dict(module.RERANK_PROFILE_CONFIGS.get(profile) or {})
    provider = str(
        os.getenv("RERANK_PROVIDER") or config.get("provider") or "public_zwwen"
    ).replace("-", "_")
    if provider in (
        "public",
        "zwwen",
        "public_zwwen_rerank",
        "local",
        "hf",
        "huggingface",
    ):
        provider = "public_zwwen"
        config = dict(module.RERANK_PROFILE_CONFIGS["public-zwwen-rerank"])
    if provider in ("sf", "remote"):
        provider = "siliconflow"
    if provider not in ("public_zwwen", "siliconflow"):
        raise RuntimeError("专题研究只支持云端 reranker")
    return {
        "api_key": module._resolve_remote_api_key(provider),
        "base_url": module._resolve_remote_base_url(provider, config),
        "model": os.getenv("RERANK_MODEL")
        or config.get("model")
        or module.DEFAULT_LOCAL_RERANK_MODEL,
    }


def _query(topic):
    if isinstance(topic, str):
        return topic.strip()
    return "\n".join(
        str(topic.get(key) or "")
        for key in ("tag", "description", "intent_queries", "queries", "keywords")
    ).strip()


def _rerank(papers, topic, root, client_factory):
    from reranker_api import SiliconFlowReranker, DEFAULT_QWEN3_RERANK_INSTRUCTION

    config = _remote_config()
    query = _query(topic)
    if not query:
        raise ValueError("专题重排 query 不能为空")
    cache = Path(root) / ".local-runs" / "topic-research-rerank-cache"
    pending, hits = [], 0
    for paper in papers:
        document = (
            "Title: "
            + str(paper.get("title") or "")
            + "\n\nAbstract: "
            + str(paper.get("abstract") or "")
        )
        fingerprint = json.dumps(
            {
                "schema": 1,
                "query": query,
                "document": document,
                "model": config["model"],
                "endpoint": config["base_url"],
                "instruction": DEFAULT_QWEN3_RERANK_INSTRUCTION,
            },
            sort_keys=True,
        )
        path = cache / (hashlib.sha256(fingerprint.encode()).hexdigest() + ".json")
        try:
            value = json.loads(path.read_text())["score"]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError("invalid cache score")
            paper["rerank_score"] = value
            hits += 1
        except (OSError, ValueError, KeyError, TypeError):
            pending.append((paper, document, path))
    if not pending:
        return hits, 0
    client = (client_factory or SiliconFlowReranker)(
        api_key=config["api_key"], base_url=config["base_url"]
    )
    configured_batch = getattr(client, "max_documents_per_request", 64)
    batch_size = (
        min(max(configured_batch, 1), 64) if isinstance(configured_batch, int) else 64
    )
    calls = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        try:
            result = client.rerank(
                query=query,
                documents=[row[1] for row in batch],
                top_n=len(batch),
                model=config["model"],
            )
            scores = {}
            for row in result["results"]:
                index, score = row["index"], row["relevance_score"]
                if (
                    isinstance(index, bool)
                    or not isinstance(index, int)
                    or index in scores
                    or not 0 <= index < len(batch)
                    or isinstance(score, bool)
                    or not isinstance(score, (int, float))
                    or not math.isfinite(score)
                ):
                    raise ValueError("invalid rerank result")
                scores[index] = score
            if len(scores) != len(batch):
                raise ValueError("incomplete rerank response")
        except Exception:
            # 不回显可能带鉴权信息的上游异常，也不把失败伪装成 RRF 重排成功。
            raise RuntimeError(
                "云端重排失败或返回分数不完整；请重试，已完成批次会复用缓存"
            ) from None
        calls += 1
        cache.mkdir(parents=True, exist_ok=True)
        for index, (paper, _, path) in enumerate(batch):
            paper["rerank_score"] = scores[index]
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps({"score": scores[index]}), encoding="utf-8")
            temp.replace(path)
    return hits, calls


def build_review_pool(
    papers,
    topic,
    root,
    pool_limit=1000,
    review_limit=300,
    rerank=True,
    client_factory=None,
):
    """先资格与版本去重，再 RRF Top1000 / 云重排 Top300；不调用 LLM。"""
    _limit(pool_limit, 1000, "pool_limit")
    _limit(review_limit, 300, "review_limit")
    rows = list(papers)
    deduped = deduplicate_papers(rows)["papers"]
    eligible, missing_ranks = [], 0
    for work in deduped:
        projected = _project(work)
        if projected is None:
            continue
        lanes = {}
        for version in work.get("versions") or [work]:
            if not _qualified_version(version):
                continue
            for evidence in version.get("retrieval_evidence") or []:
                key = (
                    str(evidence.get("lane") or ""),
                    str(evidence.get("query_text") or evidence.get("query") or ""),
                )
                rank = evidence.get("rank", evidence.get("query_rank"))
                if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                    rank = 1
                    missing_ranks += 1
                lanes[key] = min(lanes.get(key, rank), rank)
        projected["rrf_score"] = sum(1.0 / (60 + rank) for rank in lanes.values())
        eligible.append(projected)
    eligible.sort(key=lambda p: (-p["rrf_score"], _identity(p)))
    pool = eligible[:pool_limit] if review_limit else []
    hits, calls = (
        _rerank(pool, topic, root, client_factory) if rerank and pool else (0, 0)
    )
    pool.sort(
        key=lambda p: (
            -_number(p.get("rerank_score")) if rerank else 0,
            -p["rrf_score"],
            _identity(p),
        )
    )
    return {
        "papers": pool[:review_limit],
        "coverage": {
            "input_count": len(rows),
            "deduplicated_count": len(deduped),
            "eligible_count": len(eligible),
            "excluded_unqualified_count": len(deduped) - len(eligible),
            "pool_count": len(pool),
            "review_count": len(pool[:review_limit]),
            "pool_limit": pool_limit,
            "review_limit": review_limit,
            "rerank_enabled": bool(rerank),
            "rerank_cache_hits": hits,
            "rerank_calls": calls,
            "evidence_without_rank": missing_ranks,
            "unranked_evidence_policy": "equal_rank_one",
            "guarantees_all_relevant_papers": False,
        },
    }


def select_final_papers(reviewed, result_limit=100):
    """只选择合格且达到六分的 core/related，按分数优先，绝不凑数。"""
    _limit(result_limit, 100, "result_limit")
    eligible = []
    for work in reviewed:
        if (
            work.get("bucket") not in ("core", "related")
            or isinstance(work.get("score"), bool)
            or not 6 <= _number(work.get("score")) <= 10
        ):
            continue
        projected = _project(work)
        if projected is not None:
            eligible.append(projected)
    # 稳定排序分别实现日期倒序、同日期稳定 ID，避免人为 bucket 优先。
    eligible.sort(key=_identity)
    eligible.sort(key=lambda p: str(p.get("publication_date") or ""), reverse=True)
    eligible.sort(
        key=lambda p: (_number(p.get("score")), _number(p.get("rerank_score"))),
        reverse=True,
    )
    result, seen = [], set()
    for paper in eligible:
        identity = _identity(paper)
        if identity not in seen:
            seen.add(identity)
            result.append(paper)
    return result[:result_limit]
