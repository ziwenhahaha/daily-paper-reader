import arxiv
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from supabase_source import (
    get_supabase_read_config,
    fetch_recent_papers,
    fetch_papers_by_date_range,
)
try:
    from source_config import load_config_with_source_migration
except Exception:  # pragma: no cover - compatible package import path
    from src.source_config import load_config_with_source_migration

# Project root directory (current script is located in src/maintain/fetchers/)
SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
CONFIG_FILE = os.getenv("DPR_CONFIG_FILE") or os.path.join(ROOT_DIR, "config.yaml")
CRAWL_STATE_FILE = os.path.join(ROOT_DIR, "archive", "crawl_state.json")
SEEN_IDS_FILE = os.path.join(ROOT_DIR, "archive", "arxiv_seen.json")

# Main ArXiv primary categories list
# Note: Physics is special, ArXiv has many independent physics archives, for safety, we list the main ones
CATEGORIES_TO_FETCH = [
    "cs", "math", "stat", "q-bio", "q-fin", "eess", "econ",
    "physics", "cond-mat", "hep-ph", "hep-th", "gr-qc", "astro-ph",
]
RANGE_TOKEN_RE = re.compile(r"^\d{8}-\d{8}$")


def load_config() -> dict:
    try:
        return load_config_with_source_migration(CONFIG_FILE, write_back=False)
    except Exception as e:
        log(f"[WARN] Read config.yaml failed: {e}")
        return {}


def resolve_days_window(default_days: int) -> int:
    config = load_config()
    paper_setting = (config or {}).get("arxiv_paper_setting") or {}
    crawler_setting = (config or {}).get("crawler") or {}

    value = paper_setting.get("days_window")
    if value is None:
        value = crawler_setting.get("days_window")
    if value is not None:
        try:
            return max(int(value), 1)
        except Exception:
            pass
    return max(default_days, 1)


def get_run_date_token(end_date: datetime) -> str:
    token = str(os.getenv("DPR_RUN_DATE") or "").strip()
    if re.match(r"^\d{8}$", token) or RANGE_TOKEN_RE.match(token):
        return token
    return end_date.strftime("%Y%m%d")


def resolve_supabase_time_window(
    *,
    end_date: datetime,
    days: int,
) -> tuple[datetime, datetime, str]:
    """
    Distinguish single day/large interval window:
    - If DPR_RUN_DATE=YYYYMMDD: Fetch the natural day [00:00, +1d)
    - If DPR_RUN_DATE=YYYYMMDD-YYYYMMDD: Fetch the interval [start_day 00:00, end_day+1d 00:00)
    - Otherwise fallback to old logic: Recent days [now-days, now)
    """
    token = str(os.getenv("DPR_RUN_DATE") or "").strip()
    if re.match(r"^\d{8}$", token):
        # Critical fix:
        # main.py uses single-day token (e.g. 20260208) as directory identifier for small windows (<=7 days),
        # but this should not force Supabase to only fetch "single day".
        # When days>1, still fetch by rolling window to avoid fetch-days=4 but only fetching 1 day.
        safe_days = max(int(days or 1), 1)
        if safe_days > 1:
            return end_date - timedelta(days=safe_days), end_date, f"rolling:{safe_days}d(token={token})"
        day = datetime.strptime(token, "%Y%m%d").replace(tzinfo=timezone.utc)
        return day, day + timedelta(days=1), f"single-day:{token}"

    m = RANGE_TOKEN_RE.match(token)
    if m:
        start_day = datetime.strptime(m.group(0).split("-", 1)[0], "%Y%m%d").replace(tzinfo=timezone.utc)
        end_day = datetime.strptime(m.group(0).split("-", 1)[1], "%Y%m%d").replace(tzinfo=timezone.utc)
        return start_day, end_day + timedelta(days=1), f"range:{m.group(0)}"

    safe_days = max(int(days or 1), 1)
    return end_date - timedelta(days=safe_days), end_date, f"rolling:{safe_days}d"


def load_last_crawl_at() -> datetime | None:
    if not os.path.exists(CRAWL_STATE_FILE):
        return None
    try:
        with open(CRAWL_STATE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
    except Exception:
        return None
    raw = str(payload.get("last_crawl_at") or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


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
    seen_ids = {str(i).strip() for i in raw_ids if str(i).strip()}

    raw_latest = str(payload.get("latest_published_at") or "").strip()
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

def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[{ts}] {message}", flush=True)
    except BrokenPipeError:
        # Allow users to truncate output with `| head` without crashing the script
        try:
            sys.stdout.close()
        except Exception:
            pass


def _parse_iso_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_supabase_batch_window(papers: list[dict]) -> str:
    published_ts: list[datetime] = []
    updated_ts: list[datetime] = []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        p_pub = _parse_iso_datetime(str(paper.get("published") or ""))
        p_upd = _parse_iso_datetime(str(paper.get("updated_at") or ""))
        if p_pub:
            published_ts.append(p_pub)
        if p_upd:
            updated_ts.append(p_upd)

    if published_ts:
        published_ts.sort()
        pub_min = published_ts[0].strftime("%Y-%m-%d %H:%M:%S%z")
        pub_max = published_ts[-1].strftime("%Y-%m-%d %H:%M:%S%z")
    else:
        pub_min = pub_max = "N/A"

    if updated_ts:
        updated_ts.sort()
        up_min = updated_ts[0].strftime("%Y-%m-%d %H:%M:%S%z")
        up_max = updated_ts[-1].strftime("%Y-%m-%d %H:%M:%S%z")
    else:
        up_min = up_max = "N/A"

    return f"published=[{pub_min} -> {pub_max}], updated=[{up_min} -> {up_max}]"


def group_start(title: str) -> None:
    try:
        print(f"::group::{title}", flush=True)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass


def group_end() -> None:
    try:
        print("::endgroup::", flush=True)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass


def iter_time_windows(
    start_date: datetime,
    end_date: datetime,
    chunk_days: int,
) -> list[tuple[datetime, datetime]]:
    """
    Split [start_date, end_date] into multiple "minute-level closed interval" windows by chunk_days days.
    To avoid large results from single arXiv API query causing deep pagination/500.
    """
    chunk_days = max(int(chunk_days or 1), 1)
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)
    start_date = start_date.astimezone(timezone.utc)
    end_date = end_date.astimezone(timezone.utc)
    if start_date >= end_date:
        return [(start_date, end_date)]

    windows: list[tuple[datetime, datetime]] = []
    cursor = start_date
    delta = timedelta(days=chunk_days)
    minute = timedelta(minutes=1)

    while cursor < end_date:
        # Use "minute" as the minimum granularity to avoid duplicate adjacent window boundaries (submittedDate query is closed interval)
        raw_end = min(end_date, cursor + delta)
        if raw_end < end_date:
            window_end = raw_end - minute
        else:
            window_end = raw_end

        if window_end < cursor:
            window_end = cursor

        windows.append((cursor, window_end))

        next_cursor = window_end + minute
        if next_cursor <= cursor:
            next_cursor = cursor + minute
        cursor = next_cursor

    return windows


def fetch_category_in_windows(
    client: arxiv.Client,
    category: str,
    windows: list[tuple[datetime, datetime]],
    seen_ids: set[str],
    unique_papers: dict,
    split_on_error_depth: int = 1,
) -> datetime | None:
    """
    Fetch a single large category by time window.
    - Failure granularity down to "single window failure", no loss of entire category;
    - If the window is still too large causing 500, can retry on a smaller window in the upper layer (optional).
    """
    max_published_new: datetime | None = None

    for idx, (win_start, win_end) in enumerate(windows, start=1):
        start_str = win_start.strftime("%Y%m%d%H%M")
        end_str = win_end.strftime("%Y%m%d%H%M")
        group_start(f"Fetch category: {category} (window {idx}/{len(windows)} {start_str}..{end_str})")
        log(f"🚀 Fetching category: {category} | window {idx}/{len(windows)} ...")

        query = f"cat:{category}* AND submittedDate:[{start_str} TO {end_str}]"
        search = arxiv.Search(
            query=query,
            max_results=None,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        count = 0
        try:
            for r in client.results(search):
                pid = r.get_short_id()
                if pid in seen_ids:
                    continue
                if pid in unique_papers:
                    continue

                pdf_link = getattr(r, "pdf_url", None) or r.entry_id
                paper_dict = {
                    "id": pid,
                    "source": "arxiv",
                    "title": r.title.replace("\n", " "),
                    "abstract": r.summary.replace("\n", " "),
                    "authors": [a.name for a in r.authors],
                    "primary_category": r.primary_category,
                    "categories": r.categories,
                    "published": str(r.published),
                    "link": pdf_link,
                }
                unique_papers[pid] = paper_dict
                count += 1

                seen_ids.add(pid)
                published_dt = r.published
                if isinstance(published_dt, datetime):
                    if published_dt.tzinfo is None:
                        published_dt = published_dt.replace(tzinfo=timezone.utc)
                    published_dt = published_dt.astimezone(timezone.utc)
                    if max_published_new is None or published_dt > max_published_new:
                        max_published_new = published_dt

                if count % 200 == 0:
                    log(f"   Category {category} (win {idx}/{len(windows)}): {count} papers fetched...")

            log(f"   ✅ Finished {category} (win {idx}/{len(windows)}): Got {count} new papers.")
        except Exception as e:
            # Single window failure does not affect other windows/categories
            log(f"   ❌ Error fetching category {category} (win {idx}/{len(windows)}): {e}")
            # Fallback: If the window is still too large, try to split the window again (only one layer, to avoid excessive recursion)
            if split_on_error_depth > 0 and (win_end - win_start) >= timedelta(days=2):
                mid = win_start + (win_end - win_start) / 2
                mid = mid.replace(second=0, microsecond=0)
                minute = timedelta(minutes=1)
                left = (win_start, max(minute + win_start, mid - minute))
                right = (mid, win_end)
                log(
                    f"   🔁 Retry by splitting window: "
                    f"{left[0].strftime('%Y%m%d%H%M')}..{left[1].strftime('%Y%m%d%H%M')} | "
                    f"{right[0].strftime('%Y%m%d%H%M')}..{right[1].strftime('%Y%m%d%H%M')}",
                )
                cat_max_left = fetch_category_in_windows(
                    client=client,
                    category=category,
                    windows=[left],
                    seen_ids=seen_ids,
                    unique_papers=unique_papers,
                    split_on_error_depth=split_on_error_depth - 1,
                )
                cat_max_right = fetch_category_in_windows(
                    client=client,
                    category=category,
                    windows=[right],
                    seen_ids=seen_ids,
                    unique_papers=unique_papers,
                    split_on_error_depth=split_on_error_depth - 1,
                )
                for candidate in (cat_max_left, cat_max_right):
                    if candidate and (max_published_new is None or candidate > max_published_new):
                        max_published_new = candidate
            time.sleep(5)
        finally:
            group_end()

    return max_published_new


def fetch_all_domains_metadata_robust(
    days: int | None = None,
    output_file: str | None = None,
    ignore_seen: bool = False,
    chunk_days: int = 7,
    disable_supabase_read: bool = False,
    include_embedding_fields: bool = False,
) -> None:
    config = load_config()

    # 1. Calculate time window (use last crawl time first)
    end_date = datetime.now(timezone.utc)
    if days is None:
        days = resolve_days_window(1)

    # 0) Prioritize Supabase public library (stateless mode)
    # Rules:
    # - Supabase access fails or returns 0: fallback to local crawling;
    # - Supabase returns >0: directly use database results.
    sb = get_supabase_read_config(config)
    if disable_supabase_read:
        sb["enabled"] = False
        log("ℹ️ Supabase priority read disabled; forcing local arXiv crawl this run.")
    if sb.get("enabled"):
        group_start("Step 1 - fetch from Supabase (preferred)")
        sb_url = str(sb.get("url") or "")
        sb_key = str(sb.get("anon_key") or "")
        if not sb_url or not sb_key:
            log("⚠️ Supabase enabled but missing url/anon_key, fallback to local crawling.")
            group_end()
        else:
            sb_start_dt, sb_end_dt, sb_window_label = resolve_supabase_time_window(
                end_date=end_date,
                days=int(days or 1),
            )
            log(f"[Supabase] Read window: {sb_window_label}")
            if str(os.getenv("DPR_RUN_DATE") or "").strip():
                papers, msg = fetch_papers_by_date_range(
                    url=sb_url,
                    api_key=sb_key,
                    papers_table=str(sb.get("papers_table")),
                    start_dt=sb_start_dt,
                    end_dt=sb_end_dt,
                    schema=str(sb.get("schema") or "public"),
                    include_embedding=include_embedding_fields,
                )
            else:
                papers, msg = fetch_recent_papers(
                    url=sb_url,
                    api_key=sb_key,
                    papers_table=str(sb.get("papers_table")),
                    days_window=int(days or 1),
                    schema=str(sb.get("schema") or "public"),
                    include_embedding=include_embedding_fields,
                )
            log(f"[Supabase] {msg}")
            if papers:
                if not output_file:
                    run_token = get_run_date_token(end_date)
                    archive_dir = os.path.join(ROOT_DIR, "archive", run_token)
                    raw_dir = os.path.join(archive_dir, "raw")
                    output_file = os.path.join(raw_dir, f"arxiv_papers_{run_token}.json")

                os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(papers, f, ensure_ascii=False, indent=2)
                log(f"💾 Supabase results written to: {output_file}")
                log(f"[Supabase] Batch time interval: {_format_supabase_batch_window(papers)}")

                # Record crawl time to maintain consistency for subsequent processes
                save_last_crawl_at(end_date)
                group_end()
                return

            log("ℹ️ Supabase returns 0 or unavailable, fallback to local arXiv crawling.")
            group_end()

    # ignore_seen semantic: completely backtrack by days_window, not using last_crawl_at / latest_published_at as starting point
    if ignore_seen:
        log(
            "🧹 [Global Ingest] ignore_seen=true: will ignore arxiv_seen (not skip seen papers, not using latest_published_at),"
            "and ignore crawl_state (not using last_crawl_at), change to strictly backtrack by days_window.",
        )
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

    # Fallback: regardless of source, do not go earlier than (now - days_window)
    start_date = max(start_date, end_date - timedelta(days=days))

    # Safe fallback
    if start_date >= end_date:
        start_date = end_date - timedelta(minutes=1)

    # Split windows by week to avoid large single query (especially broad categories like cs*)
    windows = iter_time_windows(start_date, end_date, chunk_days=chunk_days)
    start_str = start_date.strftime("%Y%m%d%H%M")
    end_str = end_date.strftime("%Y%m%d%H%M")
    
    group_start("Step 1 - fetch arXiv")
    log(f"🌍 [Global Ingest] Window: {start_str} TO {end_str} ({source_desc})")
    if len(windows) > 1:
        log(f"🗓️  [Global Ingest] Split windows by {chunk_days} days/chunk: {len(windows)} chunks")
    
    # Result set uses dictionary to deduplicate (because some papers span multiple domains, like both cs and stat)
    unique_papers = {}
    max_published_new: datetime | None = None
    
    client = arxiv.Client(
        page_size=200,    # Downgrade: from 1000 to 200 to avoid large single response causing 500
        delay_seconds=3.0,
        num_retries=5
    )

    # 2. Iterate over categories to fetch
    for category in CATEGORIES_TO_FETCH:
        cat_max = fetch_category_in_windows(
            client=client,
            category=category,
            windows=windows,
            seen_ids=seen_ids,
            unique_papers=unique_papers,
        )
        if cat_max and (max_published_new is None or cat_max > max_published_new):
            max_published_new = cat_max

    # 3. Save summary results
    total_count = len(unique_papers)
    log(f"✅ All Done. Total unique papers fetched: {total_count}")
    
    if total_count > 0:
        # If not explicitly specified output file, use running token to name the file in the project root directory under archive/<token>/raw directory:
        # <ROOT_DIR>/archive/<YYYYMMDD or YYYYMMDD-YYYYMMDD>/raw/arxiv_papers_<token>.json
        if not output_file:
            run_token = get_run_date_token(end_date)
            archive_dir = os.path.join(ROOT_DIR, "archive", run_token)
            raw_dir = os.path.join(archive_dir, "raw")
            output_file = os.path.join(
                raw_dir,
                f"arxiv_papers_{run_token}.json",
            )

        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(list(unique_papers.values()), f, ensure_ascii=False, indent=2)
        log(f"💾 File saved to: {output_file}")
    else:
        log("⚠️ No papers found. Check your date range or network.")
    if max_published_new:
        save_seen_state(seen_ids, max_published_new)
    else:
        save_seen_state(seen_ids, latest_published_at)
    save_last_crawl_at(end_date)
    group_end()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch arXiv multi-domain paper metadata (by submission time window).")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Fetch window days (priority over config.yaml). If not filled, use days_window from config.yaml.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path (default write to archive/<token>/raw/arxiv_papers_<token>.json).",
    )
    parser.add_argument(
        "--ignore-seen",
        action="store_true",
        help="This run will ignore archive/arxiv_seen.json and archive/crawl_state.json: strictly backtrack by days_window, not skip seen papers.",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=7,
        help="Split time windows into several chunks (default 7=weekly), to reduce single query size and lower HTTP 500 probability.",
    )
    parser.add_argument(
        "--disable-supabase-read",
        action="store_true",
        help="Disable Supabase priority read, force local arXiv crawling.",
    )
    parser.add_argument(
        "--include-embedding-fields",
        action="store_true",
        help="Include embedding fields when fetching papers from Supabase (default not included).",
    )
    args = parser.parse_args()

    # It is recommended to test with --days 1 first, and then run with longer time windows if no problems are found
    fetch_all_domains_metadata_robust(
        days=args.days,
        output_file=args.output,
        ignore_seen=bool(args.ignore_seen),
        chunk_days=int(args.chunk_days or 7),
        disable_supabase_read=bool(args.disable_supabase_read),
        include_embedding_fields=bool(args.include_embedding_fields),
    )
