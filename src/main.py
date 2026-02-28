#!/usr/bin/env python
import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


SRC_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SRC_DIR, ".."))
CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")
LONG_RANGE_DAYS_THRESHOLD = 7
SKIMS_FETCH_DAYS_THRESHOLD = 11


def run_step(label: str, args: list[str]) -> None:
    print(f"[INFO] {label}: {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def load_arxiv_paper_setting() -> dict:
    if yaml is None or not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    setting = data.get("arxiv_paper_setting") or {}
    return setting if isinstance(setting, dict) else {}


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
    - 大窗口（>阈值）使用区间 token：YYYYMMDD-YYYYMMDD
    - 其它情况使用单日 token：YYYYMMDD
    """
    if fetch_days is not None:
        if fetch_days > LONG_RANGE_DAYS_THRESHOLD:
            return build_run_date_token(fetch_days)
        return datetime.now(timezone.utc).strftime("%Y%m%d")

    setting = load_arxiv_paper_setting()
    try:
        days_window = int(setting.get("days_window") or 0)
    except Exception:
        days_window = 0
    if days_window > LONG_RANGE_DAYS_THRESHOLD:
        return build_run_date_token(days_window)
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def resolve_sidebar_date_label(fetch_days: int | None) -> str | None:
    # 1) 显式传 --fetch-days 时，仅在大窗口模式下显示日期范围。
    if fetch_days is not None:
        if fetch_days > LONG_RANGE_DAYS_THRESHOLD:
            return build_sidebar_date_label(fetch_days)
        return None

    # 2) 未显式传入时，按 config 的 days_window 判断：
    #    仅在“大时间跨度”模式（默认阈值 >7 天）自动显示区间标题。
    setting = load_arxiv_paper_setting()
    try:
        days_window = int(setting.get("days_window") or 0)
    except Exception:
        days_window = 0
    if days_window > LONG_RANGE_DAYS_THRESHOLD:
        return build_sidebar_date_label(days_window)
    return None


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
    args = parser.parse_args()

    python = sys.executable

    sidebar_date_label = resolve_sidebar_date_label(args.fetch_days)
    run_date_token = resolve_run_date_token(args.fetch_days)
    os.environ["DPR_RUN_DATE"] = run_date_token
    print(f"[INFO] DPR_RUN_DATE={run_date_token}", flush=True)
    use_skims_mode = args.fetch_days is not None and args.fetch_days >= SKIMS_FETCH_DAYS_THRESHOLD
    if args.fetch_days is not None:
        print(
            f"[INFO] fetch_days={args.fetch_days}, run_mode={'skims' if use_skims_mode else 'standard'}",
            flush=True,
        )

    if args.run_enrich:
        run_step(
            "Step 0 - enrich config",
            [python, os.path.join(SRC_DIR, "0.enrich_config_queries.py")],
        )

    run_step(
        "Step 1 - fetch arxiv",
        [
            python,
            os.path.join(SRC_DIR, "1.fetch_paper_arxiv.py"),
            *(["--days", str(args.fetch_days)] if args.fetch_days is not None else []),
            *(["--ignore-seen"] if args.fetch_ignore_seen else []),
        ],
    )
    run_step(
        "Step 2.1 - BM25",
        [python, os.path.join(SRC_DIR, "2.1.retrieval_papers_bm25.py")],
    )
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
    run_step(
        "Step 2.3 - RRF",
        [python, os.path.join(SRC_DIR, "2.3.retrieval_papers_rrf.py")],
    )
    run_step(
        "Step 3 - Rerank",
        [python, os.path.join(SRC_DIR, "3.rank_papers.py")],
    )
    run_step(
        "Step 4 - LLM refine",
        [python, os.path.join(SRC_DIR, "4.llm_refine_papers.py")],
    )
    run_step(
        "Step 5 - Select",
        [
            python,
            os.path.join(SRC_DIR, "5.select_papers.py"),
            *(["--modes", "skims"] if use_skims_mode else []),
        ],
    )
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
    )


if __name__ == "__main__":
    main()
