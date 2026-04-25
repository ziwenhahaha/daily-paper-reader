#!/usr/bin/env python

from __future__ import annotations

import argparse
import os
import sys

from common import TODAY_STR, cleanup_backend, default_raw_path, ensure_parent_dir, run_step


def main() -> None:
    parser = argparse.ArgumentParser(description="维护入口：EMNLP 抓取 + Supabase 同步。")
    parser.add_argument("--year-end", type=int, default=2025)
    parser.add_argument("--year-count", type=int, default=3)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--run-date", type=str, default=TODAY_STR)
    parser.add_argument("--retention-days", type=int, default=3650)
    parser.add_argument("--raw-input", type=str, default="")
    parser.add_argument("--skip-cleanup", action="store_true")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--local-maintain", action="store_true")
    parser.add_argument("--embed-model", type=str, default="")
    args = parser.parse_args()

    run_date = str(args.run_date or TODAY_STR).strip() or TODAY_STR
    os.environ["DPR_RUN_DATE"] = run_date
    cleanup_backend(backend_key="emnlp", retention_days=args.retention_days, skip_cleanup=args.skip_cleanup)

    start_year = int(args.year_end) - int(args.year_count) + 1
    raw_path = str(args.raw_input or "").strip() or default_raw_path(
        f"emnlp-anthology-{start_year}-{int(args.year_end)}",
        run_date,
    )
    if not os.path.isabs(raw_path):
        raw_path = os.path.abspath(raw_path)
    ensure_parent_dir(raw_path)

    init_cmd = [
        sys.executable,
        os.path.join(os.path.dirname(__file__), "init_emnlp.py"),
        "--year-end",
        str(int(args.year_end)),
        "--year-count",
        str(max(int(args.year_count or 1), 1)),
        "--workers",
        str(max(int(args.workers or 1), 1)),
        "--date",
        run_date,
        "--raw-input",
        raw_path,
    ]
    if args.skip_fetch:
        init_cmd.append("--skip-fetch")
    if args.local_maintain:
        init_cmd.append("--local-maintain")
    if str(args.embed_model or "").strip():
        init_cmd += ["--embed-model", str(args.embed_model).strip()]
    run_step("Maintain EMNLP", init_cmd)


if __name__ == "__main__":
    main()
