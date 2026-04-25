#!/usr/bin/env python

from __future__ import annotations

import argparse
import os
import sys

from common import TODAY_STR, cleanup_backend, default_raw_path, ensure_parent_dir, run_step


def main() -> None:
    parser = argparse.ArgumentParser(description="维护入口：arXiv 抓取 + Supabase 同步。")
    parser.add_argument("--fetch-days", type=str, default="")
    parser.add_argument("--chunk-days", type=int, default=7)
    parser.add_argument("--run-date", type=str, default=TODAY_STR)
    parser.add_argument("--retention-days", type=int, default=45)
    parser.add_argument("--raw-input", type=str, default="")
    parser.add_argument("--skip-cleanup", action="store_true")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--ignore-seen", action="store_true", default=True)
    parser.add_argument("--use-seen", dest="ignore_seen", action="store_false")
    parser.add_argument("--local-maintain", action="store_true")
    parser.add_argument("--embed-model", type=str, default="")
    args = parser.parse_args()

    run_date = str(args.run_date or TODAY_STR).strip() or TODAY_STR
    os.environ["DPR_RUN_DATE"] = run_date
    cleanup_backend(backend_key="arxiv", retention_days=args.retention_days, skip_cleanup=args.skip_cleanup)

    raw_path = str(args.raw_input or "").strip() or default_raw_path("arxiv_papers", run_date)
    if not os.path.isabs(raw_path):
        raw_path = os.path.abspath(raw_path)
    ensure_parent_dir(raw_path)

    init_cmd = [
        sys.executable,
        os.path.join(os.path.dirname(__file__), "init_arxiv.py"),
        "--date",
        run_date,
        "--chunk-days",
        str(max(int(args.chunk_days or 1), 1)),
        "--raw-input",
        raw_path,
    ]
    if str(args.fetch_days or "").strip():
        init_cmd += ["--days", str(args.fetch_days).strip()]
    if args.skip_fetch:
        init_cmd.append("--skip-fetch")
    if args.ignore_seen:
        init_cmd.append("--ignore-seen")
    else:
        init_cmd.append("--use-seen")
    if args.local_maintain:
        init_cmd.append("--local-maintain")
    if str(args.embed_model or "").strip():
        init_cmd += ["--embed-model", str(args.embed_model).strip()]
    run_step("Maintain arXiv", init_cmd)


if __name__ == "__main__":
    main()
