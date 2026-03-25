#!/usr/bin/env python

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
import sys
from typing import Any, Dict, List
from urllib.parse import quote

import requests

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

try:
    from source_config import get_source_backend, load_config_with_source_migration
except Exception:  # pragma: no cover - 兼容 package 导入路径
    from src.source_config import get_source_backend, load_config_with_source_migration


SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")
DEFAULT_TIMEOUT = 60


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        return load_config_with_source_migration(CONFIG_FILE, write_back=False)
    except Exception as exc:
        log(f"[WARN] 读取 config.yaml 失败：{exc}")
        return {}


def _base_rest(url: str) -> str:
    return _norm(url).rstrip("/") + "/rest/v1"


def _headers(service_key: str, schema: str = "public", prefer: str | None = None) -> Dict[str, str]:
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }
    safe_schema = _norm(schema)
    if safe_schema:
        headers["Accept-Profile"] = safe_schema
        headers["Content-Profile"] = safe_schema
    if prefer:
        headers["Prefer"] = prefer
    return headers


def resolve_supabase_config(
    *,
    backend_key: str,
    url: str,
    papers_table: str,
    schema: str,
) -> Dict[str, str]:
    cfg = load_config()
    backend = get_source_backend(cfg, backend_key)
    return {
        "url": _norm(url) or _norm(backend.get("url")),
        "papers_table": _norm(papers_table) or _norm(backend.get("papers_table")) or "arxiv_papers",
        "schema": _norm(schema) or _norm(backend.get("schema")) or "public",
    }


def fetch_old_paper_ids(
    *,
    url: str,
    service_key: str,
    papers_table: str,
    schema: str,
    cutoff_iso: str,
    batch_size: int,
    timeout: int = DEFAULT_TIMEOUT,
) -> List[str]:
    endpoint = (
        f"{_base_rest(url)}/{papers_table}"
        f"?select=id"
        f"&published=lt.{quote(cutoff_iso, safe='')}"
        f"&order=published.asc.nullslast"
        f"&limit={max(int(batch_size or 1), 1)}"
    )
    resp = requests.get(
        endpoint,
        headers=_headers(service_key, schema=schema),
        timeout=max(int(timeout or DEFAULT_TIMEOUT), 1),
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"查询待清理论文失败：HTTP {resp.status_code} {resp.text[:200]}")
    rows = resp.json() or []
    if not isinstance(rows, list):
        raise RuntimeError("查询待清理论文失败：返回结果不是 list")
    out: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pid = _norm(row.get("id"))
        if pid:
            out.append(pid)
    return out


def delete_papers_by_ids(
    *,
    url: str,
    service_key: str,
    papers_table: str,
    schema: str,
    ids: List[str],
    timeout: int = DEFAULT_TIMEOUT,
) -> int:
    safe_ids = [_norm(item) for item in ids if _norm(item)]
    if not safe_ids:
        return 0
    encoded_ids = ",".join(quote(item, safe="") for item in safe_ids)
    endpoint = f"{_base_rest(url)}/{papers_table}?id=in.({encoded_ids})"
    resp = requests.delete(
        endpoint,
        headers=_headers(service_key, schema=schema, prefer="return=minimal"),
        timeout=max(int(timeout or DEFAULT_TIMEOUT), 1),
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"删除旧论文失败：HTTP {resp.status_code} {resp.text[:200]}")
    return len(safe_ids)


def cleanup_old_papers(
    *,
    url: str,
    service_key: str,
    papers_table: str,
    schema: str,
    retention_days: int,
    batch_size: int = 500,
    timeout: int = DEFAULT_TIMEOUT,
    dry_run: bool = False,
) -> Dict[str, Any]:
    safe_days = max(int(retention_days or 1), 1)
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=safe_days)
    cutoff_iso = cutoff_dt.isoformat()

    deleted = 0
    batches = 0
    while True:
        ids = fetch_old_paper_ids(
            url=url,
            service_key=service_key,
            papers_table=papers_table,
            schema=schema,
            cutoff_iso=cutoff_iso,
            batch_size=batch_size,
            timeout=timeout,
        )
        if not ids:
            break
        batches += 1
        log(
            f"[Cleanup] batch={batches} cutoff={cutoff_iso} "
            f"matched={len(ids)} sample={ids[:3]}"
        )
        if dry_run:
            deleted += len(ids)
            break
        deleted += delete_papers_by_ids(
            url=url,
            service_key=service_key,
            papers_table=papers_table,
            schema=schema,
            ids=ids,
            timeout=timeout,
        )

    return {
        "cutoff_iso": cutoff_iso,
        "retention_days": safe_days,
        "deleted": deleted,
        "batches": batches,
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="清理 Supabase 中超过保留天数的历史论文。")
    parser.add_argument("--backend-key", type=str, default=os.getenv("SUPABASE_BACKEND_KEY", "arxiv"))
    parser.add_argument("--url", type=str, default=os.getenv("SUPABASE_URL", ""))
    parser.add_argument("--service-key", type=str, default=os.getenv("SUPABASE_SERVICE_KEY", ""))
    parser.add_argument("--papers-table", type=str, default=os.getenv("SUPABASE_PAPERS_TABLE", ""))
    parser.add_argument("--schema", type=str, default=os.getenv("SUPABASE_SCHEMA", "public"))
    parser.add_argument("--retention-days", type=int, default=45)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    backend_key = _norm(args.backend_key) or "arxiv"
    config = resolve_supabase_config(
        backend_key=backend_key,
        url=args.url,
        papers_table=args.papers_table,
        schema=args.schema,
    )
    service_key = _norm(args.service_key)
    if not config["url"] or not service_key:
        raise RuntimeError("缺少 Supabase 连接信息（url 或 service key），无法执行清理。")

    log(
        f"[Cleanup] backend={backend_key} table={config['papers_table']} schema={config['schema']} "
        f"retention_days={args.retention_days} batch_size={args.batch_size} dry_run={args.dry_run}"
    )
    result = cleanup_old_papers(
        url=config["url"],
        service_key=service_key,
        papers_table=config["papers_table"],
        schema=config["schema"],
        retention_days=args.retention_days,
        batch_size=args.batch_size,
        timeout=args.timeout,
        dry_run=bool(args.dry_run),
    )
    log(
        f"[Cleanup] done deleted={result['deleted']} batches={result['batches']} "
        f"cutoff={result['cutoff_iso']}"
    )


if __name__ == "__main__":
    main()
