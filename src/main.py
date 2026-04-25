#!/usr/bin/env python
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from source_config import get_source_backend, load_config_with_source_migration
except Exception:  # pragma: no cover - 兼容 package 导入路径
    from src.source_config import get_source_backend, load_config_with_source_migration

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


SRC_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SRC_DIR, ".."))
CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")
LONG_RANGE_DAYS_THRESHOLD = 10
MAIN_DEFAULT_DAYS = 9
SKIMS_FETCH_DAYS_THRESHOLD = 11
BLT_PROVIDER_BASE_KEYWORDS = ("bltcy.ai", "gptbest.vip", "blt", "gptbest")


def run_step(label: str, args: list[str], env: dict[str, str] | None = None) -> None:
    print(f"[INFO] {label}: {' '.join(args)}", flush=True)
    subprocess.run(args, check=True, env=env)


def _load_full_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    return load_config_with_source_migration(CONFIG_FILE, write_back=False)


def load_arxiv_paper_setting() -> dict:
    data = _load_full_config()
    setting = data.get("arxiv_paper_setting") or {}
    return setting if isinstance(setting, dict) else {}


def should_skip_fetch(config: dict | None = None) -> bool:
    """
    当 Supabase 已完全接管检索（BM25 + 向量 RPC 均已启用）时，
    Step 1（全量数据拉取到本地）可以跳过——后续 Step 2.1 / 2.2
    会直接走数据库端召回，不再依赖本地原始文件。
    """
    if config is None:
        config = _load_full_config()
    sb = get_source_backend(config, "arxiv")
    if not sb.get("enabled", False):
        return False
    paper_setting = config.get("arxiv_paper_setting") or {}
    if not paper_setting.get("prefer_supabase_read", False):
        return False
    if not sb.get("use_bm25_rpc", False):
        return False
    if not sb.get("use_vector_rpc", False):
        return False
    if not sb.get("url") or not sb.get("anon_key"):
        return False
    return True


def build_sidebar_date_label(days: int) -> str:
    safe_days = max(int(days), 1)
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=safe_days - 1)
    return f"{start_date:%Y-%m-%d} ~ {end_date:%Y-%m-%d}"


def build_run_date_token(days: int) -> str:
    safe_days = max(int(days), 1)
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=safe_days - 1)
    return f"{start_date:%Y%m%d}-{end_date:%Y%m%d}"


def resolve_run_date_token(fetch_days: int | None) -> str:
    """
    统一运行日期标识：
    - 大窗口（>=阈值）使用区间 token：YYYYMMDD-YYYYMMDD
    - 其它情况使用单日 token：YYYYMMDD
    """
    if fetch_days is not None:
        if fetch_days >= LONG_RANGE_DAYS_THRESHOLD:
            return build_run_date_token(fetch_days)
        return datetime.now(timezone.utc).strftime("%Y%m%d")

    setting = load_arxiv_paper_setting()
    try:
        days_window = int(setting.get("days_window") or MAIN_DEFAULT_DAYS)
    except Exception:
        days_window = MAIN_DEFAULT_DAYS
    if days_window >= LONG_RANGE_DAYS_THRESHOLD:
        return build_run_date_token(days_window)
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def resolve_sidebar_date_label(fetch_days: int | None) -> str | None:
    # 1) 显式传 --fetch-days 时，仅在大窗口模式下显示日期范围。
    if fetch_days is not None:
        if fetch_days >= LONG_RANGE_DAYS_THRESHOLD:
            return build_sidebar_date_label(fetch_days)
        return None

    # 2) 未显式传入时，按 config 的 days_window 判断：
    #    仅在“大时间跨度”模式（默认阈值 >=10 天）自动显示区间标题。
    setting = load_arxiv_paper_setting()
    try:
        days_window = int(setting.get("days_window") or MAIN_DEFAULT_DAYS)
    except Exception:
        days_window = MAIN_DEFAULT_DAYS
    if days_window >= LONG_RANGE_DAYS_THRESHOLD:
        return build_sidebar_date_label(days_window)
    return None


def normalize_arxiv_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text.startswith("arxiv:"):
        text = text.split(":", 1)[1].strip()
    if text.startswith("http://") or text.startswith("https://"):
        text = text.split("?", 1)[0].split("#", 1)[0]
        text = text.rstrip("/")
        if "/abs/" in text:
            text = text.rsplit("/abs/", 1)[-1]
        elif "/pdf/" in text:
            text = text.rsplit("/pdf/", 1)[-1]
        else:
            text = text.rsplit("/", 1)[-1]
    if text.endswith(".pdf"):
        text = text[: -len(".pdf")]
    text = text.strip()
    matched = re.match(r"^(\d{4}\.\d{4,5})(?:v\d+)?$", text)
    if matched:
        return matched.group(1)
    return text


def parse_trace_ids(cli_values: list[str] | None) -> list[str]:
    raw_parts: list[str] = []
    for value in cli_values or []:
        raw_parts.extend(re.split(r"[,\s]+", str(value or "").strip()))
    env_value = str(os.getenv("DPR_TRACE_ARXIV_IDS") or "").strip()
    if env_value:
        raw_parts.extend(re.split(r"[,\s]+", env_value))

    seen: set[str] = set()
    result: list[str] = []
    for item in raw_parts:
        token = normalize_arxiv_id(item)
        if not token or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def load_json_safe(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[TRACE] 读取失败: {path} | {exc}", flush=True)
        return None


def save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_env_text(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _looks_like_blt_base(base_url: str) -> bool:
    lowered = str(base_url or "").strip().lower()
    return any(keyword in lowered for keyword in BLT_PROVIDER_BASE_KEYWORDS)


def should_skip_rerank() -> tuple[bool, str]:
    primary_base = _read_env_text(
        "LLM_PRIMARY_BASE_URL",
        "BLT_PRIMARY_BASE_URL",
        "GPTBEST_BASE_URL",
        "BLT_API_BASE",
    )
    if not primary_base:
        return False, ""
    if _looks_like_blt_base(primary_base):
        return False, primary_base
    return True, primary_base


def score_to_stars(score: float) -> int:
    if score >= 0.9:
        return 5
    if score >= 0.5:
        return 4
    if score >= 0.1:
        return 3
    if score >= 0.01:
        return 2
    return 1


def build_ranked_from_sim_scores(query_obj: dict[str, Any]) -> list[dict[str, Any]]:
    sim_scores = query_obj.get("sim_scores")
    if not isinstance(sim_scores, dict) or not sim_scores:
        return []

    items: list[tuple[str, float | None, int | None]] = []
    for pid, meta in sim_scores.items():
        score = None
        rank = None
        if isinstance(meta, dict):
            raw_score = meta.get("score")
            raw_rank = meta.get("rank")
            if isinstance(raw_score, (int, float)):
                score = float(raw_score)
            if isinstance(raw_rank, (int, float)):
                rank = int(raw_rank)
        elif isinstance(meta, (int, float)):
            score = float(meta)
        items.append((str(pid), score, rank))

    items.sort(
        key=lambda item: (
            item[2] is None,
            item[2] if item[2] is not None else 10**9,
            -(item[1] if item[1] is not None else 0.0),
            item[0],
        )
    )
    if not items:
        return []

    numeric_scores = [item[1] for item in items if item[1] is not None]
    min_score = min(numeric_scores) if numeric_scores else None
    max_score = max(numeric_scores) if numeric_scores else None
    total = len(items)
    ranked: list[dict[str, Any]] = []
    for idx, (pid, score, _rank) in enumerate(items, start=1):
        if (
            score is not None
            and min_score is not None
            and max_score is not None
            and max_score > min_score
        ):
            normalized = (score - min_score) / (max_score - min_score)
        elif total == 1:
            normalized = 1.0
        else:
            normalized = (total - idx) / (total - 1)
        ranked.append(
            {
                "paper_id": pid,
                "score": float(normalized),
                "star_rating": score_to_stars(float(normalized)),
            }
        )
    return ranked


def prepare_rerank_fallback(input_path: str, output_path: str) -> bool:
    if not os.path.exists(input_path):
        print(f"[WARN] Step 3 fallback 输入不存在，无法生成兜底 rerank 文件: {input_path}", flush=True)
        return False

    data = load_json_safe(input_path)
    if not isinstance(data, dict):
        print(f"[WARN] Step 3 fallback 输入格式非法，无法生成兜底 rerank 文件: {input_path}", flush=True)
        return False

    queries = data.get("queries")
    if isinstance(queries, list):
        for query in queries:
            if isinstance(query, dict):
                query["ranked"] = build_ranked_from_sim_scores(query)

    data["reranked_at"] = datetime.now(timezone.utc).isoformat()
    save_json(output_path, data)
    print(f"[INFO] 已生成 Step 3 fallback 结果: {output_path}", flush=True)
    return True


def resolve_summary_step_env() -> dict[str, str]:
    env = os.environ.copy()
    summary_api_key = _read_env_text("SUMMARY_API_KEY", "BLT_SUMMARY_API_KEY")
    summary_base_url = _read_env_text("SUMMARY_BASE_URL", "BLT_SUMMARY_BASE_URL")
    summary_model = _read_env_text("SUMMARY_MODEL", "BLT_SUMMARY_MODEL")

    if summary_api_key:
        env["BLT_API_KEY"] = summary_api_key
    if summary_base_url:
        env["LLM_PRIMARY_BASE_URL"] = summary_base_url
        env["BLT_PRIMARY_BASE_URL"] = summary_base_url
        env["BLT_API_BASE"] = summary_base_url
    if summary_model:
        env["BLT_SUMMARY_MODEL"] = summary_model
    return env


def build_paper_index(papers: Any, trace_set: set[str]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(papers, list):
        return index
    for item in papers:
        if not isinstance(item, dict):
            continue
        pid = normalize_arxiv_id(item.get("id") or item.get("paper_id") or item.get("link"))
        if not pid or pid not in trace_set or pid in index:
            continue
        index[pid] = item
    return index


def collect_query_hits(queries: Any, trace_set: set[str]) -> dict[str, list[dict[str, Any]]]:
    hits: dict[str, list[dict[str, Any]]] = {pid: [] for pid in trace_set}
    if not isinstance(queries, list):
        return hits

    for q in queries:
        if not isinstance(q, dict):
            continue
        query_tag = str(q.get("paper_tag") or q.get("tag") or q.get("query_text") or "").strip()

        sim_scores = q.get("sim_scores")
        if isinstance(sim_scores, dict):
            for raw_pid, meta in sim_scores.items():
                pid = normalize_arxiv_id(raw_pid)
                if pid not in trace_set:
                    continue
                score = None
                rank = None
                if isinstance(meta, dict):
                    score = meta.get("score")
                    rank = meta.get("rank")
                elif isinstance(meta, (int, float)):
                    score = float(meta)
                hits[pid].append(
                    {
                        "source": "sim_scores",
                        "query": query_tag,
                        "score": score,
                        "rank": rank,
                    }
                )

        ranked = q.get("ranked")
        if isinstance(ranked, list):
            for idx, item in enumerate(ranked, start=1):
                if not isinstance(item, dict):
                    continue
                pid = normalize_arxiv_id(item.get("paper_id") or item.get("id"))
                if pid not in trace_set:
                    continue
                hits[pid].append(
                    {
                        "source": "ranked",
                        "query": query_tag,
                        "score": item.get("score"),
                        "rank": item.get("rank") or idx,
                        "star_rating": item.get("star_rating"),
                    }
                )
    return hits


def print_trace_retrieval(stage: str, path: str, trace_ids: list[str]) -> None:
    if not os.path.exists(path):
        print(f"[TRACE][{stage}] 文件不存在: {path}", flush=True)
        return
    data = load_json_safe(path)
    if data is None:
        return

    trace_set = set(trace_ids)
    if isinstance(data, list):
        paper_index = build_paper_index(data, trace_set)
        query_hits = {pid: [] for pid in trace_set}
    elif isinstance(data, dict):
        paper_index = build_paper_index(data.get("papers"), trace_set)
        query_hits = collect_query_hits(data.get("queries"), trace_set)
    else:
        print(f"[TRACE][{stage}] 非法 JSON 结构: {type(data)}", flush=True)
        return

    print(f"[TRACE][{stage}] path={path}", flush=True)
    for pid in trace_ids:
        paper = paper_index.get(pid)
        hits = query_hits.get(pid) or []
        best_rank = None
        best_score = None
        for hit in hits:
            rank = hit.get("rank")
            score = hit.get("score")
            if isinstance(rank, (int, float)):
                best_rank = int(rank) if best_rank is None else min(best_rank, int(rank))
            if isinstance(score, (int, float)):
                best_score = float(score) if best_score is None else max(best_score, float(score))
        title = ""
        published = ""
        if isinstance(paper, dict):
            title = str(paper.get("title") or "").strip()
            published = str(paper.get("published") or "").strip()
        title_suffix = f" | title={title}" if title else ""
        pub_suffix = f" | published={published}" if published else ""
        print(
            f"[TRACE][{stage}] id={pid} | in_papers={'Y' if paper else 'N'} | query_hits={len(hits)}"
            f" | best_rank={best_rank if best_rank is not None else '-'}"
            f" | best_score={f'{best_score:.6f}' if best_score is not None else '-'}"
            f"{pub_suffix}{title_suffix}",
            flush=True,
        )


def print_trace_llm(stage: str, path: str, trace_ids: list[str]) -> None:
    if not os.path.exists(path):
        print(f"[TRACE][{stage}] 文件不存在: {path}", flush=True)
        return
    data = load_json_safe(path)
    if not isinstance(data, dict):
        print(f"[TRACE][{stage}] 非法 JSON 结构: {type(data)}", flush=True)
        return

    trace_set = set(trace_ids)
    paper_index = build_paper_index(data.get("papers"), trace_set)
    query_hits = collect_query_hits(data.get("queries"), trace_set)
    llm_ranked = data.get("llm_ranked")
    llm_index: dict[str, dict[str, Any]] = {}
    if isinstance(llm_ranked, list):
        for idx, item in enumerate(llm_ranked, start=1):
            if not isinstance(item, dict):
                continue
            pid = normalize_arxiv_id(item.get("paper_id") or item.get("id"))
            if pid not in trace_set or pid in llm_index:
                continue
            llm_index[pid] = {"rank": idx, "score": item.get("score"), "item": item}

    print(f"[TRACE][{stage}] path={path}", flush=True)
    for pid in trace_ids:
        paper = paper_index.get(pid)
        llm_item = llm_index.get(pid)
        hits = query_hits.get(pid) or []
        llm_rank = llm_item.get("rank") if llm_item else None
        llm_score = llm_item.get("score") if llm_item else None
        print(
            f"[TRACE][{stage}] id={pid} | in_papers={'Y' if paper else 'N'} | query_hits={len(hits)}"
            f" | in_llm_ranked={'Y' if llm_item else 'N'}"
            f" | llm_rank={llm_rank if llm_rank is not None else '-'}"
            f" | llm_score={f'{float(llm_score):.6f}' if isinstance(llm_score, (int, float)) else '-'}",
            flush=True,
        )


def print_trace_recommend(stage: str, path: str, trace_ids: list[str]) -> None:
    if not os.path.exists(path):
        print(f"[TRACE][{stage}] 文件不存在: {path}", flush=True)
        return
    data = load_json_safe(path)
    if not isinstance(data, dict):
        print(f"[TRACE][{stage}] 非法 JSON 结构: {type(data)}", flush=True)
        return

    deep = data.get("deep_dive")
    quick = data.get("quick_skim")
    deep_index: dict[str, dict[str, Any]] = {}
    quick_index: dict[str, dict[str, Any]] = {}
    if isinstance(deep, list):
        for idx, item in enumerate(deep, start=1):
            if not isinstance(item, dict):
                continue
            pid = normalize_arxiv_id(item.get("id") or item.get("paper_id"))
            if pid and pid not in deep_index:
                deep_index[pid] = {"rank": idx, "item": item}
    if isinstance(quick, list):
        for idx, item in enumerate(quick, start=1):
            if not isinstance(item, dict):
                continue
            pid = normalize_arxiv_id(item.get("id") or item.get("paper_id"))
            if pid and pid not in quick_index:
                quick_index[pid] = {"rank": idx, "item": item}

    print(f"[TRACE][{stage}] path={path}", flush=True)
    for pid in trace_ids:
        deep_item = deep_index.get(pid)
        quick_item = quick_index.get(pid)
        zone = "none"
        pos = "-"
        item = None
        if deep_item:
            zone = "deep_dive"
            pos = str(deep_item["rank"])
            item = deep_item["item"]
        elif quick_item:
            zone = "quick_skim"
            pos = str(quick_item["rank"])
            item = quick_item["item"]
        llm_score = item.get("llm_score") if isinstance(item, dict) else None
        selection_source = item.get("selection_source") if isinstance(item, dict) else None
        print(
            f"[TRACE][{stage}] id={pid} | zone={zone} | rank={pos}"
            f" | llm_score={f'{float(llm_score):.6f}' if isinstance(llm_score, (int, float)) else '-'}"
            f" | source={selection_source or '-'}",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Daily Paper Reader pipeline (steps 0~6).",
    )
    parser.add_argument(
        "--run-enrich",
        action="store_true",
        help="Run 0.enrich_config_queries.py before pipeline.",
    )
    parser.add_argument(
        "--embedding-device",
        default="cpu",
        help="Device for embedding retrieval (default: cpu).",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=8,
        help="Batch size for embedding retrieval (default: 8).",
    )
    parser.add_argument(
        "--fetch-ignore-seen",
        action="store_true",
        help="Pass --ignore-seen to Step1 (fetch arxiv), ignoring archive/arxiv_seen.json.",
    )
    parser.add_argument(
        "--fetch-days",
        type=int,
        default=None,
        help="Pass --days to Step1 (fetch arxiv). Default: use config.yaml/state logic.",
    )
    parser.add_argument(
        "--fetch-mode",
        default="auto",
        choices=("auto", "standard", "skims"),
        help="Force fetch-run mode: auto(按阈值), standard(非skims), skims(强制skims).",
    )
    parser.add_argument(
        "--profile-tag",
        default="",
        help="仅运行指定 tag 对应的词条；大小写不敏感，支持空格。",
    )
    parser.add_argument(
        "--trace-arxiv-id",
        action="append",
        default=None,
        help="可重复传入，追踪指定 arXiv ID 在各阶段是否命中；支持逗号分隔多个值。",
    )
    parser.add_argument(
        "--skip-fetch",
        default=None,
        action="store_true",
        help="跳过 Step 1（全量数据拉取）。当 Supabase 已完全接管检索时自动检测；"
             "显式传入则强制跳过。",
    )
    parser.add_argument(
        "--no-skip-fetch",
        dest="skip_fetch",
        action="store_false",
        help="强制执行 Step 1（全量数据拉取），即使 Supabase 已启用。",
    )
    args = parser.parse_args()

    python = sys.executable

    sidebar_date_label = resolve_sidebar_date_label(args.fetch_days)
    run_date_token = resolve_run_date_token(args.fetch_days)
    os.environ["DPR_RUN_DATE"] = run_date_token
    print(f"[INFO] DPR_RUN_DATE={run_date_token}", flush=True)
    profile_tag = str(args.profile_tag or os.getenv("DPR_FILTER_PROFILE_TAG") or "").strip()
    if profile_tag:
        os.environ["DPR_FILTER_PROFILE_TAG"] = profile_tag
        print(f"[INFO] profile_tag={profile_tag}", flush=True)
    else:
        os.environ.pop("DPR_FILTER_PROFILE_TAG", None)
    fetch_mode = (args.fetch_mode or "auto").strip().lower()
    if fetch_mode == "skims":
        use_skims_mode = True
    elif fetch_mode == "standard":
        use_skims_mode = False
    else:
        use_skims_mode = args.fetch_days is not None and args.fetch_days >= SKIMS_FETCH_DAYS_THRESHOLD
    if args.fetch_days is not None:
        print(
            f"[INFO] fetch_days={args.fetch_days}, run_mode={'skims' if use_skims_mode else 'standard'}, "
            f"fetch_mode={fetch_mode}",
            flush=True,
        )
    trace_ids = parse_trace_ids(args.trace_arxiv_id)
    if trace_ids:
        print(f"[TRACE] 启用论文追踪: {', '.join(trace_ids)}", flush=True)

    archive_dir = os.path.join(ROOT_DIR, "archive", run_date_token)
    raw_path = os.path.join(archive_dir, "raw", f"arxiv_papers_{run_date_token}.json")
    bm25_path = os.path.join(
        archive_dir,
        "filtered",
        f"arxiv_papers_{run_date_token}.bm25.json",
    )
    embedding_path = os.path.join(
        archive_dir,
        "filtered",
        f"arxiv_papers_{run_date_token}.embedding.json",
    )
    rrf_path = os.path.join(archive_dir, "filtered", f"arxiv_papers_{run_date_token}.json")
    rerank_path = os.path.join(archive_dir, "rank", f"arxiv_papers_{run_date_token}.json")
    llm_path = os.path.join(archive_dir, "rank", f"arxiv_papers_{run_date_token}.llm.json")
    recommend_mode = "skims" if use_skims_mode else "standard"
    recommend_path = os.path.join(
        archive_dir,
        "recommend",
        f"arxiv_papers_{run_date_token}.{recommend_mode}.json",
    )

    if args.run_enrich:
        run_step(
            "Step 0 - enrich config",
            [python, os.path.join(SRC_DIR, "0.enrich_config_queries.py")],
        )

    # 判断是否跳过 Step 1（全量数据拉取）
    if args.skip_fetch is None:
        # 自动检测：Supabase 已完全接管检索时跳过
        skip_fetch = should_skip_fetch()
    else:
        skip_fetch = args.skip_fetch

    if skip_fetch:
        print(
            "[INFO] 跳过 Step 1（全量数据拉取）："
            "Supabase 已完全接管检索（BM25 + 向量 RPC），"
            "后续步骤将直接使用数据库端召回。",
            flush=True,
        )
    else:
        run_step(
            "Step 1 - fetch arxiv",
            [
                python,
                os.path.join(SRC_DIR, "maintain", "fetchers", "fetch_arxiv.py"),
                *(["--days", str(args.fetch_days)] if args.fetch_days is not None else []),
                *(["--ignore-seen"] if args.fetch_ignore_seen else []),
            ],
        )
    if trace_ids:
        print_trace_retrieval("RAW", raw_path, trace_ids)
    run_step(
        "Step 2.1 - BM25",
        [python, os.path.join(SRC_DIR, "2.1.retrieval_papers_bm25.py")],
    )
    if trace_ids:
        print_trace_retrieval("BM25", bm25_path, trace_ids)
    run_step(
        "Step 2.2 - Embedding",
        [
            python,
            os.path.join(SRC_DIR, "2.2.retrieval_papers_embedding.py"),
            "--device",
            str(args.embedding_device),
            "--batch-size",
            str(args.embedding_batch_size),
        ],
    )
    if trace_ids:
        print_trace_retrieval("EMBEDDING", embedding_path, trace_ids)
    run_step(
        "Step 2.3 - RRF",
        [python, os.path.join(SRC_DIR, "2.3.retrieval_papers_rrf.py")],
    )
    if trace_ids:
        print_trace_retrieval("RRF", rrf_path, trace_ids)
    skip_rerank, rerank_base = should_skip_rerank()
    if skip_rerank:
        print(
            f"[INFO] Step 3 - Rerank 已跳过：当前主 LLM base 不属于柏拉图/BLT，"
            f"缺少稳定 /rerank 能力。base={rerank_base}",
            flush=True,
        )
        prepare_rerank_fallback(rrf_path, rerank_path)
    else:
        run_step(
            "Step 3 - Rerank",
            [python, os.path.join(SRC_DIR, "3.rank_papers.py")],
        )
    if trace_ids:
        print_trace_retrieval("RERANK", rerank_path, trace_ids)
    run_step(
        "Step 4 - LLM refine",
        [python, os.path.join(SRC_DIR, "4.llm_refine_papers.py")],
    )
    if trace_ids:
        print_trace_llm("LLM", llm_path, trace_ids)
    run_step(
        "Step 5 - Select",
        [
            python,
            os.path.join(SRC_DIR, "5.select_papers.py"),
            *(["--modes", "skims"] if use_skims_mode else []),
        ],
    )
    if trace_ids:
        print_trace_recommend("RECOMMEND", recommend_path, trace_ids)
    run_step(
        "Step 6 - Generate Docs",
        [
            python,
            os.path.join(SRC_DIR, "6.generate_docs.py"),
            *(["--mode", "skims"] if use_skims_mode else []),
            *(
                ["--sidebar-date-label", sidebar_date_label]
                if sidebar_date_label
                else []
            ),
        ],
        env=resolve_summary_step_env(),
    )


if __name__ == "__main__":
    main()
