"""专题研究统一编排：固定需求快照、有界评分、最多100篇、内容独立续跑。"""

from __future__ import annotations

import argparse
import copy
from datetime import date, datetime, timezone
import json
import re
from pathlib import Path

from long_range_review import fingerprint, write_json
from starter_pack_retrieval import build_tasks, run_retrieval
from starter_pack_publications import verify_publications
from paper_dedupe import deduplicate_papers
from starter_pack import review_candidates
from topic_research_budget import build_review_pool, select_final_papers

VERSION = "topic-research-v2"
MODES = {"90", "365", "starter"}
RUN_ID = re.compile(r"\d{8}-[a-f0-9]{12}")


def restore_published_task(root, run_id):
    """Actions缓存可淘汰；已发布的固定名单不依赖缓存存活。"""
    folder = Path(root) / ".local-runs/starter-pack-cache/runs" / run_id
    published = Path(root) / "docs/starter-pack" / run_id / "task-state.json"
    if (
        not (folder / "selected.json").exists()
        or not (folder / "manifest.json").exists()
    ) and published.exists():
        state = json.loads(published.read_text(encoding="utf-8"))
        manifest, selection = state.get("manifest") or {}, state.get("selection") or {}
        if (
            manifest.get("run_id") != run_id
            or manifest.get("research_version") != VERSION
            or not selection.get("selection_complete")
            or not isinstance(selection.get("papers"), list)
            or len(selection["papers"]) > 100
        ):
            raise ValueError("已发布任务快照无效，未重新检索或收费")
        write_json(folder / "manifest.json", manifest)
        write_json(folder / "selected.json", selection)
    return folder


def safe_profile(value, tag):
    if not isinstance(value, dict) or value.get("tag") != tag:
        raise ValueError("需求快照必须对应所选词条")
    result = {"tag": tag, "enabled": True, "paused": False, "paper_sources": ["arxiv"]}
    for key in ("description", "refinement"):
        text = value.get(key) or ""
        if not isinstance(text, str) or len(text) > 6000:
            raise ValueError("需求说明过长或格式无效")
        result[key] = text
    for key, field, maximum in (
        ("keywords", "keyword", 24),
        ("intent_queries", "query", 12),
    ):
        rows = value.get(key) or []
        if not isinstance(rows, list) or len(rows) > maximum:
            raise ValueError("查询数量超出任务预算")
        cleaned = []
        for row in rows:
            if isinstance(row, str):
                row = {field: row}
            if not isinstance(row, dict):
                raise ValueError("查询格式无效")
            if str(row.get("enabled", True)).strip().lower() in (
                "false",
                "0",
                "no",
                "off",
            ):
                continue
            text = (
                (row.get("keyword") or row.get("text") or row.get("query") or "")
                if key == "keywords"
                else (row.get(field) or "")
            )
            if not isinstance(text, str) or not text.strip() or len(text) > 1200:
                raise ValueError("查询内容无效")
            entry = {field: text.strip(), "enabled": True}
            if key == "keywords" and row.get("query"):
                semantic = row["query"]
                if not isinstance(semantic, str) or len(semantic) > 1200:
                    raise ValueError("语义重写内容无效")
                entry["query"] = semantic.strip()
            cleaned.append(entry)
        result[key] = cleaned
    groups = value.get("constraint_groups") or []
    if groups:
        combinations = 1
        if not isinstance(groups, list) or len(groups) > 3:
            raise ValueError("检索约束组无效")
        for group in groups:
            if (
                not isinstance(group, list)
                or not 1 <= len(group) <= 8
                or any(
                    not isinstance(term, str)
                    or not term.strip()
                    or len(term) > 300
                    or not re.search(r"[A-Za-z]", term)
                    or re.search(r"[\u3400-\u9fff]", term)
                    for term in group
                )
            ):
                raise ValueError("约束组必须包含可执行的英文检索词")
            combinations *= len(group)
        if combinations > 32:
            raise ValueError("检索约束组合超过32种")
        result["constraint_groups"] = copy.deepcopy(groups)
    if result["refinement"] and not groups:
        raise ValueError("细化需求缺少实际检索约束，不能只修改显示说明")
    return result


def research_plan(
    config, profile_tag, mode, as_of, profile_snapshot=None, conferences=None
):
    if mode not in MODES:
        raise ValueError("专题研究仅支持90天、365天和研究方向大礼包")
    date.fromisoformat(as_of)
    profiles = (config.get("subscriptions") or {}).get("intent_profiles") or []
    original = [
        p for p in profiles if isinstance(p, dict) and p.get("tag") == profile_tag
    ]
    if len(original) != 1:
        raise ValueError("请选择唯一已保存词条")
    snapshot = safe_profile(
        profile_snapshot if profile_snapshot is not None else original[0], profile_tag
    )
    scoped = copy.deepcopy(config)
    scoped.setdefault("subscriptions", {})["intent_profiles"] = [snapshot]
    plan = build_tasks(
        scoped,
        profile_tag,
        as_of,
        conferences if mode == "starter" else [],
        arxiv_days=90 if mode == "90" else 365,
        bounded=True,
    )
    plan.update(mode=mode, snapshot=snapshot, research_version=VERSION)
    if mode != "starter":
        # 90/365只查询arXiv，不把未执行的会议窗口写进结果或任务身份。
        plan["windows"].pop("conference", None)
    plan["run_id"] = (
        as_of.replace("-", "")
        + "-"
        + fingerprint(
            {
                "version": VERSION,
                "snapshot": snapshot,
                "mode": mode,
                "windows": plan["windows"],
                "conferences": plan["conferences"],
                "review_limit": 300,
                "result_limit": 100,
            }
        )[:12]
    )
    return plan, scoped


def run_research(
    config,
    profile_tag,
    mode,
    as_of,
    root,
    *,
    profile_snapshot=None,
    conferences=None,
    content_batch=10,
    action="run",
    run_id=None,
    publish=True,
    retrieve_only=False,
    max_new_reviews=300,
):
    if (
        isinstance(content_batch, bool)
        or not isinstance(content_batch, int)
        or not 0 <= content_batch <= 100
    ):
        raise ValueError("每轮内容预算必须在0–100之间")
    if (
        isinstance(max_new_reviews, bool)
        or not isinstance(max_new_reviews, int)
        or not 0 <= max_new_reviews <= 300
    ):
        raise ValueError("新增评审预算必须在0–300之间")
    root = Path(root).resolve()
    base = root / ".local-runs/starter-pack-cache/runs"
    if action == "continue-content":
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise ValueError("继续生成需要有效任务标识")
        folder = restore_published_task(root, run_id)
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        selected = json.loads((folder / "selected.json").read_text(encoding="utf-8"))
        if manifest.get("research_version") != VERSION or not selected.get(
            "selection_complete"
        ):
            raise ValueError("任务名单尚未确定，不能继续内容阶段")
        if manifest.get("mode") != "starter":
            manifest.get("windows", {}).pop("conference", None)
        manifest.update(
            content_batch=content_batch,
            status="selection_ready",
            last_action="continue-content",
            new_reviews=0,
        )
    elif action == "run":
        plan, scoped = research_plan(
            config, profile_tag, mode, as_of, profile_snapshot, conferences
        )
        run_id = plan["run_id"]
        folder = restore_published_task(root, run_id)
        if (folder / "selected.json").exists():
            # 已有固定名单的重复启动只继续内容，不重新召回或扩大评审。
            return run_research(
                config,
                profile_tag,
                mode,
                as_of,
                root,
                content_batch=content_batch,
                action="continue-content",
                run_id=run_id,
                publish=publish,
            )
        write_json(folder / "plan.json", plan)
        manifest = {
            "research_version": VERSION,
            "run_id": run_id,
            "mode": mode,
            "profile": plan["profile"],
            "snapshot": plan["snapshot"],
            "windows": plan["windows"],
            "conferences": plan["conferences"],
            "status": "retrieving",
            "review_limit": 300,
            "result_limit": 100,
            "pool_limit": 1000,
            "content_batch": content_batch,
        }
        write_json(folder / "manifest.json", manifest)
        try:
            pool_path = folder / "review-pool.json"
            if pool_path.exists():
                pool = json.loads(pool_path.read_text(encoding="utf-8"))
                retrieval = json.loads(
                    (folder / "retrieval.json").read_text(encoding="utf-8")
                )
                merged = json.loads(
                    (folder / "merged.json").read_text(encoding="utf-8")
                )
            else:
                retrieval_path = folder / "retrieval.json"
                if retrieval_path.exists():
                    retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
                else:
                    retrieval = run_retrieval(plan, scoped, root)
                    write_json(retrieval_path, retrieval)
                checked = verify_publications(
                    retrieval["papers"], root, resolve_pdfs=False
                )
                merged = deduplicate_papers(
                    [
                        p
                        for p in checked
                        if p.get("conference_acceptance_status") != "rejected"
                    ]
                )
                write_json(folder / "merged.json", merged)
                if retrieve_only:
                    manifest.update(
                        status="retrieved",
                        retrieved_records=len(retrieval["papers"]),
                        unique_papers=len(merged["papers"]),
                        coverage=retrieval["coverage"],
                    )
                    write_json(folder / "manifest.json", manifest)
                    return manifest
                pool = build_review_pool(merged["papers"], plan["profile"], root)
                write_json(pool_path, pool)
            manifest.update(
                retrieved_records=len(retrieval["papers"]),
                unique_papers=len(merged["papers"]),
                coverage={**retrieval["coverage"], "budget": pool["coverage"]},
                tasks=retrieval["tasks"],
            )
            profile = plan["profile"]
            topic = {
                "tag": profile["tag"],
                "description": profile.get("description") or "",
                "queries": profile.get("queries") or [],
                "keywords": profile.get("review_keywords") or [],
            }
            reviewed = review_candidates(
                pool["papers"], topic, root, max_new_reviews=max_new_reviews
            )
            write_json(folder / "reviewed.json", reviewed)
            manifest.update(
                remaining=reviewed["remaining"],
                new_reviews=reviewed["new_reviews"],
                cached_reviews=reviewed["cached_reviews"],
                reviewed_count=len(reviewed["papers"]),
                last_action="run",
                status="needs_resume" if reviewed["remaining"] else "selection_ready",
            )
            if not reviewed["remaining"]:
                selected = select_final_papers(reviewed["papers"])
                for paper in selected:
                    paper.update(research_run_id=run_id, research_mode=mode)
                write_json(
                    folder / "selected.json",
                    {
                        "papers": selected,
                        "selection_complete": True,
                        "order": "score_desc",
                        "reviewed_count": len(reviewed["papers"]),
                        "result_limit": 100,
                    },
                )
                manifest["selected_count"] = len(selected)
        except Exception as error:
            manifest.update(status="failed", error_type=type(error).__name__)
            write_json(folder / "manifest.json", manifest)
            raise
    else:
        raise ValueError("不支持的任务操作，不会自动扩大评审预算")
    write_json(folder / "manifest.json", manifest)
    if publish:
        from starter_pack_publish import publish_pack

        code_root = Path(__file__).resolve().parents[1]
        import os

        if root == code_root and os.getenv("GITHUB_REPOSITORY", "").lower() in (
            "",
            "ziwenhahaha/daily-paper-reader",
        ):
            raise ValueError("主仓库不能写个性化研究结果，请使用独立root或Fork")
        published = root / "docs/starter-pack" / run_id
        selection_path = folder / "selected.json"
        if selection_path.exists():
            write_json(
                published / "task-state.json",
                {
                    "manifest": manifest,
                    "selection": json.loads(selection_path.read_text(encoding="utf-8")),
                },
            )
        result = publish_pack(root, manifest, 100)
        manifest.update(status=result["status"], result=result)
        write_json(folder / "manifest.json", manifest)
        if selection_path.exists():
            write_json(
                published / "task-state.json",
                {
                    "manifest": manifest,
                    "selection": json.loads(selection_path.read_text(encoding="utf-8")),
                },
            )
    return manifest


def main(argv=None):
    from local_env import load_local_env
    import yaml

    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--profile-tag", default="")
    parser.add_argument("--mode", choices=sorted(MODES), default="starter")
    parser.add_argument(
        "--as-of", default=datetime.now(timezone.utc).date().isoformat()
    )
    parser.add_argument("--profile-snapshot", default="")
    parser.add_argument("--conferences", default="")
    parser.add_argument("--content-batch", type=int, default=10)
    parser.add_argument("--max-new-reviews", type=int, default=300)
    parser.add_argument("--action", choices=["run", "continue-content"], default="run")
    parser.add_argument("--run-id")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--retrieve-only", action="store_true")
    args = parser.parse_args(argv)
    if len(args.profile_snapshot) > 32768:
        parser.error("需求快照过大")
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    result = run_research(
        config,
        args.profile_tag,
        args.mode,
        args.as_of,
        args.root,
        profile_snapshot=(
            json.loads(args.profile_snapshot) if args.profile_snapshot else None
        ),
        conferences=[c.strip() for c in args.conferences.split(",") if c.strip()]
        or None,
        content_batch=args.content_batch,
        action=args.action,
        run_id=args.run_id,
        publish=args.publish,
        retrieve_only=args.retrieve_only,
        max_new_reviews=args.max_new_reviews,
    )
    print(
        json.dumps(
            {
                key: result.get(key)
                for key in (
                    "run_id",
                    "mode",
                    "status",
                    "selected_count",
                    "remaining",
                    "new_reviews",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
