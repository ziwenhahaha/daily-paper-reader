"""研究方向入门包：固定窗口检索、版本去重、可恢复评审。"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from long_range_review import review_batch, review_cache_path, write_json
from paper_dedupe import deduplicate_papers
from starter_pack_retrieval import build_tasks, run_retrieval


def review_candidates(
    papers, topic, root, max_new_reviews=1000, *, client_factory=None, model_key=None
):
    if max_new_reviews < 0:
        raise ValueError("评审预算不能为负数；0表示本轮不新增付费评审")
    cache = Path(root) / ".local-runs/long-range-cache"
    if model_key is None:
        model_key = [
            os.getenv("DEEPSEEK_FILTER_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or "deepseek-v4-flash",
            os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
        ]
    if client_factory is None:

        def client_factory():
            from llm import DeepSeekClient

            key = os.getenv("DEEPSEEK_API_KEY") or ""
            if not key:
                raise RuntimeError(
                    "缺少DEEPSEEK_API_KEY，已保存召回结果，可以补配置后续跑"
                )
            client = DeepSeekClient(key, model_key[0], model_key[1])
            client.kwargs.update(
                temperature=0, max_tokens=6000, thinking={"type": "disabled"}
            )
            return client

    results, pending, cached = [], [], []
    for item in papers:
        paper = {
            **item,
            "title": str(item.get("title") or ""),
            "abstract": str(item.get("abstract") or ""),
        }
        versions = paper.get("versions") or [paper]
        has_verified_source = any(
            v.get("retrieval_source") == "arxiv"
            or v.get("source") == "arxiv"
            or v.get("conference_acceptance_status") == "accepted"
            or "conference_acceptance_status" not in v
            for v in versions
        )
        if not paper["abstract"].strip() or not has_verified_source:
            results.append(
                {
                    **paper,
                    "bucket": "notice",
                    "score": None,
                    "reason": (
                        "只有标题等元数据，尚不足以生成完整内容评审"
                        if not paper["abstract"].strip()
                        else "会议录用状态待核实，不能直接当作已录用顶会论文"
                    ),
                }
            )
        elif review_cache_path(paper, topic, cache, model_key).exists():
            cached.append(paper)
        else:
            pending.append(paper)
    # 先处理关键词命中较多的候选；预算不足不会删除其余记录。
    pending.sort(
        key=lambda p: (
            -sum(
                e.get("lane") == "bm25"
                for v in p.get("versions") or [p]
                for e in v.get("retrieval_evidence", [])
            ),
            p["id"],
        )
    )
    selected = pending[:max_new_reviews]
    work = cached + selected

    def review_with_retry(batch):
        for attempt in range(2):
            try:
                return review_batch(batch, topic, cache, client_factory, model_key)
            except ValueError as error:
                print(
                    f"[入门包评审] 结构校验失败，批次重试 {attempt+1}/2：{error}",
                    flush=True,
                )
                if attempt:
                    raise

    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [
            pool.submit(review_with_retry, work[i : i + 10])
            for i in range(0, len(work), 10)
        ]
        try:
            for i, job in enumerate(as_completed(jobs), 1):
                for paper, review in job.result():
                    results.append({**paper, **review})
                print(f"[入门包] 评审阶段 {i}/{len(jobs)} 批完成", flush=True)
        except Exception:
            for job in jobs:
                job.cancel()
            raise
    results.sort(key=lambda p: p.get("canonical_id") or p["id"])
    return {
        "papers": results,
        "remaining": len(pending) - len(selected),
        "new_reviews": len(selected),
        "cached_reviews": len(cached),
        "total_candidates": len(papers),
    }


def run_pack(
    config,
    profile_tag,
    as_of,
    root,
    *,
    conferences=None,
    max_new_reviews=1000,
    retrieve_only=False,
):
    root = Path(root)
    plan = build_tasks(config, profile_tag, as_of, conferences)
    folder = root / ".local-runs/starter-pack-cache/runs" / plan["run_id"]
    write_json(folder / "plan.json", plan)
    manifest = {
        "run_id": plan["run_id"],
        "status": "retrieving",
        "windows": plan["windows"],
        "profile": plan["profile"],
        "conferences": plan["conferences"],
    }
    write_json(folder / "manifest.json", manifest)
    try:
        retrieval = run_retrieval(plan, config, root)
        write_json(folder / "retrieval.json", retrieval)
        from starter_pack_publications import verify_publications

        checked = verify_publications(retrieval["papers"], root, resolve_pdfs=False)
        write_json(folder / "verified-publications.json", checked)
        retrieval["papers"] = [
            p for p in checked if p.get("conference_acceptance_status") != "rejected"
        ]
        retrieval["coverage"]["publication_acceptance"] = {
            status: sum(
                p.get("conference_acceptance_status") == status for p in checked
            )
            for status in ("accepted", "unverified", "rejected")
        }
        merged = deduplicate_papers(retrieval["papers"])
        write_json(folder / "merged.json", merged)
        manifest.update(
            status="retrieved",
            coverage=retrieval["coverage"],
            tasks=retrieval["tasks"],
            retrieved_records=len(retrieval["papers"]),
            unique_papers=len(merged["papers"]),
            possible_duplicates=len(merged["possible_duplicates"]),
        )
        if not retrieve_only:
            profile = plan["profile"]
            topic = {
                "tag": profile["tag"],
                "description": profile.get("description") or "",
                "queries": profile.get("queries") or [],
                "keywords": profile.get("review_keywords") or [],
            }
            reviewed = review_candidates(merged["papers"], topic, root, max_new_reviews)
            write_json(folder / "reviewed.json", reviewed)
            manifest.update(
                status="needs_resume" if reviewed["remaining"] else "reviewed",
                remaining=reviewed["remaining"],
                new_reviews=reviewed["new_reviews"],
                cached_reviews=reviewed["cached_reviews"],
            )
        write_json(folder / "manifest.json", manifest)
        return manifest
    except Exception as error:
        manifest.update(status="failed", error_type=type(error).__name__)
        write_json(folder / "manifest.json", manifest)
        raise


def main():
    from local_env import load_local_env
    import yaml

    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--profile-tag", required=True)
    parser.add_argument(
        "--as-of", default=datetime.now(timezone.utc).date().isoformat()
    )
    parser.add_argument(
        "--conferences", default="", help="留空按当前库存选择所有支持会议"
    )
    parser.add_argument("--max-new-reviews", type=int, default=1000)
    parser.add_argument("--retrieve-only", action="store_true")
    parser.add_argument("--content-limit", type=int, default=12)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.max_new_reviews <= 5000:
        parser.error("单次新增评审预算范围为0–5000；固定as-of重复运行即可续跑")
    if not 1 <= args.content_limit <= 20:
        parser.error("精选内容上限范围为1–20")
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    result = run_pack(
        config,
        args.profile_tag,
        args.as_of,
        args.root,
        conferences=args.conferences.split(",") if args.conferences else None,
        max_new_reviews=args.max_new_reviews,
        retrieve_only=args.retrieve_only,
    )
    if args.publish:
        from starter_pack_publish import publish_pack

        publish_pack(args.root, result, args.content_limit)
    print(
        json.dumps(
            {
                k: result.get(k)
                for k in (
                    "run_id",
                    "status",
                    "retrieved_records",
                    "unique_papers",
                    "remaining",
                    "new_reviews",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
