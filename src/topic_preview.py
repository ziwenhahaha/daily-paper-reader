"""匿名 FTS 范围预览：只计数，不抓正文，不调用模型，不承诺相关性。"""

from __future__ import annotations

import base64
import calendar
from datetime import date, timedelta
import hashlib
import json
import math
import re
import time
from urllib.parse import urlsplit

import requests

THRESHOLD = 1500
MAX_REQUESTS = 16
TOTAL_TIMEOUT = 25
CACHE_SECONDS = 30
_CACHE = {}


def _enabled(value):
    return value is None or str(value).lower() not in {"false", "0", "no", "off"}


def english_groups(profile):
    explicit = profile.get("constraint_groups")
    if explicit is not None:
        if (
            not isinstance(explicit, list)
            or not explicit
            or any(not isinstance(g, list) or not g for g in explicit)
        ):
            raise ValueError("英文约束组无效，无法确认范围")
        raw_groups = explicit
    else:
        terms = []
        for item in profile.get("keywords") or []:
            if isinstance(item, str):
                terms.append(item)
            elif isinstance(item, dict) and _enabled(item.get("enabled")):
                terms.append(
                    item.get("keyword") or item.get("query") or item.get("text") or ""
                )
        raw_groups = [terms]
    if explicit is not None and (
        len(raw_groups) > 3
        or any(len(g) > 8 for g in raw_groups)
        or math.prod(len(g) for g in raw_groups) > 32
    ):
        raise ValueError("英文约束过多，无法在交互预算内确认范围")
    if explicit is None and sum(len(g) for g in raw_groups) > 24:
        raise ValueError("英文约束过多，无法在交互预算内确认范围")
    groups = []
    for raw in raw_groups:
        values = []
        for value in raw:
            text = " ".join(str(value).split()) if isinstance(value, str) else ""
            # 不将中文/混合语句送给英文FTS后错误显示0；不自行翻译或扩词。
            if (
                not re.search(r"[A-Za-z]", text)
                or re.search(r"[^\x20-\x7e]", text)
                or len(text) > 240
            ):
                raise ValueError("缺少可直接计数的英文关键词，请先完善英文研究约束")
            if text not in values:
                values.append(text)
        if not values:
            raise ValueError("缺少可直接计数的英文关键词，请先完善英文研究约束")
        groups.append(values)
    return groups


def scope_for(mode, as_of):
    if str(mode) not in {"90", "365", "starter"}:
        raise ValueError("不支持的预览范围")
    end = date.fromisoformat(str(as_of))
    days = 90 if str(mode) == "90" else 365
    result = {
        "mode": str(mode),
        "arxiv": {
            "start": (end - timedelta(days=days)).isoformat(),
            "end_exclusive": end.isoformat(),
        },
    }
    if mode == "starter":
        start = end.replace(
            year=end.year - 2,
            day=min(end.day, calendar.monthrange(end.year - 2, end.month)[1]),
        )
        result["conference"] = {
            "start": start.isoformat(),
            "end_exclusive": end.isoformat(),
        }
    return result


def count_filter(groups, start, end):
    def quote(term):
        return '"' + term.replace("\\", "\\\\").replace('"', '\\"') + '"'

    clauses = ["published.gte." + start, "published.lt." + end]
    clauses += [
        "or(" + ",".join("search_tsv.plfts(english)." + quote(t) for t in group) + ")"
        for group in groups
    ]
    return "(" + ",".join(clauses) + ")"


def public_key(key):
    if re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]+", key or ""):
        return True
    try:
        part = key.split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return payload.get("role") == "anon"
    except (AttributeError, IndexError, ValueError, TypeError):
        return False


def backend_for(config):
    from source_config import get_source_backend

    backend = get_source_backend(config or {}, "arxiv")
    key = str(backend.get("publishable_key") or backend.get("anon_key") or "")
    raw_url = str(backend.get("url") or "").rstrip("/")
    parsed = urlsplit(raw_url)
    if (
        backend.get("enabled") is False
        or not public_key(key)
        or parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("缺少可用的匿名论文库连接，范围未确认")
    table, schema = str(backend.get("papers_table") or "arxiv_papers"), str(
        backend.get("schema") or "public"
    )
    if any(
        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item) for item in (table, schema)
    ):
        raise ValueError("论文库配置不合法，范围未确认")
    endpoint = raw_url if raw_url.endswith("/rest/v1") else raw_url + "/rest/v1"
    return endpoint + "/" + table, key, schema


def preview_threshold(value=None, config=None):
    if value is None:
        value = ((config or {}).get("topic_research") or {}).get(
            "preview_threshold", THRESHOLD
        )
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        value = int(value)
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int))
        or not re.fullmatch(r"\d+", str(value))
    ):
        raise ValueError("预览阈值必须是1–10000整数")
    number = int(value)
    if not 1 <= number <= 10000:
        raise ValueError("预览阈值必须是1–10000整数")
    return number


def preview(
    *, profile, mode, as_of, conferences=None, config=None, request=None, threshold=None
):
    scope = None
    coverage = {
        "arxiv": {"status": "unknown", "completed_windows": 0},
        "conference": {
            "status": "unavailable" if mode == "starter" else "not_requested",
            "selected": conferences or [],
        },
    }
    base = {
        "status": "unknown",
        "count": None,
        "threshold": THRESHOLD,
        "scope": scope,
        "coverage": coverage,
        "reason": "范围未确认",
    }
    try:
        threshold = preview_threshold(threshold, config)
        base["threshold"] = threshold
    except (ValueError, TypeError, AttributeError):
        base.update(threshold=None, reason="预览阈值必须是1–10000整数；范围未确认")
        return base
    try:
        groups = english_groups(profile or {})
        scope = scope_for(str(mode), as_of)
        base["scope"] = scope
        endpoint, key, schema = backend_for(config)
    except (ValueError, TypeError, AttributeError):
        base["reason"] = "英文研究约束、时间范围或匿名连接不可用；未把未确认结果记为0"
        return base
    identity = hashlib.sha256(
        json.dumps(
            [endpoint, schema, groups, scope, conferences or [], threshold],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cached = _CACHE.get(identity)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return json.loads(json.dumps(cached[1]))
    end = date.fromisoformat(scope["arxiv"]["end_exclusive"])
    start = date.fromisoformat(scope["arxiv"]["start"])
    windows = []
    while end > start:
        lower = max(start, end - timedelta(days=30))
        windows.append((lower.isoformat(), end.isoformat()))
        end = lower
    coverage["arxiv"]["total_windows"] = len(windows)
    total = completed = 0
    deadline = time.monotonic() + TOTAL_TIMEOUT
    call = request or requests.head
    for lower, upper in windows[:MAX_REQUESTS]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        headers = {
            "apikey": key,
            "Accept-Profile": schema,
            "Prefer": "count=exact",
            "Range": "0-0",
        }
        if not key.startswith("sb_publishable_"):
            headers["Authorization"] = "Bearer " + key
        try:
            response = call(
                endpoint,
                params={
                    "select": "id",
                    "limit": "1",
                    "and": count_filter(groups, lower, upper),
                },
                headers=headers,
                timeout=min(6, remaining),
                allow_redirects=False,
            )
            if response.status_code not in (200, 206):
                break
            match = re.fullmatch(
                r"(?:\d+-\d+|\*)/(\d+)",
                str(response.headers.get("Content-Range") or "").strip(),
            )
            if not match:
                break
            total += int(match[1])
            completed += 1
            if total > threshold:
                break
        except (requests.RequestException, TimeoutError, ValueError):
            break
    coverage["arxiv"].update(
        status=(
            "exact"
            if completed == len(windows)
            else "partial" if completed else "unknown"
        ),
        completed_windows=completed,
    )
    base["count"] = total if completed else None
    if total > threshold:
        base.update(
            status="lower_bound",
            reason=f"已计数的不重叠时间片已超过{threshold}；这是范围规模，不是相关性判断",
        )
    elif completed == len(windows) and mode != "starter":
        base.update(
            status="exact", reason="英文关键词FTS命中数已确认；不等于相关论文数量"
        )
    else:
        base.update(
            status="partial" if completed else "unknown",
            reason=(
                "仅确认arXiv部分规模，会议总量未确认"
                if mode == "starter"
                else "计数预算耗尽或请求未完成，完整规模未确认"
            ),
        )
    if len(_CACHE) >= 64:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[identity] = (time.monotonic(), json.loads(json.dumps(base)))
    return base
