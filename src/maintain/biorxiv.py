#!/usr/bin/env python

from __future__ import annotations

import argparse
import os
import sys

from common import TODAY_STR, cleanup_backend, default_raw_path, ensure_parent_dir, run_step


def main() -> None:
    parser = argparse.ArgumentParser(description="维护入口：bioRxiv 抓取 + Supabase 同步。")
    parser.add_argument("--fetch-days", type=int, default=30)
    parser.add_argument("--chunk-days", type=int, default=1)
    parser.add_argument("--run-date", type=str, default=TODAY_STR)
    parser.add_argument("--retention-days", type=int, default=45)
    parser.add_argument("--raw-input", type=str, default="")
    parser.add_argument("--skip-cleanup", action="store_true")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--force-full-window", action="store_true")
    parser.add_argument("--local-maintain", action="store_true")
    parser.add_argument("--embed-model", type=str, default="")
    args = parser.parse_args()

    run_date = str(args.run_date or TODAY_STR).strip() or TODAY_STR
    os.environ["DPR_RUN_DATE"] = run_date
    cleanup_backend(backend_key="biorxiv", retention_days=args.retention_days, skip_cleanup=args.skip_cleanup)

    raw_path = str(args.raw_input or "").strip() or default_raw_path("biorxiv_papers", run_date)
    if not os.path.isabs(raw_path):
        raw_path = os.path.abspath(raw_path)
    ensure_parent_dir(raw_path)

    init_cmd = [
        sys.executable,
        os.path.join(os.path.dirname(__file__), "init_biorxiv.py"),
        "--days",
        str(max(int(args.fetch_days or 1), 1)),
        "--chunk-days",
        str(max(int(args.chunk_days or 1), 1)),
        "--date",
        run_date,
        "--raw-input",
        raw_path,
    ]
    if args.skip_fetch:
        init_cmd.append("--skip-fetch")
    if args.force_full_window:
        init_cmd.append("--ignore-seen")
    if args.local_maintain:
        init_cmd.append("--local-maintain")
    if str(args.embed_model or "").strip():
        init_cmd += ["--embed-model", str(args.embed_model).strip()]
    run_step("Maintain bioRxiv", init_cmd)


if __name__ == "__main__":
    main()
