#!/usr/bin/env python
# Initialize Supabase public paper library:
# 1) Use maintain/fetchers/fetch_arxiv.py to fetch long-term window chunked papers
# 2) Use maintain/sync.py to generate embedding and upsert to Supabase

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

try:
    import torch
except Exception:  # pragma: no cover
    torch = None


SCRIPT_DIR = os.path.dirname(__file__)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
LONG_RANGE_DAYS_THRESHOLD = 7
RANGE_TOKEN_RE = re.compile(r"^(\d{8})-(\d{8})$")
DEFAULT_FETCH_DAYS = 9
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


def find_latest_raw_file(project_root: str) -> str:
    archive_root = os.path.join(project_root, "archive")
    if not os.path.isdir(archive_root):
        return ""
    best_path = ""
    best_mtime = -1.0
    for token in os.listdir(archive_root):
        raw_dir = os.path.join(archive_root, token, "raw")
        if not os.path.isdir(raw_dir):
            continue
        for name in os.listdir(raw_dir):
            if not (name.startswith("arxiv_papers_") and name.endswith(".json")):
                continue
            path = os.path.join(raw_dir, name)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime > best_mtime:
                best_mtime = mtime
                best_path = path
    return best_path


def count_raw_rows(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f) or []
    if not isinstance(data, list):
        raise RuntimeError(f"raw json must be list: {path}")
    return len(data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch recent N days arXiv and initialize sync to Supabase (including embedding).",
    )
    parser.add_argument("--days", type=int, default=DEFAULT_FETCH_DAYS, help="backtrack fetch days, default 9.")
    parser.add_argument("--chunk-days", type=int, default=7, help="fetch chunk window days, default 7.")
    parser.add_argument(
        "--ignore-seen",
        action="store_true",
        default=True,
        help="Ignore seen/crawl_state during fetch, strictly backtrack by days (default enabled).",
    )
    parser.add_argument(
        "--use-seen",
        dest="ignore_seen",
        action="store_false",
        help="Use seen/crawl_state incremental state during fetch (disable ignore-seen).",
    )
    parser.add_argument(
        "--date",
        type=str,
        default="",
        help="Sync date directory (supports YYYYMMDD or YYYYMMDD-YYYYMMDD); automatically derive by days if not provided.",
    )
    parser.add_argument(
        "--raw-input",
        type=str,
        default="",
        help="Optional: directly specify the original JSON file path (preferred over --date directory derivation).",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip fetch step, directly reuse archive/<token>/raw/arxiv_papers_<token>.json for sync.",
    )
    parser.add_argument("--embed-model", type=str, default="", help="embedding model (empty=use config/default).")
    parser.add_argument("--embed-device", type=str, default="", help="single device mode (e.g. cpu/cuda:0).")
    parser.add_argument("--embed-devices", type=str, default="", help="multiple device list, e.g. cuda:0,cuda:1.")
    parser.add_argument("--embed-batch-size", type=int, default=DEFAULT_EMBED_BATCH_SIZE, help="embedding batch size.")
    parser.add_argument("--embed-chunk-size", type=int, default=DEFAULT_EMBED_CHUNK_SIZE, help="embedding chunk size for streaming upload.")
    parser.add_argument("--embed-max-length", type=int, default=0, help="embedding max length, <=0 means no limit.")
    parser.add_argument("--embed-local-only", action="store_true", help="force use local embedding, not use remote service.")
    parser.add_argument("--local-maintain", action="store_true", help="local maintain Supabase mode: local embedding + streaming upload.")
    parser.add_argument("--reserve-upload-cpus", type=int, default=2, help="CPU cores reserved for upload in local maintain mode.")
    parser.add_argument("--upload-workers", type=int, default=2, help="upload concurrency in local maintain mode.")
    parser.add_argument("--max-pending-upload-chunks", type=int, default=2, help="maximum pending upload chunks in local maintain mode.")
    parser.add_argument("--schema", type=str, default=os.getenv("SUPABASE_SCHEMA", "public"), help="Supabase schema.")
    parser.add_argument("--upsert-batch-size", type=int, default=200, help="Supabase upsert batch size.")
    parser.add_argument("--upsert-timeout", type=int, default=120, help="Supabase upsert timeout (seconds).")
    parser.add_argument("--upsert-retries", type=int, default=5, help="Supabase upsert retry times per batch.")
    parser.add_argument("--upsert-retry-wait", type=float, default=2.0, help="Supabase upsert retry wait time (seconds).")
    parser.add_argument("--no-embeddings", action="store_true", help="only sync metadata, not generate embedding.")
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
        cuda_mod = getattr(torch, "cuda", None)
        cuda_available = bool(cuda_mod and getattr(cuda_mod, "is_available", lambda: False)())
        cuda_count = int(getattr(cuda_mod, "device_count", lambda: 0)() or 0) if cuda_mod else 0
        if args.local_maintain and cuda_available and cuda_count > 0:
            args.embed_devices = ",".join(f"cuda:{idx}" for idx in range(cuda_count))
        else:
            args.embed_device = "cpu"
    raw_input = str(args.raw_input or "").strip()
    if raw_input:
        if os.path.isabs(raw_input):
            raw_path = raw_input
        else:
            raw_path = os.path.abspath(os.path.join(project_root, raw_input))
    else:
        raw_path = os.path.join(
            project_root,
            "archive",
            date_str,
            "raw",
            f"arxiv_papers_{date_str}.json",
        )

    if not args.skip_fetch:
        fetch_cmd = [
            python,
            os.path.join(SCRIPT_DIR, "fetchers", "fetch_arxiv.py"),
            "--days",
            str(max(int(args.days or 1), 1)),
            "--chunk-days",
            str(max(int(args.chunk_days or 1), 1)),
            "--output",
            raw_path,
            "--disable-supabase-read",
        ]
        if args.ignore_seen:
            fetch_cmd.append("--ignore-seen")
        run_step("Step 1 - fetch arXiv", fetch_cmd)
    else:
        if not os.path.exists(raw_path):
            fallback = ""
            m = RANGE_TOKEN_RE.match(date_str)
            if m:
                end_token = m.group(2)
                legacy_candidate = os.path.join(
                    project_root,
                    "archive",
                    end_token,
                    "raw",
                    f"arxiv_papers_{end_token}.json",
                )
                if os.path.exists(legacy_candidate):
                    fallback = legacy_candidate
            if not fallback:
                latest = find_latest_raw_file(project_root)
                if latest:
                    fallback = latest

            if fallback:
                print(
                    f"[WARN] --skip-fetch specified path does not exist, automatically fallback to original file: {fallback}",
                    flush=True,
                )
                raw_path = fallback
            else:
                raise FileNotFoundError(
                    f"--skip-fetch specified, but original file not found: {raw_path}"
                )
        print(f"[INFO] Step 1 skipped, reusing original file: {raw_path}", flush=True)

    fetch_count = count_raw_rows(raw_path)
    print(f"[INFO] arXiv fetch pre-check result: count={fetch_count}, raw_path={raw_path}", flush=True)
    if fetch_count <= 0:
        print("[INFO] No new arXiv papers fetched, skipping Supabase sync.", flush=True)
        return

    sync_cmd = [
        python,
        os.path.join(SCRIPT_DIR, "sync.py"),
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
    ]
    if args.local_maintain:
        sync_cmd.append("--local-maintain-mode")
    sync_cmd += ["--raw-input", raw_path]
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
    run_step("Step 2 - sync Supabase", sync_cmd)


if __name__ == "__main__":
    main()
