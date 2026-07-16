from __future__ import annotations

import argparse
import os
import sys
from typing import List

from common import TODAY_STR, cleanup_backend, default_raw_path, ensure_parent_dir, format_years_token, resolve_target_years, run_step


TABLES = {
    "osdi": "osdi_papers",
    "sosp": "sosp_papers",
    "ieee_sp": "ieee_sp_papers",
    "ndss": "ndss_papers",
}

FETCHER_LABELS = {
    "osdi": "OSDI",
    "sosp": "SOSP",
    "ieee_sp": "IEEE_SP",
    "ndss": "NDSS",
}


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--years", type=str, default="")
    parser.add_argument("--year-end", type=int, default=2026)
    parser.add_argument("--year-count", type=int, default=3)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--run-date", type=str, default=TODAY_STR)
    parser.add_argument("--retention-days", type=int, default=3650)
    parser.add_argument("--raw-input", type=str, default="")
    parser.add_argument("--skip-cleanup", action="store_true")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--allow-missing-pdf", action="store_true")
    parser.add_argument("--local-maintain", action="store_true")
    parser.add_argument("--embed-model", type=str, default="")
    parser.add_argument("--embed-device", type=str, default="cpu")
    parser.add_argument("--embed-batch-size", type=int, default=8)
    parser.add_argument("--embed-chunk-size", type=int, default=512)
    parser.add_argument("--schema", type=str, default=os.getenv("SUPABASE_SCHEMA", "public"))
    parser.add_argument("--no-embeddings", action="store_true")
    return parser


def run_public_conference_maintain(backend_key: str, *, description: str) -> None:
    safe_key = str(backend_key or "").strip().lower()
    if safe_key not in TABLES:
        raise ValueError(f"unsupported backend_key: {backend_key}")

    parser = build_parser(description)
    args = parser.parse_args()

    run_date = str(args.run_date or TODAY_STR).strip() or TODAY_STR
    os.environ["DPR_RUN_DATE"] = run_date
    cleanup_backend(backend_key=safe_key, retention_days=args.retention_days, skip_cleanup=args.skip_cleanup)

    years = resolve_target_years(years=args.years, year_end=args.year_end, year_count=args.year_count)
    years_str = ",".join(str(year) for year in years)
    raw_path = str(args.raw_input or "").strip() or default_raw_path(
        f"{safe_key}_papers_{format_years_token(years)}",
        run_date,
    )
    if not os.path.isabs(raw_path):
        raw_path = os.path.abspath(raw_path)
    ensure_parent_dir(raw_path)

    maintain_dir = os.path.dirname(__file__)
    if not args.skip_fetch:
        fetch_cmd: List[str] = [
            sys.executable,
            os.path.join(maintain_dir, "fetchers", "fetch_systems_security_conferences.py"),
            "--conference",
            FETCHER_LABELS[safe_key],
            "--years",
            years_str,
            "--workers",
            str(max(int(args.workers or 1), 1)),
            "--output",
            raw_path,
        ]
        if args.allow_missing_pdf:
            fetch_cmd.append("--allow-missing-pdf")
        run_step(f"Fetch {FETCHER_LABELS[safe_key]} papers", fetch_cmd)

    sync_cmd = [
        sys.executable,
        os.path.join(maintain_dir, "sync.py"),
        "--backend-key",
        safe_key,
        "--date",
        run_date,
        "--schema",
        str(args.schema),
        "--embed-batch-size",
        str(max(int(args.embed_batch_size or 1), 1)),
        "--embed-chunk-size",
        str(max(int(args.embed_chunk_size or 1), 1)),
        "--raw-input",
        raw_path,
        "--papers-table",
        TABLES[safe_key],
    ]
    if args.embed_model:
        sync_cmd += ["--embed-model", str(args.embed_model)]
    sync_cmd += ["--embed-device", str(args.embed_device or "cpu")]
    if args.local_maintain:
        sync_cmd.append("--local-maintain-mode")
    if args.no_embeddings:
        sync_cmd.append("--no-embeddings")
    run_step(f"Sync {FETCHER_LABELS[safe_key]} papers", sync_cmd)
