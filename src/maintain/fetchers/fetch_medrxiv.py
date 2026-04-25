#!/usr/bin/env python

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import requests

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

try:
    from source_config import load_config_with_source_migration
except Exception:  # pragma: no cover - 兼容 package 导入路径
    from src.source_config import load_config_with_source_migration


SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")
CRAWL_STATE_FILE = os.path.join(ROOT_DIR, "archive", "medrxiv_crawl_state.json")
SEEN_IDS_FILE = os.path.join(ROOT_DIR, "archive", "medrxiv_seen.json")
DATE_TOKEN_RE = re.compile(r"^\d{8}$")
RANGE_TOKEN_RE = re.compile(r"^\d{8}-\d{8}$")
API_BASE = "https://api.biorxiv.org/details/medrxiv"


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[{ts}] {message}", flush=True)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass


def group_start(title: str) -> None:
    print(f"::group::{title}", flush=True)


def group_end() -> None:
    print("::endgroup::", flush=True)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def load_config() -> dict:
    try:
        return load_config_with_source_migration(CONFIG_FILE, write_back=False)
    except Exception as exc:
        log(f"[WARN] 读取 config.yaml 失败：{exc}")
        return {}


def resolve_days_window(default_days: int) -> int:
    config = load_config()
    paper_setting = (config or {}).get("arxiv_paper_setting") or {}
    try:
        days = int(paper_setting.get("days_window") or default_days)
    except Exception:
        days = default_days
    return max(days, 1)


def get_run_date_token(end_date: datetime) -> str:
    token = str(os.getenv("DPR_RUN_DATE") or "").strip()
    if DATE_TOKEN_RE.match(token) or RANGE_TOKEN_RE.match(token):
        return token
    return end_date.strftime("%Y%m%d")


def load_last_crawl_at() -> datetime | None:
    if not os.path.exists(CRAWL_STATE_FILE):
        return None
    try:
        with open(CRAWL_STATE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
    except Exception:
        return None
    raw = _norm(payload.get("last_crawl_at"))
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def save_last_crawl_at(at_time: datetime) -> None:
    os.makedirs(os.path.dirname(CRAWL_STATE_FILE), exist_ok=True)
    payload = {"last_crawl_at": at_time.astimezone(timezone.utc).isoformat()}
    with open(CRAWL_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_seen_state() -> tuple[set[str], datetime | None]:
    if not os.path.exists(SEEN_IDS_FILE):
        return set(), None
    try:
        with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
    except Exception:
        return set(), None

    raw_ids = payload.get("ids") or []
    if not isinstance(raw_ids, list):
        raw_ids = []
    seen_ids = {str(item).strip() for item in raw_ids if str(item).strip()}

    raw_latest = _norm(payload.get("latest_published_at"))
    latest_dt = None
    if raw_latest:
        try:
            latest_dt = datetime.fromisoformat(raw_latest.replace("Z", "+00:00"))
            if latest_dt.tzinfo is None:
                latest_dt = latest_dt.replace(tzinfo=timezone.utc)
            latest_dt = latest_dt.astimezone(timezone.utc)
        except Exception:
            latest_dt = None
    return seen_ids, latest_dt


def save_seen_state(seen_ids: set[str], latest_published_at: datetime | None) -> None:
    os.makedirs(os.path.dirname(SEEN_IDS_FILE), exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "latest_published_at": latest_published_at.astimezone(timezone.utc).isoformat()
        if latest_published_at
        else "",
        "ids": sorted(seen_ids),
    }
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def iter_time_windows(
    start_date: datetime,
    end_date: datetime,
    chunk_days: int,
) -> List[Tuple[datetime, datetime]]:
    chunk_days = max(int(chunk_days or 1), 1)
    cursor = start_date
    windows: List[Tuple[datetime, datetime]] = []
    while cursor < end_date:
        next_cursor = min(cursor + timedelta(days=chunk_days), end_date)
        windows.append((cursor, next_cursor))
        cursor = next_cursor
    return windows


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = _norm(value)
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _slugify_id(raw: str) -> str:
    text = _norm(raw).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "item"


def build_medrxiv_paper_id(doi: str, version: str | int | None) -> str:
    safe_doi = _slugify_id(doi)
    version_text = _norm(version)
    if version_text and version_text.isdigit():
        version_text = f"v{version_text}"
    elif version_text and not version_text.startswith("v"):
        version_text = f"v{version_text}"
    else:
        version_text = version_text or "v1"
    return f"medrxiv-{safe_doi}-{version_text}"


def _build_medrxiv_abs_url(doi: str, version: str | int | None) -> str:
    version_text = _norm(version)
    if version_text and version_text.isdigit():
        version_text = f"v{version_text}"
    elif version_text and not version_text.startswith("v"):
        version_text = f"v{version_text}"
    elif not version_text:
        version_text = ""
    return f"https://www.medrxiv.org/content/{doi}{version_text}"


def _build_medrxiv_pdf_url(doi: str, version: str | int | None) -> str:
    return f"{_build_medrxiv_abs_url(doi, version)}.full.pdf"


def parse_authors(raw_authors: Any) -> List[str]:
    text = _norm(raw_authors)
    if not text:
        return []
    out: List[str] = []
    seen = set()
    for item in text.split(";"):
        name = _norm(item)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def normalize_medrxiv_record(raw: Dict[str, Any]) -> Dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    doi = _norm(raw.get("doi"))
    version = _norm(raw.get("version") or "1")
    if not doi:
        return None
    category = _norm(raw.get("category"))
    published = _norm(raw.get("date"))
    if published and re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
        published = f"{published}T00:00:00+00:00"
    return {
        "id": build_medrxiv_paper_id(doi, version),
        "source": "medrxiv",
        "source_paper_id": doi,
        "doi": doi,
        "version": version,
        "title": _norm(raw.get("title")),
        "abstract": _norm(raw.get("abstract")),
        "authors": parse_authors(raw.get("authors")),
        "primary_category": category or None,
        "categories": [category] if category else [],
        "published": published or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "link": _build_medrxiv_pdf_url(doi, version),
        "pdf_url": _build_medrxiv_pdf_url(doi, version),
        "abs_url": _build_medrxiv_abs_url(doi, version),
    }


def fetch_window_records(start_dt: datetime, end_dt: datetime, *, timeout: int = 60) -> List[Dict[str, Any]]:
    start_text = start_dt.date().isoformat()
    end_text = (end_dt - timedelta(seconds=1)).date().isoformat()
    cursor = 0
    page_size = 100
    total = None
    out: List[Dict[str, Any]] = []
    seen_ids = set()

    while True:
        url = f"{API_BASE}/{start_text}/{end_text}/{cursor}"
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json() or {}
        messages = data.get("messages") or []
        if isinstance(messages, list) and messages:
            first_msg = messages[0] if isinstance(messages[0], dict) else {}
            try:
                total = int(first_msg.get("total") or total or 0)
            except Exception:
                total = total or 0
            try:
                page_size = max(int(first_msg.get("count") or page_size or 100), 1)
            except Exception:
                page_size = page_size or 100
        collection = data.get("collection") or []
        if not isinstance(collection, list) or not collection:
            break

        fetched_this_page = 0
        for raw in collection:
            normalized = normalize_medrxiv_record(raw)
            if not normalized:
                continue
            pid = _norm(normalized.get("id"))
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            out.append(normalized)
            fetched_this_page += 1

        cursor += page_size
        if total is not None and cursor >= total:
            break
        if fetched_this_page <= 0:
            break
        time.sleep(0.5)
    return out


def fetch_medrxiv_metadata(
    *,
    days: int | None = None,
    output_file: str | None = None,
    ignore_seen: bool = False,
    chunk_days: int = 7,
) -> None:
    end_date = datetime.now(timezone.utc)
    if days is None:
        days = resolve_days_window(1)
    days = max(int(days or 1), 1)

    if ignore_seen:
        seen_ids, latest_published_at = set(), None
        start_date = end_date - timedelta(days=days)
        source_desc = f"days_window={days} (ignore_seen)"
    else:
        seen_ids, latest_published_at = load_seen_state()
        if latest_published_at:
            start_date = latest_published_at
            source_desc = "latest_published_at"
        else:
            last_crawl_at = load_last_crawl_at()
            if last_crawl_at:
                start_date = last_crawl_at
                source_desc = "last_crawl_at"
            else:
                start_date = end_date - timedelta(days=days)
                source_desc = f"days_window={days}"

    start_date = max(start_date, end_date - timedelta(days=days))
    if start_date >= end_date:
        start_date = end_date - timedelta(minutes=1)

    windows = iter_time_windows(start_date, end_date, chunk_days=chunk_days)
    unique_papers: Dict[str, Dict[str, Any]] = {}
    max_published_new: datetime | None = None

    group_start("Step 1 - fetch medRxiv")
    log(
        "🌍 [medRxiv Ingest] Window: "
        f"{start_date.strftime('%Y%m%d%H%M')} TO {end_date.strftime('%Y%m%d%H%M')} "
        f"({source_desc})"
    )
    if len(windows) > 1:
        log(f"🗓️  [medRxiv Ingest] 将按 {chunk_days} 天/片拆分窗口：{len(windows)} 段")

    for idx, (window_start, window_end) in enumerate(windows, start=1):
        log(
            f"[medRxiv] 抓取窗口 {idx}/{len(windows)}："
            f"{window_start.date().isoformat()} ~ {(window_end - timedelta(seconds=1)).date().isoformat()}"
        )
        try:
            rows = fetch_window_records(window_start, window_end)
        except Exception as exc:
            log(f"[WARN] medRxiv 窗口抓取失败，将跳过：{exc}")
            continue

        for paper in rows:
            pid = _norm(paper.get("id"))
            if not pid or pid in seen_ids:
                continue
            if pid not in unique_papers:
                unique_papers[pid] = paper
            published_dt = _parse_iso_datetime(paper.get("published"))
            if published_dt and (max_published_new is None or published_dt > max_published_new):
                max_published_new = published_dt
            seen_ids.add(pid)

    total_count = len(unique_papers)
    log(f"✅ All Done. Total unique medRxiv papers fetched: {total_count}")

    if total_count > 0:
        if not output_file:
            run_token = get_run_date_token(end_date)
            archive_dir = os.path.join(ROOT_DIR, "archive", run_token)
            raw_dir = os.path.join(archive_dir, "raw")
            output_file = os.path.join(raw_dir, f"medrxiv_papers_{run_token}.json")

        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(list(unique_papers.values()), f, ensure_ascii=False, indent=2)
        log(f"💾 File saved to: {output_file}")
    else:
        log("⚠️ No medRxiv papers found. Check your date range or network.")

    if max_published_new:
        save_seen_state(seen_ids, max_published_new)
    else:
        save_seen_state(seen_ids, latest_published_at)
    save_last_crawl_at(end_date)
    group_end()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取 medRxiv 论文元数据。")
    parser.add_argument("--days", type=int, default=None, help="抓取窗口天数。")
    parser.add_argument("--output", type=str, default=None, help="输出 JSON 文件路径。")
    parser.add_argument("--ignore-seen", action="store_true", help="忽略已见状态，严格按 days_window 回溯。")
    parser.add_argument("--chunk-days", type=int, default=7, help="将时间窗口拆分为若干段（默认 7 天）。")
    args = parser.parse_args()

    fetch_medrxiv_metadata(
        days=args.days,
        output_file=args.output,
        ignore_seen=bool(args.ignore_seen),
        chunk_days=int(args.chunk_days or 7),
    )
