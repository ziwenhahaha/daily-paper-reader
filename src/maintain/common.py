from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import List


MAINTAIN_DIR = os.path.dirname(__file__)
SRC_DIR = os.path.abspath(os.path.join(MAINTAIN_DIR, ".."))
ROOT_DIR = os.path.abspath(os.path.join(SRC_DIR, ".."))
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _norm(value: object) -> str:
    return str(value or "").strip()


def run_step(label: str, args: List[str]) -> None:
    log(f"{label}: {' '.join(args)}")
    subprocess.run(args, check=True)


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def count_raw_rows(path: str) -> int:
    safe_path = _norm(path)
    if not safe_path or not os.path.exists(safe_path):
        return 0
    with open(safe_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError(f"raw json must be list: {safe_path}")
    return len(data)


def default_raw_path(prefix: str, run_date: str) -> str:
    safe_prefix = _norm(prefix) or "papers"
    safe_date = _norm(run_date) or TODAY_STR
    return os.path.join(ROOT_DIR, "archive", safe_date, "raw", f"{safe_prefix}_{safe_date}.json")


def parse_year_list(value: object) -> List[int]:
    text = _norm(value)
    if not text:
        return []
    years: List[int] = []
    seen = set()
    for item in re.split(r"[,\s;]+", text):
        token = _norm(item)
        if not token:
            continue
        try:
            year = int(token)
        except Exception as exc:
            raise ValueError(f"invalid year: {token}") from exc
        if year <= 0:
            raise ValueError(f"invalid year: {token}")
        if year in seen:
            continue
        seen.add(year)
        years.append(year)
    return years


def resolve_target_years(*, years: object, year_end: int, year_count: int) -> List[int]:
    explicit_years = parse_year_list(years)
    if explicit_years:
        return explicit_years
    safe_count = max(int(year_count or 1), 1)
    end_year = int(year_end)
    start_year = end_year - safe_count + 1
    return list(range(start_year, end_year + 1))


def format_years_token(years: List[int]) -> str:
    safe_years = [str(int(year)) for year in years if int(year) > 0]
    return "-".join(safe_years) if safe_years else "years"


def cleanup_backend(*, backend_key: str, retention_days: int, skip_cleanup: bool) -> None:
    if skip_cleanup:
        log(f"[Maintain] skip cleanup backend={backend_key}")
        return
    service_key = _norm(os.getenv("SUPABASE_SERVICE_KEY"))
    if not service_key:
        log(f"[Maintain] missing SUPABASE_SERVICE_KEY, skip cleanup backend={backend_key}")
        return
    run_step(
        "Cleanup old papers",
        [
            sys.executable,
            os.path.join(MAINTAIN_DIR, "cleanup.py"),
            "--backend-key",
            _norm(backend_key),
            "--retention-days",
            str(max(int(retention_days or 1), 1)),
        ],
    )
