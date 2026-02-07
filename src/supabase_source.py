#!/usr/bin/env python
# Supabase 公共论文库读取工具（只读）

from __future__ import annotations

from datetime import timedelta, timezone, datetime
from typing import Any, Dict, List, Tuple
from urllib.parse import quote
import requests


DEFAULT_TIMEOUT = 20


def _norm(v: Any) -> str:
    return str(v or "").strip()


def get_supabase_read_config(config: Dict[str, Any]) -> Dict[str, Any]:
    root = config or {}
    sb = (root.get("supabase") or {}) if isinstance(root, dict) else {}
    setting = (root.get("arxiv_paper_setting") or {}) if isinstance(root, dict) else {}

    enabled = bool(sb.get("enabled", False))
    prefer_read = bool(setting.get("prefer_supabase_read", True))
    return {
        "enabled": enabled and prefer_read,
        "url": _norm(sb.get("url")),
        "anon_key": _norm(sb.get("anon_key")),
        "papers_table": _norm(sb.get("papers_table") or "arxiv_papers"),
        "schema": _norm(sb.get("schema") or "public"),
    }


def _build_headers(api_key: str) -> Dict[str, str]:
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }


def _base_rest_url(url: str, schema: str) -> str:
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
    # 避免 +00:00 在 URL 中被当成空格，统一转 Z 并编码
    start_iso = start_dt.isoformat().replace("+00:00", "Z")
    start_iso_q = quote(start_iso, safe="")

    rest = _base_rest_url(url, schema)
    endpoint = (
        f"{rest}/{papers_table}"
        f"?select=id,title,abstract,authors,primary_category,categories,published,link,source,"
        f"embedding,embedding_model,embedding_dim,embedding_updated_at"
        f"&published=gte.{start_iso_q}"
        f"&order=published.desc"
        f"&limit={int(max_rows)}"
    )
    try:
        resp = requests.get(endpoint, headers=_build_headers(api_key), timeout=timeout)
        if resp.status_code >= 300:
            return ([], f"papers 查询失败：HTTP {resp.status_code} {resp.text[:200]}")
        rows = resp.json() or []
        if not isinstance(rows, list):
            return ([], "papers 查询结果格式异常")
        out: List[Dict[str, Any]] = []
        for r in rows:
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
        return (out, f"papers 查询成功：{len(out)} 条")
    except Exception as e:
        return ([], f"papers 查询异常：{e}")
