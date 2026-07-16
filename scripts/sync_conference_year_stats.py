#!/usr/bin/env python
"""生成会议年份统计快照，并可同步到 Supabase。

前端只读取生成后的静态 JSON；脚本运行时才访问 Supabase。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple
from urllib.parse import urlparse

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from local_env import load_local_env


DEFAULT_OUTPUT = ROOT_DIR / "app" / "conference-stats.json"
SQL_PATH = ROOT_DIR / "sql" / "create_conference_year_stats_schema.sql"

CONFERENCE_SPECS: Tuple[Dict[str, str], ...] = (
    {"key": "iclr", "label": "ICLR", "table": "iclr_openreview_papers"},
    {"key": "icml", "label": "ICML", "table": "icml_openreview_papers"},
    {"key": "neurips", "label": "NeurIPS", "table": "neurips_openreview_papers"},
    {"key": "aaai", "label": "AAAI", "table": "aaai_papers"},
    {"key": "cvpr", "label": "CVPR", "table": "cvpr_papers"},
    {"key": "eccv", "label": "ECCV", "table": "eccv_papers"},
    {"key": "ijcai", "label": "IJCAI", "table": "ijcai_papers"},
    {"key": "acl", "label": "ACL", "table": "acl_papers"},
    {"key": "emnlp", "label": "EMNLP", "table": "emnlp_papers"},
    {"key": "osdi", "label": "OSDI", "table": "osdi_papers"},
    {"key": "sosp", "label": "SOSP", "table": "sosp_papers"},
    {"key": "ieee_sp", "label": "IEEE S&P", "table": "ieee_sp_papers"},
    {"key": "ndss", "label": "NDSS", "table": "ndss_papers"},
)

# 官方录取数仅在“生产库不是完整 accepted 集合”的会议上强制给定。
# 其它会议从 Supabase 中 accepted source 计数回退得到，reject 会额外展示。
OFFICIAL_ACCEPTED_COUNTS: Dict[Tuple[str, int], int] = {
    ("osdi", 2024): 53,
    ("osdi", 2025): 53,
    ("osdi", 2026): 136,
    ("sosp", 2024): 43,
    ("sosp", 2025): 66,
    ("ieee_sp", 2024): 261,
    ("ieee_sp", 2025): 255,
    ("ieee_sp", 2026): 254,
    ("ndss", 2024): 140,
    ("ndss", 2025): 211,
    ("ndss", 2026): 265,
}


def _norm(value: object) -> str:
    return str(value or "").strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_years() -> List[int]:
    current = datetime.now(timezone.utc).year
    return [current, current - 1, current - 2]


def parse_years(value: str) -> List[int]:
    raw = _norm(value)
    if not raw:
        return default_years()
    years: List[int] = []
    seen = set()
    for part in raw.replace(";", ",").replace(" ", ",").split(","):
        text = _norm(part)
        if not text:
            continue
        year = int(text)
        if year not in seen:
            seen.add(year)
            years.append(year)
    return years or default_years()


def year_from_row(row: Mapping[str, Any]) -> int | None:
    source = _norm(row.get("source"))
    match = re.search(r"(?:^|[^0-9])((?:19|20)[0-9]{2})(?:[^0-9]|$)", source)
    if match:
        return int(match.group(1))
    published = _norm(row.get("published"))
    if len(published) >= 4 and published[:4].isdigit():
        return int(published[:4])
    return None


def classify_source_status(source: str) -> str:
    text = _norm(source).lower()
    if "reject" in text:
        return "rejected"
    if "withdraw" in text:
        return "other"
    if "accept" in text:
        return "accepted"
    if re.match(r"^icml-[0-9]{4}-public$", text):
        return "accepted"
    # 这些源本身就是官方 accepted/proceedings/open-access 列表。
    accepted_markers = (
        "csdl",
        "usenix",
        "ndss",
        "sosp",
        "cvpr",
        "eccv",
        "ijcai",
        "acl",
        "emnlp",
        "aaai",
        "proceedings",
    )
    if any(marker in text for marker in accepted_markers):
        return "accepted"
    return "other"


def build_conference_year_stats(
    rows_by_table: Mapping[str, List[Mapping[str, Any]]],
    *,
    official_counts: Mapping[Tuple[str, int], int] | None = None,
    years: Iterable[int] | None = None,
    generated_at: str | None = None,
) -> List[Dict[str, Any]]:
    official_counts = official_counts or OFFICIAL_ACCEPTED_COUNTS
    include_all_specs = years is not None
    selected_years = list(years or sorted({year_from_row(row) for rows in rows_by_table.values() for row in rows if year_from_row(row)}, reverse=True))
    if not selected_years:
        selected_years = default_years()
    generated = generated_at or now_iso()

    table_year_counts: Dict[Tuple[str, int], Counter[str]] = defaultdict(Counter)
    for table, rows in rows_by_table.items():
        for row in rows:
            year = year_from_row(row)
            if year is None:
                continue
            table_year_counts[(table, year)][classify_source_status(_norm(row.get("source")))] += 1

    out: List[Dict[str, Any]] = []
    for spec in CONFERENCE_SPECS:
        key = spec["key"]
        table = spec["table"]
        if not include_all_specs and table not in rows_by_table:
            continue
        for year in selected_years:
            counts = table_year_counts.get((table, int(year)), Counter())
            if not include_all_specs and not counts:
                continue
            accepted = int(counts.get("accepted", 0))
            rejected = int(counts.get("rejected", 0))
            other = int(counts.get("other", 0))
            total = accepted + rejected + other
            official = int(official_counts.get((key, int(year)), accepted))
            out.append(
                {
                    "id": f"{key}-{int(year)}",
                    "conference_key": key,
                    "conference_label": spec["label"],
                    "year": int(year),
                    "source_table": table,
                    "official_accepted_count": official,
                    "stored_total_count": total,
                    "stored_accepted_count": accepted,
                    "stored_rejected_count": rejected,
                    "stored_other_count": other,
                    "generated_at": generated,
                    "updated_at": generated,
                }
            )
    out.sort(key=lambda item: (item["conference_label"].lower(), -int(item["year"])))
    return out


def rest_base_url(supabase_url: str) -> str:
    return _norm(supabase_url).rstrip("/") + "/rest/v1"


def rest_headers(api_key: str, schema: str = "public", *, prefer: str = "") -> Dict[str, str]:
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Accept-Profile": schema,
        "Content-Profile": schema,
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def fetch_table_rows(
    *,
    supabase_url: str,
    service_key: str,
    table: str,
    schema: str = "public",
    page_size: int = 1000,
    timeout: int = 60,
) -> List[Dict[str, Any]]:
    endpoint = f"{rest_base_url(supabase_url)}/{table}"
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        response = requests.get(
            endpoint,
            params={
                "select": "id,source,published",
                "limit": str(page_size),
                "offset": str(offset),
            },
            headers=rest_headers(service_key, schema),
            timeout=timeout,
        )
        response.raise_for_status()
        chunk = response.json() or []
        if not isinstance(chunk, list):
            raise RuntimeError(f"{table} 返回格式不是 list")
        rows.extend(item for item in chunk if isinstance(item, dict))
        if len(chunk) < page_size:
            return rows
        offset += page_size


def fetch_all_conference_rows(*, supabase_url: str, service_key: str, schema: str = "public") -> Dict[str, List[Dict[str, Any]]]:
    rows_by_table: Dict[str, List[Dict[str, Any]]] = {}
    for spec in CONFERENCE_SPECS:
        table = spec["table"]
        rows = fetch_table_rows(supabase_url=supabase_url, service_key=service_key, table=table, schema=schema)
        rows_by_table[table] = rows
        print(f"[stats] fetched {table}: {len(rows)} rows", flush=True)
    return rows_by_table


def build_snapshot(items: List[Dict[str, Any]], generated_at: str) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "items": items,
    }


def write_snapshot(path: Path, snapshot: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[stats] wrote {path}", flush=True)


def resolve_project_ref(supabase_url: str, explicit_ref: str = "") -> str:
    if _norm(explicit_ref):
        return _norm(explicit_ref)
    host = urlparse(_norm(supabase_url)).hostname or ""
    suffix = ".supabase.co"
    if host.endswith(suffix):
        return host[: -len(suffix)]
    return ""


def management_query_url(project_ref: str) -> str:
    return f"https://api.supabase.com/v1/projects/{project_ref}/database/query"


def apply_sql_schema(*, supabase_url: str, access_token: str, project_ref: str = "", timeout: int = 120) -> None:
    resolved_ref = resolve_project_ref(supabase_url, project_ref)
    if not resolved_ref:
        raise RuntimeError("无法解析 Supabase project ref")
    sql = SQL_PATH.read_text(encoding="utf-8")
    response = requests.post(
        management_query_url(resolved_ref),
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"query": sql, "read_only": False},
        timeout=timeout,
    )
    response.raise_for_status()
    print(f"[stats] applied {SQL_PATH.relative_to(ROOT_DIR)}", flush=True)


def upsert_stats_rows(
    *,
    supabase_url: str,
    service_key: str,
    rows: List[Dict[str, Any]],
    schema: str = "public",
    timeout: int = 60,
) -> None:
    if not rows:
        return
    endpoint = f"{rest_base_url(supabase_url)}/conference_year_stats"
    response = requests.post(
        endpoint,
        params={"on_conflict": "id"},
        headers={**rest_headers(service_key, schema, prefer="resolution=merge-duplicates"), "Content-Type": "application/json"},
        json=rows,
        timeout=timeout,
    )
    response.raise_for_status()
    print(f"[stats] upserted conference_year_stats: {len(rows)} rows", flush=True)


def load_required_env() -> Tuple[str, str, str, str, str]:
    load_local_env()
    supabase_url = _norm(os.getenv("SUPABASE_URL"))
    service_key = _norm(os.getenv("SUPABASE_SERVICE_KEY"))
    anon_key = _norm(os.getenv("SUPABASE_ANON_KEY"))
    access_token = _norm(os.getenv("SUPABASE_ACCESS_TOKEN"))
    schema = _norm(os.getenv("SUPABASE_SCHEMA") or "public")
    if not supabase_url or not service_key:
        raise RuntimeError("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_KEY")
    return supabase_url, service_key, anon_key, access_token, schema


def verify_stats_table(*, supabase_url: str, anon_key: str, schema: str = "public", timeout: int = 30) -> int:
    if not anon_key:
        print("[stats] skip anon verify: SUPABASE_ANON_KEY missing", flush=True)
        return 0
    response = requests.get(
        f"{rest_base_url(supabase_url)}/conference_year_stats",
        params={"select": "id,conference_key,year,stored_total_count,official_accepted_count", "limit": "1"},
        headers=rest_headers(anon_key, schema, prefer="count=exact"),
        timeout=timeout,
    )
    response.raise_for_status()
    content_range = response.headers.get("content-range", "")
    total = 0
    if "/" in content_range:
        tail = content_range.rsplit("/", 1)[-1]
        if tail.isdigit():
            total = int(tail)
    print(f"[stats] verified conference_year_stats via anon: count={total or 'unknown'}", flush=True)
    return total


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步会议年份统计快照。")
    parser.add_argument("--years", default="", help="年份列表，默认当前年及前两年。")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="静态 JSON 输出路径。")
    parser.add_argument("--apply-sql", action="store_true", help="先在生产 Supabase 应用统计表 schema。")
    parser.add_argument("--sync", action="store_true", help="将统计结果 upsert 到 Supabase。")
    parser.add_argument("--verify", action="store_true", help="同步后用 anon key 验证统计表可读。")
    parser.add_argument("--project-ref", default="", help="Supabase project ref；默认从 SUPABASE_URL 推断。")
    args = parser.parse_args(argv)

    supabase_url, service_key, anon_key, access_token, schema = load_required_env()
    if args.apply_sql and not access_token:
        raise RuntimeError("应用 SQL 需要 SUPABASE_ACCESS_TOKEN")
    if args.apply_sql:
        apply_sql_schema(supabase_url=supabase_url, access_token=access_token, project_ref=args.project_ref)

    years = parse_years(args.years)
    generated_at = now_iso()
    rows_by_table = fetch_all_conference_rows(supabase_url=supabase_url, service_key=service_key, schema=schema)
    items = build_conference_year_stats(
        rows_by_table,
        official_counts=OFFICIAL_ACCEPTED_COUNTS,
        years=years,
        generated_at=generated_at,
    )
    snapshot = build_snapshot(items, generated_at)
    write_snapshot(Path(args.output), snapshot)
    if args.sync:
        upsert_stats_rows(supabase_url=supabase_url, service_key=service_key, rows=items, schema=schema)
    if args.verify:
        verify_stats_table(supabase_url=supabase_url, anon_key=anon_key, schema=schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
