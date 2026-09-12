"""入门包只读检索编排：固定窗口、逐查询检查点及明确的覆盖边界。"""

from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import threading
from itertools import product

from long_range_review import collect_window, fingerprint, keyword_aliases, write_json
from paper_dates import resolve_publication_date, publication_window_status
from source_config import get_source_backend
from subscription_plan import build_pipeline_inputs
from supabase_source import match_papers_by_bm25, match_papers_by_embedding

VERSION = "starter-retrieval-v1"
MODEL = "BAAI/bge-small-en-v1.5"


def _boolean(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() not in {"false", "0", "no", "off", ""}


def build_tasks(
    config,
    profile_tag,
    as_of,
    conferences=None,
    stats_snapshot=None,
    *,
    arxiv_days=365,
    bounded=False,
):
    """as_of 为排他结束日；滚动 24 个月按日历计算，不按 730 天。"""
    from conference_retrieval import CONFERENCE_DEFAULTS

    end = date.fromisoformat(str(as_of))
    if arxiv_days not in (90, 365):
        raise ValueError("专题窗口仅支持90天或365天")
    start = end - timedelta(days=arxiv_days)
    conf_start = end.replace(
        year=end.year - 2,
        day=min(end.day, calendar.monthrange(end.year - 2, end.month)[1]),
    )
    profiles = (config.get("subscriptions") or {}).get("intent_profiles") or []
    selected = [
        p for p in profiles if isinstance(p, dict) and p.get("tag") == profile_tag
    ]
    if (
        len(selected) != 1
        or not _boolean(selected[0].get("enabled"), True)
        or _boolean(selected[0].get("paused"))
    ):
        raise ValueError("请选择唯一、已启用且未暂停的研究方向")
    scoped = copy.deepcopy(config)
    scoped["subscriptions"]["intent_profiles"] = copy.deepcopy(selected)
    for flag in ("scope", "conference_only", "temporary"):
        scoped["subscriptions"]["intent_profiles"][0].pop(flag, None)
    inputs = build_pipeline_inputs(scoped)
    keywords = [
        copy.deepcopy(q) for q in inputs["bm25_queries"] if q.get("tag") == profile_tag
    ]
    vectors = [
        copy.deepcopy(q)
        for q in inputs["embedding_queries"]
        if q.get("tag") == profile_tag
    ]
    if not keywords and not vectors:
        raise ValueError("所选方向没有启用的合法查询")
    review_keywords = [q["query_text"] for q in keywords]
    groups = selected[0].get("constraint_groups") or []
    if groups:
        if (
            not isinstance(groups, list)
            or len(groups) > 3
            or any(
                not isinstance(g, list)
                or not 1 <= len(g) <= 8
                or any(
                    not isinstance(t, str) or not t.strip() or len(t) > 300 for t in g
                )
                for g in groups
            )
        ):
            raise ValueError("检索约束组无效")
        combinations = list(product(*groups))
        if len(combinations) > 32:
            raise ValueError("检索约束组合超过32种，请减少同义词")
        keywords = [
            {
                "query_text": " ".join(parts),
                "tag": profile_tag,
                "paper_tag": "keyword:" + profile_tag,
            }
            for parts in combinations
        ]
        review_keywords = [q["query_text"] for q in keywords]
        context = " AND ".join("(" + " OR ".join(g) + ")" for g in groups)
        for query in vectors:
            query["query_text"] = context + ": " + query["query_text"]
    existing = {q["query_text"].casefold() for q in keywords}
    for alias in (
        [] if groups else keyword_aliases(profile_tag) + keyword_aliases(selected[0])
    ):
        if alias.casefold() not in existing:
            keywords.append(
                {
                    "query_text": alias,
                    "tag": profile_tag,
                    "paper_tag": "keyword:" + profile_tag,
                }
            )
            existing.add(alias.casefold())
    sources = sorted(
        dict.fromkeys(
            str(c).strip().lower()
            for c in (CONFERENCE_DEFAULTS if conferences is None else conferences)
        )
    )
    if any(c not in CONFERENCE_DEFAULTS for c in sources):
        raise ValueError("会议列表包含不支持的会议")
    if stats_snapshot is None:
        try:
            stats_snapshot = json.loads(
                (
                    Path(__file__).resolve().parents[1] / "app/conference-stats.json"
                ).read_text()
            )
        except (OSError, ValueError):
            stats_snapshot = {}
    inventory = {
        (str(i.get("conference_key")).lower(), int(i["year"])): i
        for i in stats_snapshot.get("items", [])
        if isinstance(i, dict) and str(i.get("year", "")).isdigit()
    }
    tasks = []
    for lane, queries in [("bm25", keywords), ("embedding", vectors)]:
        for query in queries:
            cursor = start
            while cursor < end:
                stop = end if lane == "bm25" else min(cursor + timedelta(days=30), end)
                tasks.append(
                    {
                        "source": "arxiv",
                        "lane": lane,
                        "query": query,
                        "start": cursor.isoformat(),
                        "end_exclusive": stop.isoformat(),
                        "limit": (
                            (100 if lane == "bm25" else 50)
                            if bounded
                            else (500 if lane == "bm25" else 100)
                        ),
                        **({"bounded": True} if bounded else {}),
                    }
                )
                cursor = stop
    missing = []
    unknown = []
    disabled = []
    for conference in sources:
        configured = (config.get("source_backends") or {}).get(conference) or {}
        if "enabled" in configured and not _boolean(configured["enabled"]):
            disabled.append(conference)
            continue
        for year in range(conf_start.year, (end - timedelta(days=1)).year + 1):
            entry = inventory.get((conference, year))
            pair = {"conference": conference, "year": year}
            if entry and entry.get("stored_total_count") == 0:
                missing.append(pair)
                continue
            if not entry:
                unknown.append(pair)
            for lane, queries in [("bm25", keywords), ("embedding", vectors)]:
                for query in queries:
                    tasks.append(
                        {
                            "source": conference,
                            "year": year,
                            "lane": lane,
                            "query": query,
                            "start": conf_start.isoformat(),
                            "end_exclusive": end.isoformat(),
                            "limit": 50,
                        }
                    )
    # 不把 updated_at 或密钥放进检查点标识。
    profile = {
        k: copy.deepcopy(selected[0].get(k))
        for k in ("tag", "description", "keywords", "intent_queries")
    }
    profile["queries"] = [q["query_text"] for q in vectors]
    profile["review_keywords"] = review_keywords
    if groups:
        profile["constraint_groups"] = copy.deepcopy(groups)
    if selected[0].get("refinement"):
        profile["refinement"] = selected[0]["refinement"]
    plan = {
        "version": VERSION,
        "profile": profile,
        "as_of": end.isoformat(),
        "arxiv_start": start.isoformat(),
        "conference_start": conf_start.isoformat(),
        "conferences": sources,
        "tasks": tasks,
        "missing_inventory": missing,
        "unknown_inventory": unknown,
        "disabled_sources": disabled,
        **({"bounded": True} if bounded else {}),
    }
    plan["windows"] = {
        "arxiv": {"start": start.isoformat(), "end_exclusive": end.isoformat()},
        "conference": {
            "start": conf_start.isoformat(),
            "end_exclusive": end.isoformat(),
        },
    }
    plan["run_id"] = (
        end.strftime("%Y%m%d")
        + "-"
        + fingerprint(
            {
                "version": VERSION,
                "profile": profile,
                "windows": plan["windows"],
                "conferences": sources,
                **({"bounded": True} if bounded else {}),
            }
        )[:12]
    )
    return plan


def _validate_rows(rows, task):
    if not isinstance(rows, list):
        raise RuntimeError("RPC 返回非列表记录")
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            raise RuntimeError("RPC 返回缺少论文 ID 的记录")
        if task["source"] == "arxiv":
            continue
        source_year = re.search(r"(?<!\d)(20\d{2})(?!\d)", str(row.get("source") or ""))
        actual_year = str(
            row.get("conference_year")
            or row.get("year")
            or (source_year.group(1) if source_year else "")
        )
        source_conf = re.sub(
            r"[^a-z0-9]",
            "",
            re.split(r"[-_ ]20\d{2}", str(row.get("source") or "").lower())[0],
        )
        actual_conf = re.sub(
            r"[^a-z0-9]", "", str(row.get("conference_key") or source_conf).lower()
        )
        if actual_year != str(task["year"]) or actual_conf != re.sub(
            r"[^a-z0-9]", "", task["source"]
        ):
            raise RuntimeError("会议 RPC 返回不符合指定会议/年份的记录")


def _read_cache(path, key):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            value.get("key") == key
            and value.get("status") == "done"
            and isinstance(value.get("rows"), list)
        ):
            return value["rows"]
    except (OSError, ValueError, AttributeError):
        pass
    return None


def _backend_identity(backend):
    return {
        k: backend.get(k)
        for k in ("url", "schema", "papers_table", "bm25_rpc", "vector_rpc_exact")
    }


def _vector(query, cache):
    """只使用云端模型；缓存嵌入与检索检查点分离，续跑不重复编码。"""
    import numpy as np
    from conference_retrieval import prepare_embedding_queries

    key = fingerprint(
        {
            "model": MODEL,
            "query": query["query_text"],
            "endpoint": os.getenv("DPR_EMBED_API_URL", ""),
        }
    )
    path = cache / "embeddings" / (key + ".json")
    rows = _read_cache(path, key)
    if rows is None:
        os.environ["DPR_MODELS_REMOTE_ONLY"] = "1"
        item = copy.deepcopy(query)
        prepare_embedding_queries(
            [item], model_name=MODEL, device="cpu", batch_size=1, max_length=512
        )
        rows = np.asarray(item["query_embedding"], dtype=float).tolist()
    vector = np.asarray(rows, dtype=float)
    if (
        vector.shape != (384,)
        or not np.isfinite(vector).all()
        or np.linalg.norm(vector) < 1e-8
    ):
        raise RuntimeError("云端 embedding 必须返回有效的 384 维向量")
    write_json(path, {"key": key, "status": "done", "rows": rows})
    return rows


def run_retrieval(plan, config, root):
    """失败直接抛错；成功分片仍可续用，不将不完整结果当成功发布。"""
    from conference_retrieval import resolve_unified_conference_backend

    cache = Path(root) / ".local-runs/starter-pack-cache/retrieval"
    papers = {}
    statuses = []
    excluded = uncertain = excluded_nonaccepted = 0
    embedding_locks = {}
    lock_guard = threading.Lock()

    def retrieve_task(task):
        conference = task["source"] != "arxiv"
        backend = (
            resolve_unified_conference_backend(config)
            if conference
            else get_source_backend(config, "arxiv")
        )
        if (
            backend.get("enabled") is False
            or not backend.get("url")
            or not backend.get("anon_key")
        ):
            raise RuntimeError(f"{task['source']} 缺少可用 Supabase 后端")
        # 后端地址与实际查询一起入hash，防止切换数据库后复用其他库结果。
        identity = {
            "version": VERSION,
            "task": task,
            "profile": plan["profile"],
            "backend": _backend_identity(backend),
            "model": MODEL,
        }
        # 默认服务保持历史key；自定义端点必须使任务级召回检查点失效。
        endpoint = (
            (os.getenv("DPR_EMBED_API_URL") or "https://zwwen.online/embed")
            .strip()
            .rstrip("/")
        )
        if task["lane"] == "embedding" and endpoint != "https://zwwen.online/embed":
            identity["embedding_endpoint"] = endpoint
        key = fingerprint(identity)
        path = cache / "tasks" / (key + ".json")
        rows = _read_cache(path, key)
        # 已有全年缓存是本次有界查询的超集，按同一查询分数取子集，不重新联网。
        if rows is None and task.get("bounded"):
            old_task = {k: v for k, v in task.items() if k != "bounded"}
            old_task["limit"] = 500 if task["lane"] == "bm25" else 100
            old_key = fingerprint({**identity, "task": old_task})
            previous = _read_cache(cache / "tasks" / (old_key + ".json"), old_key)
            if previous is not None:
                score_key = "score" if task["lane"] == "bm25" else "similarity"
                rows = sorted(
                    previous,
                    key=lambda p: (-float(p.get(score_key) or 0), str(p.get("id"))),
                )[: task["limit"]]
                write_json(path, {"key": key, "status": "done", "rows": rows})
        restored = rows is not None
        if rows is None:
            vector = None
            if task["lane"] == "embedding":
                embedding_key = task["query"]["query_text"]
                with lock_guard:
                    embedding_lock = embedding_locks.setdefault(
                        embedding_key, threading.Lock()
                    )
                with embedding_lock:
                    vector = _vector(task["query"], cache)

            def call(a=None, b=None, limit=None):
                slice_key = fingerprint(
                    {
                        "task": key,
                        "start": a.isoformat() if a else None,
                        "end": b.isoformat() if b else None,
                        "limit": limit,
                    }
                )
                slice_path = cache / "slices" / (slice_key + ".json")
                cached = _read_cache(slice_path, slice_key)
                if cached is not None:
                    return cached, "rpc 查询成功 (checkpoint)"
                kwargs = {
                    "url": backend["url"],
                    "api_key": backend["anon_key"],
                    "schema": backend.get("schema") or "public",
                    "match_count": limit or task["limit"],
                }
                if conference:
                    kwargs["extra_payload"] = {
                        "filter_pairs": [f"{task['source']}:{task['year']}"]
                    }
                else:
                    kwargs.update(start_dt=a, end_dt=b)
                if task["lane"] == "bm25":
                    kwargs.update(
                        rpc_name=backend.get("bm25_rpc") or "match_arxiv_papers_bm25",
                        query_text=task["query"]["query_text"],
                    )
                    found, message = match_papers_by_bm25(**kwargs)
                else:
                    kwargs.update(
                        rpc_name=backend.get("vector_rpc_exact")
                        or backend.get("vector_rpc")
                        or "match_arxiv_papers_exact",
                        query_embedding=vector,
                    )
                    found, message = match_papers_by_embedding(**kwargs)
                if message.startswith("rpc 查询成功"):
                    _validate_rows(found, task)
                    write_json(
                        slice_path, {"key": slice_key, "status": "done", "rows": found}
                    )
                return found, message

            if conference:
                rows, message = call(limit=task["limit"])
                if not message.startswith("rpc 查询成功"):
                    raise RuntimeError(
                        f"会议召回失败 {task['source']} {task['year']}: {message}"
                    )
            else:
                a = datetime.fromisoformat(task["start"]).replace(tzinfo=timezone.utc)
                b = datetime.fromisoformat(task["end_exclusive"]).replace(
                    tzinfo=timezone.utc
                )
                rows = collect_window(
                    call,
                    a,
                    b,
                    exhaustive=task["lane"] == "bm25" and not task.get("bounded"),
                    limit=task["limit"],
                )
                if task.get("bounded"):
                    score_key = "score" if task["lane"] == "bm25" else "similarity"
                    rows = sorted(
                        rows,
                        key=lambda p: (-float(p.get(score_key) or 0), str(p.get("id"))),
                    )[: task["limit"]]
            write_json(path, {"key": key, "status": "done", "rows": rows})
        _validate_rows(rows, task)
        return rows, {
            "key": key,
            "source": task["source"],
            "year": task.get("year"),
            "lane": task["lane"],
            "query_text": task["query"]["query_text"],
            "start": task["start"],
            "end_exclusive": task["end_exclusive"],
            "status": "done",
            "restored": restored,
            "raw_count": len(rows),
            "bounded": conference or task["lane"] == "embedding",
        }

    # 并发只负责读取与独立checkpoint；归并仍按原计划顺序，结果不受完成先后影响。
    unique_tasks = {fingerprint(task): task for task in plan["tasks"]}
    completed = {}
    workers = max(1, min(4, int(os.getenv("DPR_STARTER_RETRIEVAL_WORKERS", "4"))))
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="starter-recall"
    ) as pool:
        futures = {
            pool.submit(retrieve_task, task): task_key
            for task_key, task in unique_tasks.items()
        }
        try:
            for future in as_completed(futures):
                task_key = futures[future]
                completed[task_key] = future.result()
                status = completed[task_key][1]
                print(
                    f"[入门包召回] {len(completed)}/{len(unique_tasks)} {status['source']} {status.get('year') or ''} {status['lane']} {'缓存' if status['restored'] else '完成'} {status['raw_count']} 篇",
                    flush=True,
                )
        except Exception:
            for future in futures:
                future.cancel()
            raise
    for task in plan["tasks"]:
        rows, status_entry = completed[fingerprint(task)]
        statuses.append(status_entry)
        conference = task["source"] != "arxiv"
        key = status_entry["key"]
        for rank, raw in enumerate(rows, 1):
            row = dict(raw)
            if not row.get("id"):
                raise RuntimeError("RPC 返回缺少论文 ID 的记录")
            if conference:
                decision_text = " ".join(
                    str(row.get(field) or "")
                    for field in ("source", "decision", "status")
                )
                if re.search(
                    r"\b(?:reject(?:ed|ion)?|withdraw(?:n|al)?)\b", decision_text, re.I
                ):
                    excluded_nonaccepted += 1
                    continue
                row.update(conference=task["source"], conference_year=task["year"])
            else:
                row["source"] = "arxiv"
            row.update(
                resolve_publication_date(
                    row,
                    conference=task["source"] if conference else "",
                    year=task.get("year"),
                )
            )
            status = publication_window_status(
                row, task["start"], task["end_exclusive"]
            )
            row["publication_window_status"] = status
            if status == "excluded":
                excluded += 1
                continue
            if status == "uncertain":
                uncertain += 1
            row["retrieval_source"] = task["source"]
            evidence = {
                "lane": task["lane"],
                "query_text": task["query"]["query_text"],
                "task_key": key,
                "rank": rank,
            }
            paper_key = (task["source"], str(row["id"]))
            if paper_key not in papers:
                row["retrieval_evidence"] = []
                papers[paper_key] = row
            papers[paper_key]["retrieval_evidence"].append(evidence)
    return {
        "papers": list(papers.values()),
        "tasks": statuses,
        "coverage": {
            "all_tasks_completed": True,
            "guarantees_all_relevant_papers": False,
            "arxiv_keyword": (
                "top100_per_query"
                if plan.get("bounded")
                else "exhaustive_within_configured_queries_and_database"
            ),
            "arxiv_vector": (
                "top50_per_query_per_30_days"
                if plan.get("bounded")
                else "top100_per_query_per_30_days"
            ),
            "conference_keyword": "top50_per_query_per_conference_year",
            "conference_vector": "top50_per_query_per_conference_year",
            "missing_inventory": plan["missing_inventory"],
            "unknown_inventory": plan["unknown_inventory"],
            "disabled_sources": plan.get("disabled_sources", []),
            "excluded_date_hits": excluded,
            "excluded_nonaccepted": excluded_nonaccepted,
            "uncertain_date_hits": uncertain,
            "note": "数据库及所选会议范围内的查询召回；关键词不等于全部相关论文，语义和会议候选有 Top-K 上限。",
        },
    }
