#!/usr/bin/env python

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

import torch


SCRIPT_DIR = os.path.dirname(__file__)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
DEFAULT_EMBED_BATCH_SIZE = 8
DEFAULT_EMBED_CHUNK_SIZE = 512
LOCAL_MAINTAIN_EMBED_BATCH_SIZE = 64
LOCAL_MAINTAIN_EMBED_CHUNK_SIZE = 1024


def run_step(label: str, args: list[str]) -> None:
    print(f"[INFO] {label}: {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取近三年 AAAI 官方 proceedings 并同步到 Supabase。")
    parser.add_argument("--year-end", type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument("--year-count", type=int, default=3)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--date", type=str, default=TODAY_STR)
    parser.add_argument("--raw-input", type=str, default="")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--embed-model", type=str, default="")
    parser.add_argument("--embed-device", type=str, default="")
    parser.add_argument("--embed-devices", type=str, default="")
    parser.add_argument("--embed-batch-size", type=int, default=DEFAULT_EMBED_BATCH_SIZE)
    parser.add_argument("--embed-chunk-size", type=int, default=DEFAULT_EMBED_CHUNK_SIZE)
    parser.add_argument("--embed-max-length", type=int, default=0)
    parser.add_argument("--embed-local-only", dest="embed_local_only", action="store_true")
    parser.add_argument("--allow-remote-embedding", dest="embed_local_only", action="store_false")
    parser.set_defaults(embed_local_only=False)
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
    date_str = str(args.date or TODAY_STR).strip() or TODAY_STR
    os.environ["DPR_RUN_DATE"] = date_str
    print(f"[INFO] DPR_RUN_DATE={date_str}", flush=True)

    if args.local_maintain and args.embed_batch_size == DEFAULT_EMBED_BATCH_SIZE:
        args.embed_batch_size = LOCAL_MAINTAIN_EMBED_BATCH_SIZE
    if args.local_maintain and args.embed_chunk_size == DEFAULT_EMBED_CHUNK_SIZE:
        args.embed_chunk_size = LOCAL_MAINTAIN_EMBED_CHUNK_SIZE
    if args.local_maintain:
        args.embed_local_only = True
    if not str(args.embed_device or "").strip() and not str(args.embed_devices or "").strip():
        if not args.local_maintain:
            args.embed_device = "cpu"
        elif torch.cuda.is_available() and int(torch.cuda.device_count() or 0) > 0:
            args.embed_devices = ",".join(f"cuda:{idx}" for idx in range(int(torch.cuda.device_count() or 0)))
        else:
            args.embed_device = "cpu"
    elif args.local_maintain and not str(args.embed_devices or "").strip() and str(args.embed_device or "").strip().lower() == "auto":
        if torch.cuda.is_available() and int(torch.cuda.device_count() or 0) > 0:
            args.embed_devices = ",".join(f"cuda:{idx}" for idx in range(int(torch.cuda.device_count() or 0)))
        else:
            args.embed_device = "cpu"

    raw_path = str(args.raw_input or "").strip()
    if raw_path:
        if not os.path.isabs(raw_path):
            raw_path = os.path.abspath(os.path.join(project_root, raw_path))
    else:
        token = f"aaai-papers-{int(args.year_end) - int(args.year_count) + 1}-{int(args.year_end)}"
        raw_path = os.path.join(project_root, "archive", date_str, "raw", f"{token}.json")

    if not args.skip_fetch:
        fetch_cmd = [
            python,
            os.path.join(SCRIPT_DIR, "fetchers", "fetch_aaai_ojs.py"),
            "--year-end",
            str(int(args.year_end)),
            "--year-count",
            str(max(int(args.year_count or 1), 1)),
            "--workers",
            str(max(int(args.workers or 1), 1)),
            "--output",
            raw_path,
        ]
        run_step("Step 1 - fetch AAAI proceedings", fetch_cmd)
    else:
        print(f"[INFO] Step 1 已跳过，复用原始文件：{raw_path}", flush=True)

    sync_cmd = [
        python,
        os.path.join(SCRIPT_DIR, "sync.py"),
        "--backend-key",
        "aaai",
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
        "--papers-table",
        "aaai_papers",
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
    run_step("Step 2 - sync AAAI papers to Supabase", sync_cmd)


if __name__ == "__main__":
    main()
