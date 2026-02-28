#!/usr/bin/env python
# Supabase 公共论文库读取工具（只读）

from __future__ import annotations

from datetime import timedelta, timezone, datetime
from typing import Any, Dict, List, Tuple
from urllib.parse import quote
import re
import requests


DEFAULT_TIMEOUT = 20


def _parse_datetime_like(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            n = float(value)
        except Exception:
            return None
        if n <= 0:
            return None
        sec = n / 1000 if n > 10_000_000_000 else n
        return datetime.fromtimestamp(sec, tz=timezone.utc)

    text = _norm(value)
    if not text:
        return None

    if re.fullmatch(r"\d{8}", text):
        try:
            return datetime.strptime(text, "%Y%m%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None

    if " " in text and len(text) > 10:
        # 兼容 '2026-02-28 12:00:00'
        text = text.replace(" ", "T", 1)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_within_time_window(
    record: Dict[str, Any],
    *,
    start_dt: datetime | None,
    end_dt: datetime | None,
    time_fields: tuple[str, ...] = ("published",),
    keep_without_time: bool = True,
) -> bool:
    if not start_dt or not end_dt:
        return True
    if end_dt <= start_dt:
        return True

    for field in time_fields:
        dt = _parse_datetime_like(record.get(field))
        if dt is None:
            continue
        if start_dt <= dt < end_dt:
            return True

    return keep_without_time


def _filter_rows_by_window(
    rows: List[Dict[str, Any]],
    *,
    start_dt: datetime | None,
    end_dt: datetime | None,
    time_fields: tuple[str, ...] = ("published",),
) -> List[Dict[str, Any]]:
    if not rows or not start_dt or not end_dt:
        return rows
    return [
        row
        for row in rows
        if isinstance(row, dict) and _is_within_time_window(row, start_dt=start_dt, end_dt=end_dt, time_fields=time_fields)
    ]


def _norm(v: Any) -> str:
    return str(v or "").strip()


def get_supabase_read_config(config: Dict[str, Any]) -> Dict[str, Any]:
    root = config or {}
    sb = (root.get("supabase") or {}) if isinstance(root, dict) else {}
    setting = (root.get("arxiv_paper_setting") or {}) if isinstance(root, dict) else {}

    enabled = bool(sb.get("enabled", False))
    prefer_read = bool(setting.get("prefer_supabase_read", True))
    use_vector_rpc = bool(sb.get("use_vector_rpc", False))
    return {
        "enabled": enabled and prefer_read,
        "use_vector_rpc": use_vector_rpc,
        "use_bm25_rpc": bool(sb.get("use_bm25_rpc", False)),
        "url": _norm(sb.get("url")),
        "anon_key": _norm(sb.get("anon_key")),
        "papers_table": _norm(sb.get("papers_table") or "arxiv_papers"),
        "schema": _norm(sb.get("schema") or "public"),
        "vector_rpc": _norm(sb.get("vector_rpc") or "match_arxiv_papers"),
        "bm25_rpc": _norm(sb.get("bm25_rpc") or "match_arxiv_papers_bm25"),
    }


def _build_headers(api_key: str, schema: str = "public") -> Dict[str, str]:
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    safe_schema = _norm(schema)
    if safe_schema:
        headers["Accept-Profile"] = safe_schema
        headers["Content-Profile"] = safe_schema
    return headers


def _base_rest_url(url: str) -> str:
    u = _norm(url).rstrip("/")
    return f"{u}/rest/v1"


def _parse_embedding(value: Any) -> List[float]:
    """
    兼容 pgvector 的多种返回形式：
    - "[0.1,0.2,...]" 字符串
    - [0.1, 0.2, ...] 数组
    """
    if isinstance(value, list):
        out: List[float] = []
        for x in value:
            try:
                out.append(float(x))
            except Exception:
                return []
        return out
    text = _norm(value)
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    parts = [p.strip() for p in text.split(",") if p.strip()]
    out: List[float] = []
    for p in parts:
        try:
            out.append(float(p))
        except Exception:
            return []
    return out


def fetch_recent_papers(
    *,
    url: str,
    api_key: str,
    papers_table: str,
    days_window: int,
    schema: str = "public",
    timeout: int = DEFAULT_TIMEOUT,
    max_rows: int = 20000,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    从 Supabase 拉取窗口内论文元数据。
    约定 papers_table 至少含字段：
    id,title,abstract,authors,primary_category,categories,published,link,source
    """
    safe_days = max(int(days_window or 1), 1)
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=safe_days)
    return fetch_papers_by_date_range(
        url=url,
        api_key=api_key,
        papers_table=papers_table,
        start_dt=start_dt,
        end_dt=end_dt,
        schema=schema,
        timeout=timeout,
        max_rows=max_rows,
    )


def fetch_papers_by_date_range(
    *,
    url: str,
    api_key: str,
    papers_table: str,
    start_dt: datetime,
    end_dt: datetime,
    schema: str = "public",
    timeout: int = DEFAULT_TIMEOUT,
    max_rows: int = 20000,
    time_fields: tuple[str, ...] = ("published",),
) -> Tuple[List[Dict[str, Any]], str]:
    """
    按明确时间区间拉取论文：
    - published >= start_dt
    - published < end_dt
    """
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    start_dt = start_dt.astimezone(timezone.utc)
    end_dt = end_dt.astimezone(timezone.utc)
    if end_dt <= start_dt:
        return ([], "时间窗口非法：end_dt <= start_dt")

    # 避免 +00:00 在 URL 中被当成空格，统一转 Z 并编码
    start_iso_q = quote(start_dt.isoformat().replace("+00:00", "Z"), safe="")
    end_iso_q = quote(end_dt.isoformat().replace("+00:00", "Z"), safe="")

    rest = _base_rest_url(url)
    per_page = min(max(int(max_rows or 1), 1), 1000)
    fetched = 0
    offset = 0
    all_rows: List[Dict[str, Any]] = []
    try:
        while fetched < int(max_rows):
            page_limit = min(per_page, int(max_rows) - fetched)
            endpoint = (
                f"{rest}/{papers_table}"
                f"?select=id,title,abstract,authors,primary_category,categories,published,link,source,"
                f"embedding,embedding_model,embedding_dim,embedding_updated_at"
                f"&published=gte.{start_iso_q}"
                f"&published=lt.{end_iso_q}"
                f"&order=published.desc"
                f"&limit={int(page_limit)}"
                f"&offset={int(offset)}"
            )
            resp = requests.get(endpoint, headers=_build_headers(api_key, schema), timeout=timeout)
            if resp.status_code >= 300:
                return ([], f"papers 查询失败：HTTP {resp.status_code} {resp.text[:200]}")
            rows = resp.json() or []
            if not isinstance(rows, list):
                return ([], "papers 查询结果格式异常")
            if not rows:
                break
            all_rows.extend(rows)
            got = len(rows)
            fetched += got
            offset += got
            # 最后一页（不足页大小）即可结束
            if got < page_limit:
                break

        out: List[Dict[str, Any]] = []
        for r in all_rows:
            if not isinstance(r, dict):
                continue
            pid = _norm(r.get("id"))
            if not pid:
                continue
            emb_dim = 0
            try:
                emb_dim = int(r.get("embedding_dim") or 0)
            except Exception:
                emb_dim = 0
            out.append(
                {
                    "id": pid,
                    "source": _norm(r.get("source") or "supabase"),
                    "title": _norm(r.get("title")),
                    "abstract": _norm(r.get("abstract")),
                    "authors": r.get("authors") if isinstance(r.get("authors"), list) else [],
                    "primary_category": _norm(r.get("primary_category")) or None,
                    "categories": r.get("categories") if isinstance(r.get("categories"), list) else [],
                    "published": _norm(r.get("published")),
                    "link": _norm(r.get("link")),
                    "embedding": _parse_embedding(r.get("embedding")),
                    "embedding_model": _norm(r.get("embedding_model")),
                    "embedding_dim": emb_dim,
                    "embedding_updated_at": _norm(r.get("embedding_updated_at")),
                }
            )
        return (
            out,
            f"papers 查询成功：{len(out)} 条（分页，offset 到 {offset}，window={start_dt.isoformat()}~{end_dt.isoformat()}）",
        )
    except Exception as e:
        return ([], f"papers 查询异常：{e}")


def match_papers_by_embedding(
    *,
    url: str,
    api_key: str,
    rpc_name: str,
    query_embedding: List[float],
    match_count: int,
    schema: str = "public",
    timeout: int = DEFAULT_TIMEOUT,
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
    time_fields: tuple[str, ...] = ("published",),
) -> Tuple[List[Dict[str, Any]], str]:
    """
    调用 Supabase RPC，在数据库侧执行向量相似度检索。
    约定 RPC 参数：
      - query_embedding: vector(N)
      - match_count: int
    """
    safe_rpc = _norm(rpc_name)
    if not safe_rpc:
        safe_rpc = "match_arxiv_papers"
    vec = [float(x) for x in (query_embedding or [])]
    if not vec:
        return ([], "query embedding 为空")
    k = max(int(match_count or 1), 1)
    endpoint = f"{_base_rest_url(url)}/rpc/{safe_rpc}"
    payload = {
        "query_embedding": vec,
        "match_count": k,
    }
    try:
        resp = requests.post(
            endpoint,
            headers={
                **_build_headers(api_key, schema),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=max(int(timeout or DEFAULT_TIMEOUT), 1),
        )
        if resp.status_code >= 300:
            return ([], f"rpc 查询失败：HTTP {resp.status_code} {resp.text[:200]}")
        rows = resp.json() or []
        if not isinstance(rows, list):
            return ([], "rpc 查询结果格式异常")
        rows = _filter_rows_by_window(
            rows,
            start_dt=start_dt,
            end_dt=end_dt,
            time_fields=time_fields,
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            pid = _norm(r.get("id"))
            if not pid:
                continue
            sim = r.get("similarity")
            try:
                sim_f = float(sim)
            except Exception:
                sim_f = 0.0
            out.append(
                {
                    "id": pid,
                    "title": _norm(r.get("title")),
                    "abstract": _norm(r.get("abstract")),
                    "published": _norm(r.get("published")) or None,
                    "link": _norm(r.get("link")) or None,
                    "authors": r.get("authors") if isinstance(r.get("authors"), list) else [],
                    "primary_category": _norm(r.get("primary_category")) or None,
                    "categories": r.get("categories") if isinstance(r.get("categories"), list) else [],
                    "source": "supabase",
                    "similarity": sim_f,
                }
            )
        return (out, f"rpc 查询成功：{len(out)} 条")
    except Exception as e:
        return ([], f"rpc 查询异常：{e}")


def match_papers_by_bm25(
    *,
    url: str,
    api_key: str,
    rpc_name: str,
    query_text: str,
    match_count: int,
    schema: str = "public",
    timeout: int = DEFAULT_TIMEOUT,
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
    time_fields: tuple[str, ...] = ("published",),
) -> Tuple[List[Dict[str, Any]], str]:
    """
    调用 Supabase RPC，在数据库侧执行 BM25 风格检索（PostgreSQL FTS）。
    约定 RPC 参数：
      - query_text: text
      - match_count: int
    """
    safe_rpc = _norm(rpc_name)
    if not safe_rpc:
        safe_rpc = "match_arxiv_papers_bm25"
    q = _norm(query_text)
    if not q:
        return ([], "query_text 为空")
    k = max(int(match_count or 1), 1)
    endpoint = f"{_base_rest_url(url)}/rpc/{safe_rpc}"
    payload = {
        "query_text": q,
        "match_count": k,
    }
    try:
        resp = requests.post(
            endpoint,
            headers={
                **_build_headers(api_key, schema),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=max(int(timeout or DEFAULT_TIMEOUT), 1),
        )
        if resp.status_code >= 300:
            return ([], f"rpc 查询失败：HTTP {resp.status_code} {resp.text[:200]}")
        rows = resp.json() or []
        if not isinstance(rows, list):
            return ([], "rpc 查询结果格式异常")
        rows = _filter_rows_by_window(
            rows,
            start_dt=start_dt,
            end_dt=end_dt,
            time_fields=time_fields,
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            pid = _norm(r.get("id"))
            if not pid:
                continue
            out.append(
                {
                    "id": pid,
                    "title": _norm(r.get("title")),
                    "abstract": _norm(r.get("abstract")),
                    "published": _norm(r.get("published")) or None,
                    "link": _norm(r.get("link")) or None,
                    "authors": r.get("authors") if isinstance(r.get("authors"), list) else [],
                    "primary_category": _norm(r.get("primary_category")) or None,
                    "categories": r.get("categories") if isinstance(r.get("categories"), list) else [],
                    "score": r.get("score"),
                    "similarity": r.get("similarity"),
                }
            )
        return (out, f"rpc 查询成功：{len(out)} 条")
    except Exception as e:
        return ([], f"rpc 查询异常：{e}")
