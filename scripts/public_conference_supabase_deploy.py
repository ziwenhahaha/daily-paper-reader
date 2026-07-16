#!/usr/bin/env python
"""Apply and verify public-conference Supabase SQL.

默认只打印执行计划；只有传入 --yes 时才会调用生产 Supabase Management API。
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from local_env import load_local_env


CONFERENCE_TABLES = {
    "osdi": "osdi_papers",
    "sosp": "sosp_papers",
    "ieee_sp": "ieee_sp_papers",
    "ndss": "ndss_papers",
}

CONFERENCE_QUERIES = {
    "osdi": "operating system",
    "sosp": "operating system",
    "ieee_sp": "security privacy",
    "ndss": "security privacy",
}

SQL_FILES = [
    "create_osdi_papers_schema.sql",
    "create_sosp_papers_schema.sql",
    "create_ieee_sp_papers_schema.sql",
    "create_ndss_papers_schema.sql",
    "match_osdi_papers.sql",
    "match_sosp_papers.sql",
    "match_ieee_sp_papers.sql",
    "match_ndss_papers.sql",
    "enable_conference_anon_read_policies.sql",
]


def _norm(value: object) -> str:
    return str(value or "").strip()


def resolve_project_ref(supabase_url: str, explicit_ref: str = "") -> str:
    direct = _norm(explicit_ref)
    if direct:
        return direct
    host = urlparse(_norm(supabase_url)).hostname or ""
    suffix = ".supabase.co"
    if host.endswith(suffix):
        return host[: -len(suffix)]
    return ""


def sql_paths(names: Iterable[str] = SQL_FILES) -> List[Path]:
    return [ROOT_DIR / "sql" / name for name in names]


def validate_sql_files(paths: Iterable[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("缺少 SQL 文件：" + ", ".join(missing))


def management_query_url(project_ref: str, *, read_only: bool = False) -> str:
    suffix = "/read-only" if read_only else ""
    return f"https://api.supabase.com/v1/projects/{project_ref}/database/query{suffix}"


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


def parse_content_range(value: str) -> int | None:
    text = _norm(value)
    if "/" not in text:
        return None
    total = text.rsplit("/", 1)[-1]
    if total == "*":
        return None
    try:
        return int(total)
    except ValueError:
        return None


def run_management_query(
    *,
    project_ref: str,
    access_token: str,
    query: str,
    read_only: bool = False,
    timeout: int = 120,
) -> object:
    url = management_query_url(project_ref, read_only=read_only)
    body = {"query": query}
    if not read_only:
        body["read_only"] = False
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=timeout,
    )
    response.raise_for_status()
    if not response.text:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


def apply_sql_files(*, project_ref: str, access_token: str, paths: Iterable[Path], timeout: int = 120) -> None:
    for path in paths:
        sql = path.read_text(encoding="utf-8")
        print(f"[sql] apply {path.relative_to(ROOT_DIR)}", flush=True)
        run_management_query(project_ref=project_ref, access_token=access_token, query=sql, timeout=timeout)


def expected_counts_from_raw(raw_dir: str = "/tmp/dpr_public_conference") -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for key in CONFERENCE_TABLES:
        path = Path(raw_dir) / f"{key}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            counts[key] = len(data)
    return counts


def _require_rows(response: requests.Response, *, context: str) -> List[Dict[str, Any]]:
    response.raise_for_status()
    data = response.json() or []
    if not isinstance(data, list):
        raise RuntimeError(f"{context} 返回格式不是 list")
    if not data:
        raise RuntimeError(f"{context} 未返回任何结果")
    return data


def verify_table(
    *,
    supabase_url: str,
    anon_key: str,
    table: str,
    expected_count: int | None = None,
    schema: str = "public",
    timeout: int = 30,
) -> int:
    endpoint = f"{rest_base_url(supabase_url)}/{table}"
    response = requests.get(
        endpoint,
        params={"select": "id,title,pdf_url,embedding_dim", "limit": "1"},
        headers=rest_headers(anon_key, schema, prefer="count=exact"),
        timeout=timeout,
    )
    rows = _require_rows(response, context=f"table {table}")
    sample = rows[0]
    if not _norm(sample.get("id")) or not _norm(sample.get("pdf_url")):
        raise RuntimeError(f"table {table} 样例缺少 id 或 pdf_url")
    count = parse_content_range(response.headers.get("content-range", "")) or len(rows)
    if expected_count is not None and count < expected_count:
        raise RuntimeError(f"table {table} 行数不足：actual={count}, expected>={expected_count}")
    print(f"[verify] table {table}: count={count}, sample={sample.get('id')}", flush=True)
    return count


def verify_rpc(
    *,
    supabase_url: str,
    anon_key: str,
    rpc_name: str,
    payload: Dict[str, Any],
    schema: str = "public",
    timeout: int = 60,
) -> List[Dict[str, Any]]:
    endpoint = f"{rest_base_url(supabase_url)}/rpc/{rpc_name}"
    response = requests.post(
        endpoint,
        json=payload,
        headers={**rest_headers(anon_key, schema), "Content-Type": "application/json"},
        timeout=timeout,
    )
    rows = _require_rows(response, context=f"rpc {rpc_name}")
    sample = rows[0]
    if not _norm(sample.get("id")) or not _norm(sample.get("pdf_url")):
        raise RuntimeError(f"rpc {rpc_name} 样例缺少 id 或 pdf_url")
    print(f"[verify] rpc {rpc_name}: rows={len(rows)}, sample={sample.get('id')}", flush=True)
    return rows


def verify_public_conferences(
    *,
    supabase_url: str,
    anon_key: str,
    raw_dir: str = "/tmp/dpr_public_conference",
    schema: str = "public",
    timeout: int = 60,
) -> None:
    expected_counts = expected_counts_from_raw(raw_dir)
    test_vector = [0.001] * 384
    for key, table in CONFERENCE_TABLES.items():
        verify_table(
            supabase_url=supabase_url,
            anon_key=anon_key,
            table=table,
            expected_count=expected_counts.get(key),
            schema=schema,
            timeout=timeout,
        )
        verify_rpc(
            supabase_url=supabase_url,
            anon_key=anon_key,
            rpc_name=f"match_{key}_papers_bm25",
            payload={
                "query_text": CONFERENCE_QUERIES[key],
                "match_count": 1,
            },
            schema=schema,
            timeout=timeout,
        )
        verify_rpc(
            supabase_url=supabase_url,
            anon_key=anon_key,
            rpc_name=f"match_{key}_papers_exact",
            payload={
                "query_embedding": test_vector,
                "match_count": 1,
            },
            schema=schema,
            timeout=timeout,
        )


def build_sync_commands(raw_dir: str = "/tmp/dpr_public_conference", run_date: str = "20260629") -> List[List[str]]:
    commands: List[List[str]] = []
    for key, table in CONFERENCE_TABLES.items():
        raw_path = Path(raw_dir) / f"{key}.json"
        commands.append(
            [
                sys.executable,
                "src/maintain/sync.py",
                "--backend-key",
                key,
                "--date",
                run_date,
                "--schema",
                "public",
                "--raw-input",
                str(raw_path),
                "--papers-table",
                table,
                "--embed-device",
                "cpu",
                "--embed-batch-size",
                "8",
                "--embed-chunk-size",
                "512",
                "--stream-upsert",
                "--upload-workers",
                "2",
            ]
        )
    return commands


def format_command(command: List[str]) -> str:
    return "PYTHONPATH=src " + " ".join(shlex.quote(part) for part in command)


def print_sync_commands(raw_dir: str = "/tmp/dpr_public_conference", run_date: str = "20260629") -> None:
    for command in build_sync_commands(raw_dir=raw_dir, run_date=run_date):
        print(format_command(command))


def run_sync_commands(raw_dir: str = "/tmp/dpr_public_conference", run_date: str = "20260629") -> None:
    env = os.environ.copy()
    src_path = str(SRC_DIR)
    existing = _norm(env.get("PYTHONPATH"))
    env["PYTHONPATH"] = src_path if not existing else src_path + os.pathsep + existing
    for key, command in zip(CONFERENCE_TABLES, build_sync_commands(raw_dir=raw_dir, run_date=run_date)):
        print(f"[sync] {key}: {format_command(command)}", flush=True)
        subprocess.run(command, cwd=ROOT_DIR, env=env, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply public-conference Supabase SQL and print sync commands.")
    parser.add_argument("--yes", action="store_true", help="真正执行 SQL。默认只 dry-run。")
    parser.add_argument("--project-ref", default=os.getenv("SUPABASE_PROJECT_REF", ""))
    parser.add_argument("--supabase-url", default=os.getenv("SUPABASE_URL", ""))
    parser.add_argument("--access-token", default=os.getenv("SUPABASE_ACCESS_TOKEN", ""))
    parser.add_argument("--anon-key", default=os.getenv("SUPABASE_ANON_KEY", ""))
    parser.add_argument("--schema", default=os.getenv("SUPABASE_SCHEMA", "public"))
    parser.add_argument("--raw-dir", default="/tmp/dpr_public_conference")
    parser.add_argument("--run-date", default="20260629")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--print-sync-commands", action="store_true")
    parser.add_argument("--sync", action="store_true", help="执行四个会议的 sync.py 入库。会写入生产 Supabase。")
    parser.add_argument("--skip-sql", action="store_true", help="配合 --yes 使用：跳过 SQL apply，只执行 sync/verify。")
    parser.add_argument("--verify", action="store_true", help="执行只读 REST/RPC 验证。会调用生产 Supabase API。")
    args = parser.parse_args()

    load_local_env()
    supabase_url = _norm(args.supabase_url or os.getenv("SUPABASE_URL"))
    access_token = _norm(args.access_token or os.getenv("SUPABASE_ACCESS_TOKEN"))
    anon_key = _norm(args.anon_key or os.getenv("SUPABASE_ANON_KEY"))
    project_ref = resolve_project_ref(supabase_url, args.project_ref or os.getenv("SUPABASE_PROJECT_REF", ""))
    paths = sql_paths()
    validate_sql_files(paths)

    print(f"[plan] project_ref={project_ref or '<missing>'}")
    print("[plan] SQL files:")
    for path in paths:
        print(f"  - {path.relative_to(ROOT_DIR)}")

    if args.print_sync_commands:
        print("[plan] sync commands:")
        print_sync_commands(raw_dir=args.raw_dir, run_date=args.run_date)

    if not args.yes:
        if args.sync:
            print("[dry-run] --sync 需要显式配合 --yes，当前不调用 Supabase API。")
        if args.verify:
            print("[dry-run] --verify 需要显式配合 --yes，当前不调用 Supabase API。")
        print("[dry-run] 未传入 --yes，不调用 Supabase API。")
        return
    if not project_ref or not access_token:
        raise SystemExit("缺少 SUPABASE_PROJECT_REF/SUPABASE_URL 或 SUPABASE_ACCESS_TOKEN")

    if not args.skip_sql:
        apply_sql_files(project_ref=project_ref, access_token=access_token, paths=paths, timeout=args.timeout)
        print("[done] SQL applied")
    if args.sync:
        run_sync_commands(raw_dir=args.raw_dir, run_date=args.run_date)
        print("[done] sync finished")
    if args.verify:
        if not supabase_url or not anon_key:
            raise SystemExit("缺少 SUPABASE_URL 或 SUPABASE_ANON_KEY，无法验证")
        verify_public_conferences(
            supabase_url=supabase_url,
            anon_key=anon_key,
            raw_dir=args.raw_dir,
            schema=args.schema,
            timeout=args.timeout,
        )
        print("[done] verification passed")


if __name__ == "__main__":
    main()
