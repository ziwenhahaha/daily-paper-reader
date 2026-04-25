#!/usr/bin/env python

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import torch


SCRIPT_DIR = os.path.dirname(__file__)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
LONG_RANGE_DAYS_THRESHOLD = 7
DEFAULT_EMBED_BATCH_SIZE = 8
DEFAULT_EMBED_CHUNK_SIZE = 512
LOCAL_MAINTAIN_EMBED_BATCH_SIZE = 64
LOCAL_MAINTAIN_EMBED_CHUNK_SIZE = 1024


def run_step(label: str, args: list[str]) -> None:
    print(f"[INFO] {label}: {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def build_run_date_token(days: int) -> str:
    safe_days = max(int(days), 1)
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=safe_days - 1)
    return f"{start_date:%Y%m%d}-{end_date:%Y%m%d}"


def resolve_date_token(date_arg: str, days: int) -> str:
    manual = str(date_arg or "").strip()
    if manual:
        return manual
    if int(days or 1) > LONG_RANGE_DAYS_THRESHOLD:
        return build_run_date_token(days)
    return TODAY_STR


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取近 N 天 bioRxiv 并同步到 Supabase（同 project 可用）。")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--chunk-days", type=int, default=7)
    parser.add_argument("--date", type=str, default="")
    parser.add_argument("--raw-input", type=str, default="")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--ignore-seen", action="store_true", default=False)
    parser.add_argument("--use-seen", dest="ignore_seen", action="store_false")
    parser.add_argument("--embed-model", type=str, default="")
    parser.add_argument("--embed-device", type=str, default="")
    parser.add_argument("--embed-devices", type=str, default="")
    parser.add_argument("--embed-batch-size", type=int, default=DEFAULT_EMBED_BATCH_SIZE)
    parser.add_argument("--embed-chunk-size", type=int, default=DEFAULT_EMBED_CHUNK_SIZE)
    parser.add_argument("--embed-max-length", type=int, default=0)
    parser.add_argument("--embed-local-only", action="store_true")
    parser.add_argument("--local-maintain", action="store_true")
    parser.add_argument("--reserve-upload-cpus", type=int, default=2)
    parser.add_argument("--upload-workers", type=int, default=2)
    parser.add_argument("--max-pending-upload-chunks", type=int, default=2)
    parser.add_argument("--schema", type=str, default=os.getenv("SUPABASE_SCHEMA", "public"))
    parser.add_argument("--upsert-batch-size", type=int, default=200)
    parser.add_argument("--upsert-timeout", type=int, default=120)
    parser.add_argument("--upsert-retries", type=int, default=5)
    parser.add_argument("--upsert-retry-wait", type=float, default=2.0)
    parser.add_argument("--no-embeddings", action="store_true")
    args = parser.parse_args()

    python = sys.executable
    project_root = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
    date_str = resolve_date_token(args.date, int(args.days or 1))
    os.environ["DPR_RUN_DATE"] = date_str
    print(f"[INFO] DPR_RUN_DATE={date_str}", flush=True)
    if args.local_maintain and args.embed_batch_size == DEFAULT_EMBED_BATCH_SIZE:
        args.embed_batch_size = LOCAL_MAINTAIN_EMBED_BATCH_SIZE
    if args.local_maintain and args.embed_chunk_size == DEFAULT_EMBED_CHUNK_SIZE:
        args.embed_chunk_size = LOCAL_MAINTAIN_EMBED_CHUNK_SIZE
    if args.local_maintain:
        args.embed_local_only = True
    if not str(args.embed_device or "").strip() and not str(args.embed_devices or "").strip():
        if args.local_maintain and torch.cuda.is_available() and int(torch.cuda.device_count() or 0) > 0:
            args.embed_devices = ",".join(f"cuda:{idx}" for idx in range(int(torch.cuda.device_count() or 0)))
        else:
            args.embed_device = "cpu"

    raw_path = str(args.raw_input or "").strip()
    if raw_path:
        if not os.path.isabs(raw_path):
            raw_path = os.path.abspath(os.path.join(project_root, raw_path))
    else:
        raw_path = os.path.join(project_root, "archive", date_str, "raw", f"biorxiv_papers_{date_str}.json")

    if not args.skip_fetch:
        fetch_cmd = [
            python,
            os.path.join(SCRIPT_DIR, "fetchers", "fetch_biorxiv.py"),
            "--days",
            str(max(int(args.days or 1), 1)),
            "--chunk-days",
            str(max(int(args.chunk_days or 1), 1)),
            "--output",
            raw_path,
        ]
        if args.ignore_seen:
            fetch_cmd.append("--ignore-seen")
        run_step("Step 1 - fetch bioRxiv", fetch_cmd)
    else:
        print(f"[INFO] Step 1 已跳过，复用原始文件：{raw_path}", flush=True)

    sync_cmd = [
        python,
        os.path.join(SCRIPT_DIR, "sync.py"),
        "--backend-key",
        "biorxiv",
        "--date",
        date_str,
        "--schema",
        str(args.schema),
        "--embed-batch-size",
        str(max(int(args.embed_batch_size or 1), 1)),
        "--embed-chunk-size",
        str(max(int(args.embed_chunk_size or 1), 1)),
        "--embed-max-length",
        str(int(args.embed_max_length or 0)),
        "--reserve-upload-cpus",
        str(max(int(args.reserve_upload_cpus or 0), 0)),
        "--upload-workers",
        str(max(int(args.upload_workers or 1), 1)),
        "--max-pending-upload-chunks",
        str(max(int(args.max_pending_upload_chunks or 1), 1)),
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
    ]
    if args.local_maintain:
        sync_cmd.append("--local-maintain-mode")
    if args.embed_model:
        sync_cmd += ["--embed-model", str(args.embed_model)]
    if args.embed_devices:
        sync_cmd += ["--embed-devices", str(args.embed_devices)]
    else:
        sync_cmd += ["--embed-device", str(args.embed_device or "cpu")]
    if args.embed_local_only and not args.local_maintain:
        sync_cmd.append("--embed-local-only")
    if args.no_embeddings:
        sync_cmd.append("--no-embeddings")
    run_step("Step 2 - sync bioRxiv to Supabase", sync_cmd)


if __name__ == "__main__":
    main()
