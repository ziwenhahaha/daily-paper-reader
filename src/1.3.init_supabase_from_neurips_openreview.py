#!/usr/bin/env python

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone


SCRIPT_DIR = os.path.dirname(__file__)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")


def run_step(label: str, args: list[str]) -> None:
    print(f"[INFO] {label}: {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取近三年 NeurIPS OpenReview 投稿并同步到 Supabase。")
    parser.add_argument("--year-end", type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument("--year-count", type=int, default=3)
    parser.add_argument("--date", type=str, default=TODAY_STR)
    parser.add_argument("--raw-input", type=str, default="")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--username", type=str, default=os.getenv("OPENREVIEW_USERNAME", ""))
    parser.add_argument("--password", type=str, default=os.getenv("OPENREVIEW_PASSWORD", ""))
    parser.add_argument("--embed-model", type=str, default="")
    parser.add_argument("--embed-device", type=str, default="cpu")
    parser.add_argument("--embed-devices", type=str, default="")
    parser.add_argument("--embed-batch-size", type=int, default=8)
    parser.add_argument("--embed-max-length", type=int, default=0)
    parser.add_argument("--schema", type=str, default=os.getenv("SUPABASE_SCHEMA", "public"))
    parser.add_argument("--upsert-batch-size", type=int, default=200)
    parser.add_argument("--upsert-timeout", type=int, default=120)
    parser.add_argument("--upsert-retries", type=int, default=5)
    parser.add_argument("--upsert-retry-wait", type=float, default=2.0)
    parser.add_argument("--no-embeddings", action="store_true")
    args = parser.parse_args()

    python = sys.executable
    project_root = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    date_str = str(args.date or TODAY_STR).strip() or TODAY_STR
    os.environ["DPR_RUN_DATE"] = date_str
    print(f"[INFO] DPR_RUN_DATE={date_str}", flush=True)

    raw_path = str(args.raw_input or "").strip()
    if raw_path:
        if not os.path.isabs(raw_path):
            raw_path = os.path.abspath(os.path.join(project_root, raw_path))
    else:
        token = f"neurips-openreview-{int(args.year_end) - int(args.year_count) + 1}-{int(args.year_end)}"
        raw_path = os.path.join(project_root, "archive", date_str, "raw", f"{token}.json")

    if not args.skip_fetch:
        fetch_cmd = [
            python,
            os.path.join(SCRIPT_DIR, "1.fetch_paper_openreview_conference.py"),
            "--conference",
            "NeurIPS",
            "--year-end",
            str(int(args.year_end)),
            "--year-count",
            str(max(int(args.year_count or 1), 1)),
            "--output",
            raw_path,
        ]
        if str(args.username or "").strip():
            fetch_cmd += ["--username", str(args.username)]
        if str(args.password or "").strip():
            fetch_cmd += ["--password", str(args.password)]
        run_step("Step 1 - fetch NeurIPS OpenReview", fetch_cmd)
    else:
        print(f"[INFO] Step 1 已跳过，复用原始文件：{raw_path}", flush=True)

    sync_cmd = [
        python,
        os.path.join(SCRIPT_DIR, "1.2.sync_supabase_public.py"),
        "--backend-key",
        "neurips",
        "--date",
        date_str,
        "--schema",
        str(args.schema),
        "--embed-batch-size",
        str(max(int(args.embed_batch_size or 1), 1)),
        "--embed-max-length",
        str(int(args.embed_max_length or 0)),
        "--upsert-batch-size",
        str(max(int(args.upsert_batch_size or 1), 1)),
        "--upsert-timeout",
        str(max(int(args.upsert_timeout or 1), 1)),
        "--upsert-retries",
        str(max(int(args.upsert_retries or 0), 0)),
        "--upsert-retry-wait",
        str(max(float(args.upsert_retry_wait or 0.0), 0.0)),
        "--raw-input",
        raw_path,
        "--papers-table",
        "neurips_openreview_papers",
    ]
    if args.embed_model:
        sync_cmd += ["--embed-model", str(args.embed_model)]
    if args.embed_devices:
        sync_cmd += ["--embed-devices", str(args.embed_devices)]
    else:
        sync_cmd += ["--embed-device", str(args.embed_device or "cpu")]
    if args.no_embeddings:
        sync_cmd.append("--no-embeddings")
    run_step("Step 2 - sync NeurIPS OpenReview to Supabase", sync_cmd)


if __name__ == "__main__":
    main()
