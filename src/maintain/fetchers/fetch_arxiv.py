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
except Exception:  # pragma: no cover - 兼容 package 导入路径
    from src.source_config import load_config_with_source_migration

# 项目根目录（当前脚本位于 src/maintain/fetchers/ 下）
SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")
CRAWL_STATE_FILE = os.path.join(ROOT_DIR, "archive", "crawl_state.json")
SEEN_IDS_FILE = os.path.join(ROOT_DIR, "archive", "arxiv_seen.json")

# ArXiv 的主要一级分类列表
# 注意：物理学比较特殊，ArXiv 历史上有很多独立的物理存档，为了保险，我们列出主要的
CATEGORIES_TO_FETCH = [
    "cs", "math", "stat", "q-bio", "q-fin", "eess", "econ",
    "physics", "cond-mat", "hep-ph", "hep-th", "gr-qc", "astro-ph",
]
RANGE_TOKEN_RE = re.compile(r"^\d{8}-\d{8}$")


def load_config() -> dict:
    try:
        return load_config_with_source_migration(CONFIG_FILE, write_back=False)
    except Exception as e:
        log(f"[WARN] 读取 config.yaml 失败：{e}")
        return {}


def resolve_days_window(default_days: int) -> int:
    config = load_config()
    paper_setting = (config or {}).get("arxiv_paper_setting") or {}
    crawler_setting = (config or {}).get("crawler") or {}

    value = paper_setting.get("days_window")
    if value is None:
        value = crawler_setting.get("days_window")
    try:
        days = int(value)
        return max(days, 1)
    except Exception:
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
    区分单天/大区间窗口：
    - 若存在 DPR_RUN_DATE=YYYYMMDD：拉取该自然日 [00:00, +1d)
    - 若存在 DPR_RUN_DATE=YYYYMMDD-YYYYMMDD：拉取该区间 [start_day 00:00, end_day+1d 00:00)
    - 否则回退旧逻辑：最近 days 天 [now-days, now)
    """
    token = str(os.getenv("DPR_RUN_DATE") or "").strip()
    if re.match(r"^\d{8}$", token):
        # 关键修复：
        # main.py 在小窗口（<=7天）下会使用单日 token（如 20260208）作为目录标识，
        # 但这不应强制 Supabase 只查“单天”。
        # 当 days>1 时，仍按滚动窗口拉取，避免 fetch-days=4 却只查 1 天。
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
        # 允许用户用 `| head` 等方式截断输出而不让脚本崩溃
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
    将 [start_date, end_date] 按 chunk_days 天切分成多个“分钟级闭区间”窗口。
    目的是避免单次 arXiv API 查询结果过大导致深分页/500。
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
        # 以“分钟”为最小粒度，避免相邻窗口边界重复（submittedDate 查询是闭区间）
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
    按时间窗口抓取单个大类。
    - 失败粒度降为“单窗口失败”，不会丢掉整个分类；
    - 若窗口仍然过大导致 500，可继续在上层按更小窗口重试（可选）。
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
            # 单个窗口失败不影响其他窗口/分类
            log(f"   ❌ Error fetching category {category} (win {idx}/{len(windows)}): {e}")
            # 回退：如果窗口仍然很大，尝试把该窗口再二分（仅一层，避免过度递归）
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

    # 1. 计算时间窗口（优先使用上次抓取时间）
    end_date = datetime.now(timezone.utc)
    if days is None:
        days = resolve_days_window(1)

    # 0) 优先走 Supabase 公共库（无状态模式）
    # 规则：
    # - Supabase 访问失败或返回 0 条：回退本地爬取；
    # - Supabase 返回 >0 条：直接使用数据库结果。
    sb = get_supabase_read_config(config)
    if disable_supabase_read:
        sb["enabled"] = False
        log("ℹ️ 已关闭 Supabase 优先读取，本次将强制本地 arXiv 抓取。")
    if sb.get("enabled"):
        group_start("Step 1 - fetch from Supabase (preferred)")
        sb_url = str(sb.get("url") or "")
        sb_key = str(sb.get("anon_key") or "")
        if not sb_url or not sb_key:
            log("⚠️ Supabase 已启用但缺少 url/anon_key，回退本地爬取。")
            group_end()
        else:
            sb_start_dt, sb_end_dt, sb_window_label = resolve_supabase_time_window(
                end_date=end_date,
                days=int(days or 1),
            )
            log(f"[Supabase] 读取窗口：{sb_window_label}")
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
                log(f"💾 Supabase 结果已写入：{output_file}")
                log(f"[Supabase] 该批次时间区间：{_format_supabase_batch_window(papers)}")

                # 记录抓取时间，维持后续流程一致性
                save_last_crawl_at(end_date)
                group_end()
                return

            log("ℹ️ Supabase 返回 0 条或不可用，回退本地 arXiv 抓取。")
            group_end()

    # ignore_seen 语义：完全按 days_window 回溯，不使用 last_crawl_at / latest_published_at 作为起点
    if ignore_seen:
        log(
            "🧹 [Global Ingest] ignore_seen=true：将忽略 arxiv_seen（不跳过已见论文，不使用 latest_published_at），"
            "并忽略 crawl_state（不使用 last_crawl_at），改为严格按 days_window 回溯。",
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

    # 兜底：无论来源如何，都不早于 (now - days_window)
    start_date = max(start_date, end_date - timedelta(days=days))

    # 安全兜底
    if start_date >= end_date:
        start_date = end_date - timedelta(minutes=1)

    # 按周拆分窗口，避免单次查询过大（尤其 cs* 这种大类）
    windows = iter_time_windows(start_date, end_date, chunk_days=chunk_days)
    start_str = start_date.strftime("%Y%m%d%H%M")
    end_str = end_date.strftime("%Y%m%d%H%M")
    
    group_start("Step 1 - fetch arXiv")
    log(f"🌍 [Global Ingest] Window: {start_str} TO {end_str} ({source_desc})")
    if len(windows) > 1:
        log(f"🗓️  [Global Ingest] 将按 {chunk_days} 天/片拆分窗口：{len(windows)} 段")
    
    # 结果集使用字典去重 (因为有些论文跨领域，比如同时在 cs 和 stat)
    unique_papers = {}
    max_published_new: datetime | None = None
    
    client = arxiv.Client(
        page_size=200,    # 降级：从 1000 降到 200，避免单次响应过大导致 500
        delay_seconds=3.0,
        num_retries=5
    )

    # 2. 遍历分类进行抓取
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

    # 3. 保存汇总结果
    total_count = len(unique_papers)
    log(f"✅ All Done. Total unique papers fetched: {total_count}")
    
    if total_count > 0:
        # 若未显式指定输出文件，则按运行 token 命名到项目根目录下的 archive/<token>/raw 目录：
        # <ROOT_DIR>/archive/<YYYYMMDD 或 YYYYMMDD-YYYYMMDD>/raw/arxiv_papers_<token>.json
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

    parser = argparse.ArgumentParser(description="抓取 arXiv 多领域论文元数据（按提交时间窗口）。")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="抓取窗口天数（优先级高于 config.yaml）。不填则使用 config.yaml 的 days_window。",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出 JSON 文件路径（默认写入 archive/<token>/raw/arxiv_papers_<token>.json）。",
    )
    parser.add_argument(
        "--ignore-seen",
        action="store_true",
        help="本次运行忽略 archive/arxiv_seen.json 与 archive/crawl_state.json：严格按 days_window 回溯窗口，不跳过已见论文。",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=7,
        help="将时间窗口拆分为若干段（默认 7=按周），以减少单次查询规模并降低 HTTP 500 概率。",
    )
    parser.add_argument(
        "--disable-supabase-read",
        action="store_true",
        help="关闭 Supabase 优先读取，强制执行本地 arXiv 抓取。",
    )
    parser.add_argument(
        "--include-embedding-fields",
        action="store_true",
        help="从 Supabase 拉取论文时额外包含 embedding 字段（默认不带）。",
    )
    args = parser.parse_args()

    # 建议先用 --days 1 测试一下，没问题再跑更长时间窗口
    fetch_all_domains_metadata_robust(
        days=args.days,
        output_file=args.output,
        ignore_seen=bool(args.ignore_seen),
        chunk_days=int(args.chunk_days or 7),
        disable_supabase_read=bool(args.disable_supabase_read),
        include_embedding_fields=bool(args.include_embedding_fields),
    )
