#!/usr/bin/env python
import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone


SRC_DIR = os.path.dirname(__file__)


def run_step(label: str, args: list[str]) -> None:
    print(f"[INFO] {label}: {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


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

    sidebar_date_label = None
    if args.fetch_days is not None:
        days = max(int(args.fetch_days), 1)
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days - 1)
        sidebar_date_label = f"{start_date:%Y-%m-%d} ~ {end_date:%Y-%m-%d}"

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
            *(["--modes", "skims"] if args.fetch_days is not None else []),
        ],
    )
    run_step(
        "Step 6 - Generate Docs",
        [
            python,
            os.path.join(SRC_DIR, "6.generate_docs.py"),
            *(["--mode", "skims"] if args.fetch_days is not None else []),
            *(
                ["--sidebar-date-label", sidebar_date_label]
                if sidebar_date_label
                else []
            ),
        ],
    )


if __name__ == "__main__":
    main()
